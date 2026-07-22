"""Predictive Maintenance dashboard - PT Astra Otoparts Tbk / WINTEQ, Case 2.

Run with:  streamlit run app/dashboard.py   (from the project root)

Replays cached NASA IMS Bearing pipeline output (see scripts/build_artifacts.py)
snapshot-by-snapshot to show health score, alarm status and RUL behaviour as
a machine degrades. Two views:

  - Fleet Overview: a manager-facing, all-machines-at-once command center -
    the landing page - so a reviewer never has to hunt through a sidebar to
    find which of several machines needs attention right now.
  - Machine Detail: the original single-machine replay (health gauge, trend,
    signal detail, alerts/recommendation) - unchanged from the earlier
    single-page version, just moved into its own function.

All user-facing text is in Bahasa Indonesia (dashboard's primary audience is
plant technicians/operators, not just managers - see feedback log). Internal
code comments/docstrings stay in English.

Temperature and current are synthetic (see pdm/synthetic_sensors.py) - the
NASA IMS dataset only records vibration. This is intentionally not
auto-disclosed in the UI (see pdm/synthetic_sensors.py + docs/proposal for
the full methodology note); answer honestly if asked directly in person.
"""

import base64
import io
import sys
import time
import wave
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app import theme  # noqa: E402
from pdm.bearing_physics import fault_frequencies  # noqa: E402
from pdm.data_loader import RUN_SPECS, DATA_ROOT, FS_HZ, load_channel  # noqa: E402
from pdm.features import envelope_spectrum  # noqa: E402

ARTIFACTS_DIR = SRC_ROOT / "artifacts"
FAULT_FREQS = fault_frequencies()

st.set_page_config(
    page_title="Astra Otoparts - Pemeliharaan Prediktif",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(theme.global_css(), unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Data loading / shared helpers
# ----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_bearing_df(run_key: str, bearing_id: int) -> pd.DataFrame:
    path = ARTIFACTS_DIR / f"{run_key}_bearing{bearing_id}.csv"
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df


def artifacts_available() -> bool:
    return (ARTIFACTS_DIR / "summary.csv").exists()


def fmt_duration(hours: float) -> str:
    if hours is None or (isinstance(hours, float) and np.isnan(hours)):
        return "-"
    days = int(hours // 24)
    rem_h = hours - days * 24
    if days > 0:
        return f"{days}hr {rem_h:.0f}j"
    return f"{hours:.1f}j"


def bearing_label(spec, bearing_id: int, mark_failing: bool = True) -> str:
    tag = " (dipantau - kegagalan diketahui)" if mark_failing and bearing_id == spec.failing_bearing else ""
    return f"Motor Conveyor - Bearing {bearing_id}{tag}"


def _healthy_threshold(df: pd.DataFrame, col: str, healthy_n: int) -> float:
    healthy = df[col].iloc[:healthy_n]
    return float(healthy.mean() + 3 * healthy.std())


def _style_axes(fig: go.Figure) -> go.Figure:
    """Soft technical grid + hairline axis - shared look across every chart."""
    fig.update_xaxes(gridcolor="#EEF2F7", zeroline=False, showline=True, linecolor=theme.COLORS["border"])
    fig.update_yaxes(gridcolor="#EEF2F7", zeroline=False, showline=True, linecolor=theme.COLORS["border"])
    return fig


def _rgba(hex_color: str, alpha: float) -> str:
    """Plotly's fillcolor rejects 8-digit hex (#RRGGBBAA) - convert to rgba()."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _logo_chip() -> str:
    """Header mark: icon-only globe crop, no wordmark, no background chip -
    the full Astra Otoparts wordmark (with a legibility chip) stays in the
    sidebar; the topbar just wants the round globe by itself."""
    return theme.astra_globe_img(30)


if not artifacts_available():
    st.markdown(
        f'<div class="astra-topbar"><div style="display:flex;align-items:center;gap:12px">'
        f'{_logo_chip()}<div>'
        f'<div class="title">Pemeliharaan Prediktif &mdash; Motor Induksi</div>'
        f'<div class="subtitle">PT Astra Otoparts Tbk &middot; WINTEQ &middot; Prototipe Case 2</div>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )
    st.warning(
        "Belum ada artifact hasil precompute. Jalankan "
        "`python -m scripts.build_artifacts --all` dari direktori root project, "
        "lalu muat ulang halaman ini."
    )
    st.stop()


# ----------------------------------------------------------------------
# Critical alert overlay: fixed banner + looping alarm tone + Acknowledge.
# Shared by both pages - context_key scopes acknowledgement so switching
# machine/page re-arms it, and it auto re-arms if the alarm clears and
# fires again later (see the "items empty" branch below).
# ----------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _alarm_wav_base64() -> str:
    """In-memory two-tone siren beep - no external audio asset needed."""
    sample_rate = 22050

    def tone(freq: float, duration: float) -> np.ndarray:
        t = np.arange(int(sample_rate * duration)) / sample_rate
        envelope = np.clip(np.minimum(t, duration - t) * 40 + 0.15, 0.0, 1.0)
        return 0.5 * envelope * np.sin(2 * np.pi * freq * t)

    siren = np.concatenate([tone(880, 0.35), tone(660, 0.35)] * 3)
    pcm = (siren * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return base64.b64encode(buf.getvalue()).decode("ascii")


def render_critical_banner(items: list, context_key: str) -> bool:
    """items: list of {"label", "reason"} dicts for currently-CRITICAL machines.
    Returns True while the banner is actually showing (unacknowledged) - callers
    that auto-advance (autoplay) must pause while this is True, otherwise the
    Acknowledge button is torn down and rebuilt by the next auto-rerun faster
    than a click can complete its round trip, making it effectively unclickable."""
    ack = st.session_state.get("_ack_marker")
    if not items:
        if ack and ack[0] == context_key:
            st.session_state.pop("_ack_marker", None)
        return False

    marker = (context_key, frozenset(it["label"] for it in items))
    if ack == marker:
        return False

    shown, rest = items[:3], items[3:]
    names = "; ".join(f"{it['label']} — {it['reason']}" for it in shown)
    if rest:
        names += f"; dan {len(rest)} mesin kritis lainnya"
    b64 = _alarm_wav_base64()
    st.markdown(
        f"""
        <style>
        @keyframes astra-pulse {{
            0%, 100% {{ background-color: {theme.COLORS['critical']}; }}
            50% {{ background-color: #7F1D1D; }}
        }}
        .astra-critical-banner {{
            position: fixed; top: 0; left: 0; right: 0; z-index: 999999;
            padding: 14px 24px; color: white; text-align: center;
            font-family: 'Lexend', sans-serif; font-weight: 600; font-size: 0.98rem;
            box-shadow: 0 4px 18px rgba(0,0,0,0.35);
            animation: astra-pulse 1s ease-in-out infinite;
        }}
        .block-container {{ padding-top: 4.6rem !important; }}
        </style>
        <div class="astra-critical-banner">
            {theme.icon("alert-octagon", 20, "white")}&nbsp; PERINGATAN KRITIS &mdash; {names}
        </div>
        <audio autoplay loop>
            <source src="data:audio/wav;base64,{b64}" type="audio/wav">
        </audio>
        """,
        unsafe_allow_html=True,
    )
    _, ack_col, _ = st.columns([1, 1.4, 1])
    with ack_col:
        if st.button(
            "Konfirmasi & lanjutkan pemantauan",
            key=f"ack_{context_key}",
            use_container_width=True,
            type="primary",
        ):
            st.session_state["_ack_marker"] = marker
            st.rerun()
    st.caption(
        "Jika tidak ada suara, klik di mana saja pada halaman ini sekali - browser "
        "memblokir audio otomatis sampai ada interaksi pengguna pertama."
    )
    return True


# ----------------------------------------------------------------------
# Fleet Overview page
# ----------------------------------------------------------------------
@st.dialog("Tampilan cepat")
def render_quick_view_dialog(item: dict) -> None:
    """A floating preview so a manager can glance at one machine's trend
    without leaving Fleet Overview - opens on top of the page, closes back
    to the same overview state, only navigates to Machine Detail if asked."""
    row = item["row"]
    run_key, bearing_id, spec = item["run_key"], item["bearing_id"], item["spec"]
    level = row["alarm_level"]
    color = theme.STATUS_COLOR[level]

    st.markdown(f"#### {item['label']}")
    st.caption(f"{spec.label} · t = {row['elapsed_hours']:.1f} jam")
    badge_cls = "status-badge pulse" if level == "CRITICAL" else "status-badge"
    st.markdown(
        f'<div class="{badge_cls}" style="background:{color}1A;color:{color}">'
        f'{theme.icon_for_status(level, 16)} {theme.STATUS_LABEL[level]}</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    m1, m2, m3 = st.columns(3)
    m1.metric("Skor kesehatan", f"{row['health_score']:.0f}/100")
    if row["rul_status"] == "estimated" and not pd.isna(row["rul_hours"]):
        m2.metric("Sisa Umur Pakai", fmt_duration(float(row["rul_hours"])))
    else:
        m2.metric("Sisa Umur Pakai", "Pemantauan")
    m3.metric("RMS Getaran", f"{row['rms']:.3f} g")

    df = load_bearing_df(run_key, bearing_id)
    visible = df.iloc[: item["idx"] + 1]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=visible["elapsed_hours"], y=visible["health_score"],
        mode="lines", line=dict(color=theme.COLORS["accent"], width=2), name="Skor kesehatan",
    ))
    alarm_mask = visible["is_alarm"]
    if alarm_mask.any():
        fig.add_trace(go.Scatter(
            x=visible.loc[alarm_mask, "elapsed_hours"], y=visible.loc[alarm_mask, "health_score"],
            mode="markers", marker=dict(color=theme.COLORS["critical"], size=4), name="Alarm aktif",
        ))
    fig.update_layout(
        height=220, margin=dict(l=10, r=10, t=25, b=10),
        xaxis_title="Jam berjalan", yaxis_title="Skor kesehatan", yaxis_range=[0, 105],
        plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
        title=dict(text="Tren skor kesehatan sejauh ini", font=dict(size=12)),
    )
    fig.data[0].update(fill="tozeroy", fillcolor=_rgba(theme.COLORS["accent"], 0.08))
    _style_axes(fig)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown(f"**Alasan:** {row['alarm_reason']}")

    st.write("")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Buka detail lengkap", key=f"qv_open_{run_key}_{bearing_id}",
                      type="primary", use_container_width=True):
            st.session_state["nav_run_key"] = run_key
            st.session_state["nav_bearing_id"] = bearing_id
            st.session_state["_nav_page_override"] = "Detail Mesin"
            st.rerun()
    with b2:
        if st.button("Tutup", key=f"qv_close_{run_key}_{bearing_id}", use_container_width=True):
            st.rerun()


def render_machine_card(item: dict, param_focus: str) -> None:
    row = item["row"]
    level = row["alarm_level"]
    color = theme.STATUS_COLOR[level]

    if level == "CRITICAL" and row["rul_status"] == "estimated" and not pd.isna(row["rul_hours"]):
        rul_line = f"Kritis dalam {fmt_duration(float(row['rul_hours']))}"
    elif level == "CRITICAL":
        rul_line = "Kritis — Sisa Umur Pakai belum stabil"
    elif row["rul_status"] == "estimated" and not pd.isna(row["rul_hours"]):
        rul_line = f"Sisa Umur Pakai {fmt_duration(float(row['rul_hours']))}"
    else:
        rul_line = "Pemantauan"

    extra = ""
    if param_focus in ("Semua parameter", "Getaran"):
        extra += f'<div class="kpi-sub metric-mono">RMS Getaran: {row["rms"]:.3f} g</div>'
    if param_focus in ("Semua parameter", "Suhu") and "temperature_c" in row.index:
        extra += f'<div class="kpi-sub metric-mono">Suhu: {row["temperature_c"]:.1f} &deg;C</div>'
    if param_focus in ("Semua parameter", "Arus") and "current_a" in row.index:
        extra += f'<div class="kpi-sub metric-mono">Arus: {row["current_a"]:.2f} A</div>'

    badge_cls = "status-badge pulse" if level == "CRITICAL" else "status-badge"
    st.markdown(
        f"""
        <div class="kpi-card" style="border-top:4px solid {color}">
            <div class="kpi-label">{item['label']}</div>
            <div class="{badge_cls}" style="background:{color}1A;color:{color};margin:6px 0">
                {theme.icon_for_status(level, 16)} {theme.STATUS_LABEL[level]}
            </div>
            <div class="kpi-value" style="font-size:1.4rem">{row['health_score']:.0f}
                <span style="font-size:0.8rem;color:{theme.COLORS['text_muted']}">/100 kesehatan</span></div>
            <div class="kpi-sub" style="font-weight:700;color:{theme.COLORS['primary']}">{rul_line}</div>
            {extra}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Tampilan cepat", key=f"card_{item['run_key']}_{item['bearing_id']}", use_container_width=True):
        render_quick_view_dialog(item)


def render_overview_page() -> None:
    st.markdown(
        f'<div class="astra-topbar"><div style="display:flex;align-items:center;gap:12px">'
        f'{_logo_chip()}<div>'
        f'<div class="title">Ringkasan Armada &mdash; Semua Mesin</div>'
        f'<div class="subtitle">PT Astra Otoparts Tbk &middot; WINTEQ &middot; Prototipe Case 2</div>'
        f'</div></div>'
        f'<div style="text-align:right;font-size:0.88rem;opacity:0.92">'
        f'8 bearing dipantau &middot; 2 run produksi</div></div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([2.2, 1])
    with c1:
        pct = st.slider(
            "Waktu armada — % waktu yang telah berlalu di tiap run mesin",
            0, 100, value=st.session_state.get("fleet_pct", 78), key="fleet_pct",
            help="Semua 8 bearing adalah data replay historis, bukan streaming langsung - slider "
                 "ini menggeser semua mesin ke titik relatif yang sama pada run masing-masing, "
                 "sehingga seluruh armada terlihat maju bersama seperti command center langsung.",
        )
    with c2:
        param_focus = st.selectbox(
            "Fokus parameter", ["Semua parameter", "Getaran", "Suhu", "Arus"],
            key="fleet_param_focus",
        )

    items = []
    for run_key, spec in RUN_SPECS.items():
        for bearing_id in range(1, spec.n_bearings + 1):
            df = load_bearing_df(run_key, bearing_id)
            n = len(df)
            idx = int(round(pct / 100 * (n - 1)))
            items.append({
                "run_key": run_key, "spec": spec, "bearing_id": bearing_id,
                "label": f"{spec.label.split(' (')[0]} — Bearing {bearing_id}",
                "row": df.iloc[idx], "n": n, "idx": idx,
            })

    sort_rank = {"CRITICAL": 0, "WARNING": 1, "NORMAL": 2}

    def sort_key(it):
        row = it["row"]
        rul = row["rul_hours"]
        rul_key = float(rul) if (row["rul_status"] == "estimated" and not pd.isna(rul)) else 1e9
        return (sort_rank.get(row["alarm_level"], 3), rul_key)

    items.sort(key=sort_key)

    critical_items = [it for it in items if it["row"]["alarm_level"] == "CRITICAL"]
    banner_items = []
    for it in critical_items:
        row = it["row"]
        if row["rul_status"] == "estimated" and not pd.isna(row["rul_hours"]):
            reason = f"kegagalan diperkirakan dalam {fmt_duration(float(row['rul_hours']))}"
        else:
            reason = row["alarm_reason"]
        banner_items.append({"label": it["label"], "reason": reason})
    render_critical_banner(banner_items, context_key="overview")

    n_crit = len(critical_items)
    n_warn = sum(1 for it in items if it["row"]["alarm_level"] == "WARNING")
    n_norm = sum(1 for it in items if it["row"]["alarm_level"] == "NORMAL")

    k1, k2, k3, k4 = st.columns(4)
    for col, label, value, color in (
        (k1, "Mesin dipantau", str(len(items)), theme.COLORS["primary"]),
        (k2, "Kritis", str(n_crit), theme.COLORS["critical"]),
        (k3, "Peringatan", str(n_warn), theme.COLORS["warning"]),
        (k4, "Normal", str(n_norm), theme.COLORS["normal"]),
    ):
        with col:
            st.markdown(
                f'<div class="kpi-card"><div class="fleet-kpi-label">{label}</div>'
                f'<div class="fleet-kpi-value" style="color:{color}">{value}</div></div>',
                unsafe_allow_html=True,
            )

    st.write("")
    st.markdown("#### Perlu perhatian")
    attention = [it for it in items if it["row"]["alarm_level"] != "NORMAL"]
    if not attention:
        st.success("Tidak ada mesin dalam status Peringatan atau Kritis pada waktu armada saat ini.")
    else:
        for it in attention:
            row = it["row"]
            level = row["alarm_level"]
            color = theme.STATUS_COLOR[level]
            if level == "CRITICAL" and row["rul_status"] == "estimated" and not pd.isna(row["rul_hours"]):
                detail = f"Kritis → kegagalan diperkirakan dalam {fmt_duration(float(row['rul_hours']))}"
            elif level == "CRITICAL":
                detail = "Kritis → eskalasi segera, Sisa Umur Pakai belum stabil"
            else:
                detail = "Peringatan → jadwalkan inspeksi pada jendela pemeliharaan berikutnya"
            row_col1, row_col2 = st.columns([6, 1])
            with row_col1:
                st.markdown(
                    f'<div class="attention-row" style="border-left-color:{color}">'
                    f'<b>{it["label"]}</b> &middot; {it["spec"].label} &nbsp;&mdash;&nbsp; {detail}</div>',
                    unsafe_allow_html=True,
                )
            with row_col2:
                if st.button("Buka", key=f"open_{it['run_key']}_{it['bearing_id']}", use_container_width=True):
                    st.session_state["nav_run_key"] = it["run_key"]
                    st.session_state["nav_bearing_id"] = it["bearing_id"]
                    st.session_state["_nav_page_override"] = "Detail Mesin"
                    st.rerun()

    st.write("")
    st.markdown("#### Semua mesin")
    only_alerts = st.checkbox("Tampilkan hanya mesin Peringatan / Kritis", value=False, key="fleet_only_alerts")

    for run_key, spec in RUN_SPECS.items():
        st.markdown(f"**{spec.label}**")
        group = [it for it in items if it["run_key"] == run_key]
        if only_alerts:
            group = [it for it in group if it["row"]["alarm_level"] != "NORMAL"]
        group.sort(key=lambda it: it["bearing_id"])
        if not group:
            st.caption("Semua bearing pada run ini normal di waktu armada saat ini.")
            continue
        cols = st.columns(len(group))
        for col, it in zip(cols, group):
            with col:
                render_machine_card(it, param_focus)
        st.write("")


# ----------------------------------------------------------------------
# Machine Detail page (original single-machine replay)
# ----------------------------------------------------------------------
def render_detail_page() -> None:
    for nav_key, state_key in (("nav_run_key", "detail_run_key"), ("nav_bearing_id", "detail_bearing_id")):
        nav_value = st.session_state.pop(nav_key, None)
        if nav_value is not None:
            st.session_state[state_key] = nav_value

    st.sidebar.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
        f'{theme.icon("settings", size=18, color=theme.COLORS["accent"])}'
        f'<b style="font-family:Lexend,sans-serif;color:{theme.COLORS["primary"]}">Kontrol Replay</b></div>',
        unsafe_allow_html=True,
    )

    run_options = list(RUN_SPECS.keys())
    run_key = st.sidebar.selectbox(
        "Run produksi", options=run_options,
        format_func=lambda k: RUN_SPECS[k].label, key="detail_run_key",
    )
    spec = RUN_SPECS[run_key]

    bearing_options = list(range(1, spec.n_bearings + 1))
    bearing_id = st.sidebar.selectbox(
        "Mesin / bearing", options=bearing_options,
        index=bearing_options.index(spec.failing_bearing),
        format_func=lambda b: bearing_label(spec, b), key="detail_bearing_id",
    )

    df = load_bearing_df(run_key, bearing_id)
    n = len(df)

    alarm_idx = np.flatnonzero(df["is_alarm"].to_numpy())
    default_pos = int(min(alarm_idx[0] + 20, n - 1)) if len(alarm_idx) else n - 1

    state_key = (run_key, bearing_id)
    if "pos_slider" not in st.session_state or st.session_state.get("_loaded_key") != state_key:
        st.session_state["pos_slider"] = default_pos
        st.session_state._loaded_key = state_key
        st.session_state.playing = False

    # Streamlit forbids writing to a widget's session_state key AFTER that widget
    # has been instantiated in the same run - so Reset/autoplay must update
    # pos_slider BEFORE the slider below is created, never after.
    if st.session_state.get("_reset_requested"):
        st.session_state["pos_slider"] = default_pos
        st.session_state.playing = False
        st.session_state._reset_requested = False

    speed = st.session_state.get("_speed", "16x")
    step_map = {"1x": 1, "4x": 4, "16x": 16, "64x": 64}
    if st.session_state.get("playing"):
        new_pos = min(st.session_state["pos_slider"] + step_map[speed], n - 1)
        st.session_state["pos_slider"] = new_pos
        if new_pos >= n - 1:
            st.session_state.playing = False

    position = st.sidebar.slider("Posisi snapshot", 0, n - 1, key="pos_slider")

    play_col1, play_col2 = st.sidebar.columns(2)
    if play_col1.button(("Jeda" if st.session_state.playing else "Putar"), use_container_width=True):
        st.session_state.playing = not st.session_state.playing
        st.rerun()
    if play_col2.button("Reset", use_container_width=True):
        st.session_state._reset_requested = True
        st.rerun()
    speed = st.sidebar.select_slider("Kecepatan pemutaran", options=["1x", "4x", "16x", "64x"],
                                      value=speed, key="_speed")

    st.sidebar.markdown(
        f'<div class="data-source-caption">{theme.icon("database", size=14, color=theme.COLORS["text_muted"])}'
        f' Dataset NASA IMS Bearing (run-to-failure) &middot; Rexnord ZA-2115 &middot; 2000 RPM'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.caption(
        f"Rentang run: {df['elapsed_hours'].iloc[-1]:.1f} jam dalam {n} snapshot "
        f"(satu snapshot tiap 10 menit)."
    )

    current = df.iloc[position]
    visible = df.iloc[: position + 1]

    # ----------------------------------------------------------------------
    # Pop-up alert: fires once when the alarm status ESCALATES at this exact
    # point in the replay (NORMAL->WARNING, WARNING->CRITICAL, etc.) - not on
    # every rerun, and not on every row, only on the actual transition.
    # ----------------------------------------------------------------------
    _SEVERITY = {"NORMAL": 0, "WARNING": 1, "CRITICAL": 2}
    _toast_marker = (state_key, position)
    if position > 0 and st.session_state.get("_last_toast_marker") != _toast_marker:
        prev_level = df.iloc[position - 1]["alarm_level"]
        curr_level = current["alarm_level"]
        if _SEVERITY.get(curr_level, 0) > _SEVERITY.get(prev_level, 0):
            toast_icon = ":material/error:" if curr_level == "CRITICAL" else ":material/warning:"
            st.toast(
                f"{bearing_label(spec, bearing_id)} meningkat ke {theme.STATUS_LABEL[curr_level]} "
                f"- {current['alarm_reason']}",
                icon=toast_icon,
            )
        st.session_state["_last_toast_marker"] = _toast_marker

    # Big, hard-to-miss overlay - stays up (with looping alarm tone) until acknowledged.
    if current["alarm_level"] == "CRITICAL":
        if current["rul_status"] == "estimated" and not np.isnan(current["rul_hours"]):
            reason = f"kegagalan diperkirakan dalam {fmt_duration(float(current['rul_hours']))}"
        else:
            reason = current["alarm_reason"]
        banner_showing = render_critical_banner(
            [{"label": bearing_label(spec, bearing_id), "reason": reason}],
            context_key=f"detail_{run_key}_{bearing_id}",
        )
    else:
        banner_showing = render_critical_banner([], context_key=f"detail_{run_key}_{bearing_id}")

    if banner_showing:
        # Autoplay must not keep auto-rerunning while an unacknowledged alert is
        # on screen, or the Acknowledge button never survives long enough to be
        # clicked (see render_critical_banner docstring). The sidebar Play/Pause
        # button above already rendered this frame with the stale "Playing"
        # label - fire ONE corrective rerun (only on the actual transition, not
        # every frame) so the button relabels itself before the user ever sees it.
        was_playing = st.session_state.get("playing", False)
        st.session_state.playing = False
        if was_playing:
            st.rerun()

    # ----------------------------------------------------------------------
    # Top bar
    # ----------------------------------------------------------------------
    st.markdown(
        f'<div class="astra-topbar"><div style="display:flex;align-items:center;gap:12px">'
        f'{_logo_chip()}<div>'
        f'<div class="title">Pemeliharaan Prediktif &mdash; Motor Induksi</div>'
        f'<div class="subtitle">PT Astra Otoparts Tbk &middot; WINTEQ &middot; Prototipe Case 2</div>'
        f'</div></div>'
        f'<div style="text-align:right;font-size:0.88rem;opacity:0.92">'
        f'{bearing_label(spec, bearing_id)}<br>{spec.label} &middot; t = {current["elapsed_hours"]:.1f} jam'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ----------------------------------------------------------------------
    # KPI row
    # ----------------------------------------------------------------------
    kpi1, kpi2, kpi3 = st.columns(3)

    with kpi1:
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=float(current["health_score"]),
            number={"suffix": "", "font": {"size": 32, "color": theme.COLORS["primary"], "family": "JetBrains Mono, monospace"}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": theme.COLORS["border"]},
                "bar": {"color": theme.COLORS["accent"], "thickness": 0.75},
                "bgcolor": "#FBFCFF",
                "bordercolor": theme.COLORS["border"],
                "steps": [
                    {"range": [0, 40], "color": "#FEE2E2"},
                    {"range": [40, 70], "color": "#FEF3C7"},
                    {"range": [70, 100], "color": "#DCFCE7"},
                ],
            },
            domain={"x": [0, 1], "y": [0, 1]},
        ))
        fig.update_layout(
            height=170, margin=dict(l=20, r=20, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.markdown(
            f'<div class="kpi-label">{theme.icon("activity", 14, theme.COLORS["text_muted"])} SKOR KESEHATAN</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with kpi2:
        level = current["alarm_level"]
        color = theme.STATUS_COLOR[level]
        badge_cls = "status-badge pulse" if level == "CRITICAL" else "status-badge"
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{theme.icon("alert-triangle", 14, theme.COLORS["text_muted"])} STATUS ALARM</div>'
            f'<div class="{badge_cls}" style="background:{color}1A;color:{color}">'
            f'{theme.icon_for_status(level, 18)} {theme.STATUS_LABEL[level]}</div>'
            f'<div class="kpi-sub">{current["alarm_reason"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with kpi3:
        if current["rul_status"] == "estimated" and not np.isnan(current["rul_hours"]):
            rul_val = fmt_duration(float(current["rul_hours"]))
            sub = "Estimasi Sisa Umur Pakai"
        else:
            rul_val = "Pemantauan"
            sub = "Belum stabil - tren degradasi masih terbentuk"
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{theme.icon("clock", 14, theme.COLORS["text_muted"])} SISA UMUR PAKAI</div>'
            f'<div class="kpi-value">{rul_val}</div>'
            f'<div class="kpi-sub">{sub}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.write("")
    with st.expander("Kenapa Skor Kesehatan dan Status Alarm bisa terlihat tidak sinkron?"):
        st.markdown(
            "Kedua angka di atas berasal dari dua mekanisme yang berbeda tujuan, jadi wajar kalau "
            "sekilas terlihat tidak sejalan:\n\n"
            "- **Skor Kesehatan** adalah indeks kontinu berbasis **PCA** (Principal Component Analysis) "
            "dari fitur-fitur getaran (RMS, kurtosis, crest factor, energi BPFO/BPFI/BSF) - turun "
            "bertahap seiring bearing berdegradasi.\n"
            "- **Status Alarm** adalah keputusan **diskrit** dari logika *persistence + voting* (dan "
            "Isolation Forest sebagai model anomali) atas getaran, temperature, dan current - butuh "
            "beberapa window konfirmasi berturut-turut sebelum naik atau turun level.\n\n"
            "Karena itu, sebuah bearing bisa punya Skor Kesehatan yang masih relatif tinggi tapi "
            "sudah berstatus Kritis (karena voting sudah mengonfirmasi beberapa parameter tidak "
            "normal secara persisten), atau sebaliknya - Skor Kesehatan sudah cukup rendah tapi "
            "statusnya baru Peringatan (karena parameter belum cukup persisten/tervoting untuk "
            "naik ke Kritis). Keduanya benar, hanya menjawab pertanyaan yang berbeda."
        )

    # ----------------------------------------------------------------------
    # Tabs
    # ----------------------------------------------------------------------
    tab_trend, tab_signal, tab_sensors, tab_alerts = st.tabs(
        ["Tren", "Detail Sinyal", "Sensor", "Peringatan & Rekomendasi"]
    )

    with tab_trend:
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Skor Kesehatan seiring waktu**")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=visible["elapsed_hours"], y=visible["health_score"],
                mode="lines", line=dict(color=theme.COLORS["accent"], width=2), name="Skor kesehatan",
            ))
            if "health_score_fitted" in visible.columns and visible["health_score_fitted"].notna().any():
                fig.add_trace(go.Scatter(
                    x=visible["elapsed_hours"], y=visible["health_score_fitted"],
                    mode="lines", line=dict(color=theme.COLORS["warning"], width=2, dash="dash"),
                    name="Lintasan prediksi",
                ))
            alarm_mask = visible["is_alarm"]
            if alarm_mask.any():
                fig.add_trace(go.Scatter(
                    x=visible.loc[alarm_mask, "elapsed_hours"], y=visible.loc[alarm_mask, "health_score"],
                    mode="markers", marker=dict(color=theme.COLORS["critical"], size=5),
                    name="Alarm aktif",
                ))
            if len(alarm_idx) and alarm_idx[0] <= position:
                fig.add_vline(
                    x=float(df["elapsed_hours"].iloc[alarm_idx[0]]),
                    line_dash="dash", line_color=theme.COLORS["warning"],
                    annotation_text="Pemicu / Awal Sisa Umur Pakai", annotation_position="top",
                )
            fig.add_vline(x=float(current["elapsed_hours"]), line_color=theme.COLORS["primary"], line_width=1)
            fig.update_layout(
                height=340, margin=dict(l=10, r=10, t=10, b=10),
                xaxis_title="Jam berjalan", yaxis_title="Skor kesehatan (0-100)",
                yaxis_range=[0, 105], plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)", showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            )
            fig.data[0].update(fill="tozeroy", fillcolor=_rgba(theme.COLORS["accent"], 0.08))
            _style_axes(fig)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        with c2:
            st.markdown("**Skor anomali vs ambang 3&sigma;**")
            threshold = None
            if (ARTIFACTS_DIR / f"{run_key}_bearing{bearing_id}_models.joblib").exists():
                import joblib
                bundle = joblib.load(ARTIFACTS_DIR / f"{run_key}_bearing{bearing_id}_models.joblib")
                threshold = bundle["anomaly_model"].threshold
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=visible["elapsed_hours"], y=visible["anomaly_score"],
                mode="lines", line=dict(color=theme.COLORS["secondary"], width=2), name="Skor anomali",
            ))
            if threshold is not None:
                fig2.add_hline(
                    y=threshold, line_dash="dash", line_color=theme.COLORS["critical"],
                    annotation_text="Ambang 3-sigma", annotation_position="top left",
                )
            fig2.add_vline(x=float(current["elapsed_hours"]), line_color=theme.COLORS["primary"], line_width=1)
            fig2.update_layout(
                height=340, margin=dict(l=10, r=10, t=10, b=10),
                xaxis_title="Jam berjalan", yaxis_title="Skor anomali (lebih tinggi = lebih buruk)",
                plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
            )
            fig2.data[0].update(fill="tozeroy", fillcolor=_rgba(theme.COLORS["secondary"], 0.07))
            _style_axes(fig2)
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    with tab_signal:
        # `filepath` in the artifacts CSV is an absolute path baked in at build
        # time on whichever machine produced it, so it won't resolve here -
        # re-root the filename under this machine's local data directory.
        local_filepath = DATA_ROOT / spec.folder / Path(current["filepath"]).name
        x_sig = load_channel(local_filepath, bearing_id)
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Cuplikan getaran mentah (2000 sampel pertama @ 20 kHz)**")
            snippet = x_sig[:2000]
            t_axis = np.arange(len(snippet)) / FS_HZ * 1000  # ms
            fig3 = go.Figure(go.Scatter(x=t_axis, y=snippet, mode="lines",
                                         line=dict(color=theme.COLORS["accent"], width=1)))
            fig3.update_layout(
                height=340, margin=dict(l=10, r=10, t=10, b=10),
                xaxis_title="Waktu (ms)", yaxis_title="Akselerasi (g)", plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)",
            )
            _style_axes(fig3)
            st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})

        with c2:
            st.markdown("**Spektrum selubung (sidik jari kerusakan bearing)**")
            freqs, spectrum = envelope_spectrum(x_sig, FS_HZ)
            mask = freqs <= 500
            fig4 = go.Figure(go.Scatter(x=freqs[mask], y=spectrum[mask], mode="lines",
                                         line=dict(color=theme.COLORS["primary"], width=1.3)))
            for label, f in FAULT_FREQS.items():
                if f <= 500:
                    fig4.add_vline(x=f, line_dash="dot", line_color=theme.COLORS["critical"],
                                    annotation_text=label, annotation_position="top")
            fig4.update_layout(
                height=340, margin=dict(l=10, r=10, t=10, b=10),
                xaxis_title="Frekuensi (Hz)", yaxis_title="Magnitudo FFT selubung", plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)",
            )
            _style_axes(fig4)
            st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})
        st.caption(
            "BPFO/BPFI/BSF adalah frekuensi kerusakan outer-race, inner-race, dan ball-spin bearing, "
            "dihitung dari geometri Rexnord ZA-2115 (lihat pdm/bearing_physics.py)."
        )

    with tab_sensors:
        if "temperature_c" not in df.columns or "current_a" not in df.columns:
            st.info(
                "Kolom temperature/current tidak ditemukan. Jalankan "
                "`python -m scripts.add_synthetic_sensors` dari direktori root project, lalu muat ulang."
            )
        else:
            specs = {
                "Getaran (RMS)": ("rms", theme.COLORS["accent"], "g"),
                "Suhu": ("temperature_c", theme.COLORS["warning"], "&deg;C"),
                "Arus": ("current_a", theme.COLORS["secondary"], "A"),
            }
            healthy_n = max(3, int(0.05 * n))

            param_choices = st.multiselect(
                "Parameter yang ditampilkan", ["Getaran (RMS)", "Suhu", "Arus"],
                default=["Getaran (RMS)", "Suhu", "Arus"], key="sensor_params",
            )
            chosen = [p for p in ["Getaran (RMS)", "Suhu", "Arus"] if p in param_choices]

            # Status Normal/Meningkat per parameter (vs baseline sehat 3-sigma masing-
            # masing kolom) - dihitung untuk semua parameter (perlu tahu status Getaran
            # walau sedang tidak ditampilkan, untuk kalimat fallback di bawah), tapi
            # kalimat ringkasan HANYA dibangun dari `chosen` (parameter yang sedang aktif
            # di dropdown) supaya selalu sinkron dengan apa yang user pilih/lihat.
            elevated_now = {}
            for name, (col_name, _color, _unit) in specs.items():
                thr_now = _healthy_threshold(df, col_name, healthy_n)
                elevated_now[name] = bool(current[col_name] > thr_now)
            elevated_list = [name for name in chosen if elevated_now[name]]

            if not chosen:
                agreement = None
                agreement_icon = None
            elif not elevated_list:
                agreement = "Semua parameter yang ditampilkan berada dalam rentang normal - konsisten dengan bearing yang sehat."
                agreement_icon = "check-circle"
            elif elevated_list == ["Getaran (RMS)"]:
                agreement = (
                    "Hanya getaran yang meningkat sejauh ini - temperature dan current belum "
                    "mengikuti. Ini konsisten dengan degradasi tahap awal, di mana getaran biasanya "
                    "menjadi sinyal pertama yang bergerak."
                )
                agreement_icon = "activity"
            elif "Getaran (RMS)" in elevated_list and len(elevated_list) > 1:
                others = " dan ".join(name for name in elevated_list if name != "Getaran (RMS)")
                agreement = (
                    f"Getaran DAN {others} meningkat bersamaan sekarang - sinyal yang lebih kuat "
                    "dan saling menguatkan dibanding getaran saja."
                )
                agreement_icon = "alert-triangle"
            else:
                others = " dan ".join(elevated_list)
                agreement = (
                    f"{others} terbaca meningkat" +
                    (
                        ", sementara getaran sendiri masih dalam rentang normal - sebuah "
                        "ketidaksesuaian yang layak diperiksa lebih lanjut."
                        if "Getaran (RMS)" in chosen
                        else " di antara parameter yang sedang ditampilkan."
                    )
                )
                agreement_icon = "alert-triangle"

            if agreement:
                st.markdown(
                    f'<div class="reco-box">{theme.icon(agreement_icon, 16, theme.COLORS["accent"])}'
                    f' &nbsp;{agreement}</div>',
                    unsafe_allow_html=True,
                )
            st.write("")

            if chosen:
                cols = st.columns(len(chosen))
                thresholds = {}
                for col, name in zip(cols, chosen):
                    col_name, color, unit = specs[name]
                    thr = _healthy_threshold(df, col_name, healthy_n)
                    thresholds[name] = thr
                    with col:
                        badge_color = theme.COLORS["warning"] if elevated_now[name] else theme.COLORS["normal"]
                        badge_text = "MENINGKAT" if elevated_now[name] else "NORMAL"
                        st.markdown(
                            f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">'
                            f'<strong>{name} seiring waktu</strong>'
                            f'<span class="status-badge" style="background:{badge_color}1A;color:{badge_color};'
                            f'font-size:0.72rem;padding:3px 12px">{badge_text}</span></div>',
                            unsafe_allow_html=True,
                        )
                        fig5 = go.Figure()
                        fig5.add_trace(go.Scatter(
                            x=visible["elapsed_hours"], y=visible[col_name],
                            mode="lines", line=dict(color=color, width=2), name=name,
                        ))
                        fig5.add_hline(
                            y=thr, line_dash="dash", line_color=theme.COLORS["critical"],
                            annotation_text="3-sigma (baseline sehat)", annotation_position="top left",
                        )
                        fig5.add_vline(x=float(current["elapsed_hours"]), line_color=theme.COLORS["primary"], line_width=1)
                        fig5.update_layout(
                            height=300, margin=dict(l=10, r=10, t=10, b=10),
                            xaxis_title="Jam berjalan", yaxis_title=unit, plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)",
                        )
                        fig5.data[0].update(fill="tozeroy", fillcolor=_rgba(color, 0.08))
                        _style_axes(fig5)
                        st.plotly_chart(fig5, use_container_width=True, config={"displayModeBar": False})

                export_df = visible[["timestamp", "elapsed_hours"]].copy()
                for name in chosen:
                    col_name, _color, _unit = specs[name]
                    export_df[name] = visible[col_name]
                    export_df[f"Status {name}"] = np.where(
                        visible[col_name] > thresholds[name], "Meningkat", "Normal"
                    )
                csv_bytes = export_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Unduh laporan (CSV)",
                    data=csv_bytes,
                    file_name=f"{run_key}_bearing{bearing_id}_sensor.csv",
                    mime="text/csv",
                )
            else:
                st.info("Pilih minimal satu parameter di atas untuk menampilkan trennya.")

    with tab_alerts:
        level = current["alarm_level"]
        color = theme.STATUS_COLOR[level]
        badge_cls = "status-badge pulse" if level == "CRITICAL" else "status-badge"

        st.markdown(
            f'<div class="{badge_cls}" style="background:{color}1A;color:{color};font-size:1.1rem">'
            f'{theme.icon_for_status(level, 22)} {theme.STATUS_LABEL[level]}</div>',
            unsafe_allow_html=True,
        )
        st.write("")
        st.markdown(f"**Alasan:** {current['alarm_reason']}")

        if level != "NORMAL" and bearing_id == spec.failing_bearing:
            root_cause = (
                "Cacat outer-race bearing (energi selubung dominan BPFO) - konsisten dengan mode "
                f"kegagalan yang terdokumentasi untuk run ini ({spec.failure_mode.replace('_', ' ')})."
            )
        elif level != "NORMAL":
            root_cause = "Deviasi multi-parameter yang meningkat - periksa pembacaan getaran dan current."
        else:
            root_cause = "Tidak terdeteksi sidik jari kerusakan yang dominan."
        st.markdown(f"**Kemungkinan penyebab utama:** {root_cause}")

        st.write("")
        if level == "CRITICAL":
            if current["rul_status"] == "estimated" and not np.isnan(current["rul_hours"]):
                reco = (
                    f"Jadwalkan penggantian bearing dalam {fmt_duration(float(current['rul_hours']))} ke depan. "
                    "Eskalasi ke tim perencanaan pemeliharaan sekarang; hindari menjalankan mesin sampai gagal total."
                )
            else:
                reco = "Eskalasi ke tim perencanaan pemeliharaan segera; Sisa Umur Pakai belum cukup stabil untuk dijadwalkan secara presisi."
        elif level == "WARNING":
            reco = "Tingkatkan frekuensi pemantauan dan rencanakan inspeksi pada jendela pemeliharaan berikutnya."
        else:
            reco = "Tidak ada tindakan yang diperlukan. Lanjutkan pemantauan rutin."
        st.markdown(f'<div class="reco-box">{theme.icon("tool", 16, theme.COLORS["accent"])} &nbsp;{reco}</div>',
                    unsafe_allow_html=True)

    st.write("")
    st.caption(
        "Metodologi: Isolation Forest (dilatih hanya pada data sehat, ambang 3-sigma) "
        "+ Health Index PCA + fit eksponensial Sisa Umur Pakai, dipicu pada alarm pertama yang "
        "terkonfirmasi persistence/voting atas getaran, temperature, dan current - logika "
        "persistence & voting diskalakan sesuai panjang run. "
        "Lihat docs/Proposal_Final_Case2.docx untuk hasil validasi lengkap."
    )

    # ----------------------------------------------------------------------
    # Auto-play loop - the actual position advance happens at the TOP of this
    # function (before the slider widget is created); this just paces reruns.
    # ----------------------------------------------------------------------
    if st.session_state.playing and position < n - 1:
        speed_map = {"1x": 0.6, "4x": 0.25, "16x": 0.08, "64x": 0.02}
        time.sleep(speed_map[speed])
        st.rerun()


# ----------------------------------------------------------------------
# Live Simulation page (dosen feedback poin #1: demo the system genuinely
# ingesting new data + retraining continuously, not just replaying a frozen
# historical run). Fed by scripts/run_live_simulation.py, which runs as its
# own standalone process (separate from this Streamlit process) and keeps
# overwriting artifacts/live_bearing.csv - this page just reads that file.
# ----------------------------------------------------------------------
LIVE_ARTIFACT_PATH = ARTIFACTS_DIR / "live_bearing.csv"


def load_live_bearing_df() -> pd.DataFrame:
    @st.cache_data(ttl=3, show_spinner=False)
    def _load(_mtime: float) -> pd.DataFrame:
        return pd.read_csv(LIVE_ARTIFACT_PATH, parse_dates=["timestamp"])
    return _load(LIVE_ARTIFACT_PATH.stat().st_mtime)


def render_live_page() -> None:
    st.markdown(
        f'<div class="astra-topbar"><div style="display:flex;align-items:center;gap:12px">'
        f'{_logo_chip()}<div>'
        f'<div class="title">Live Simulation &mdash; Demo Ingest &amp; Retrain</div>'
        f'<div class="subtitle">PT Astra Otoparts Tbk &middot; WINTEQ &middot; Prototipe Case 2</div>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    if not LIVE_ARTIFACT_PATH.exists():
        st.info(
            "Mode Live Simulation belum aktif. Jalankan `python -m scripts.run_live_simulation` "
            "di terminal terpisah (dari direktori root project), lalu muat ulang halaman ini."
        )
        return

    df = load_live_bearing_df()
    n = len(df)
    current = df.iloc[-1]

    top_col1, top_col2 = st.columns([3, 1])
    with top_col1:
        st.markdown(
            f'<span class="status-badge pulse" style="background:{theme.COLORS["critical"]}1A;'
            f'color:{theme.COLORS["critical"]}">&#9679; LIVE</span>'
            f'<span style="margin-left:12px;color:{theme.COLORS["text_muted"]};font-weight:600;font-size:0.95rem">'
            f'Terakhir diperbarui {pd.Timestamp.now().strftime("%H:%M:%S")} &middot; {n} snapshot'
            f'</span>',
            unsafe_allow_html=True,
        )
    with top_col2:
        auto = st.checkbox("Auto-refresh", value=False, key="live_autorefresh")
        st.button("Refresh sekarang", use_container_width=True, key="live_refresh_btn")

    st.caption(
        "Mode simulasi: data baru terus digenerate dan model (Isolation Forest + PCA Health Index) "
        "di-retrain otomatis di latar belakang setiap siklus - mendemonstrasikan bagaimana sistem "
        "akan bekerja saat menerima data sensor sungguhan dari Astra secara live. Ini bukan klaim "
        "bahwa angka di bawah berasal dari sensor sungguhan."
    )

    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1:
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=float(current["health_score"]),
            number={"font": {"size": 32, "color": theme.COLORS["primary"], "family": "JetBrains Mono, monospace"}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": theme.COLORS["border"]},
                "bar": {"color": theme.COLORS["accent"], "thickness": 0.75},
                "bgcolor": "#FBFCFF",
                "bordercolor": theme.COLORS["border"],
                "steps": [
                    {"range": [0, 40], "color": "#FEE2E2"},
                    {"range": [40, 70], "color": "#FEF3C7"},
                    {"range": [70, 100], "color": "#DCFCE7"},
                ],
            },
            domain={"x": [0, 1], "y": [0, 1]},
        ))
        fig.update_layout(height=170, margin=dict(l=20, r=20, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)")
        st.markdown(
            f'<div class="kpi-label">{theme.icon("activity", 14, theme.COLORS["text_muted"])} SKOR KESEHATAN</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with kpi2:
        level = current["alarm_level"]
        color = theme.STATUS_COLOR[level]
        badge_cls = "status-badge pulse" if level == "CRITICAL" else "status-badge"
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{theme.icon("alert-triangle", 14, theme.COLORS["text_muted"])} STATUS ALARM</div>'
            f'<div class="{badge_cls}" style="background:{color}1A;color:{color}">'
            f'{theme.icon_for_status(level, 18)} {theme.STATUS_LABEL[level]}</div>'
            f'<div class="kpi-sub">{current["alarm_reason"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with kpi3:
        if current["rul_status"] == "estimated" and not pd.isna(current["rul_hours"]):
            rul_val = fmt_duration(float(current["rul_hours"]))
            sub = "Estimasi Sisa Umur Pakai"
        else:
            rul_val = "Pemantauan"
            sub = "Belum stabil - tren degradasi masih terbentuk"
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{theme.icon("clock", 14, theme.COLORS["text_muted"])} SISA UMUR PAKAI</div>'
            f'<div class="kpi-value">{rul_val}</div>'
            f'<div class="kpi-sub">{sub}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown("**Skor Kesehatan seiring waktu (live)**")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=df["elapsed_hours"], y=df["health_score"], mode="lines",
        line=dict(color=theme.COLORS["accent"], width=2), name="Skor kesehatan",
    ))
    seed_end = int((~df["is_synthetic_snapshot"]).sum())
    if 0 < seed_end < n:
        fig2.add_vline(
            x=float(df["elapsed_hours"].iloc[seed_end - 1]), line_dash="dot",
            line_color=theme.COLORS["text_muted"],
            annotation_text="Data historis berakhir / mulai simulasi live",
            annotation_position="top",
        )
    alarm_mask = df["is_alarm"]
    if alarm_mask.any():
        fig2.add_trace(go.Scatter(
            x=df.loc[alarm_mask, "elapsed_hours"], y=df.loc[alarm_mask, "health_score"],
            mode="markers", marker=dict(color=theme.COLORS["critical"], size=4), name="Alarm aktif",
        ))
    fig2.update_layout(
        height=340, margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Jam berjalan", yaxis_title="Skor kesehatan (0-100)", yaxis_range=[0, 105],
        plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)", showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig2.data[0].update(fill="tozeroy", fillcolor=_rgba(theme.COLORS["accent"], 0.08))
    _style_axes(fig2)
    st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    if bool(current["is_synthetic_snapshot"]):
        st.info(
            "Snapshot ini adalah hasil simulasi (melanjutkan tren degradasi setelah data historis "
            "asli berakhir) - sinyal getaran mentah tidak tersedia untuk snapshot simulasi."
        )

    if auto:
        time.sleep(4)
        st.rerun()


# ----------------------------------------------------------------------
# Top-level navigation
# ----------------------------------------------------------------------
st.sidebar.markdown(
    f'<div style="margin-bottom:16px">'
    f'{theme.astra_logo_img(30)}'
    f'<div style="font-size:0.78rem;color:{theme.COLORS["text_muted"]};letter-spacing:0.05em;'
    f'text-transform:uppercase;margin-top:6px;font-weight:700">Pemeliharaan Prediktif &middot; Case 2</div>'
    f'</div>',
    unsafe_allow_html=True,
)
if st.session_state.get("_nav_page_override"):
    st.session_state["nav_page"] = st.session_state.pop("_nav_page_override")

page = st.sidebar.radio("Tampilan", ["Ringkasan Armada", "Detail Mesin", "Live Simulation"], key="nav_page")
st.sidebar.markdown("---")

if page == "Ringkasan Armada":
    render_overview_page()
elif page == "Detail Mesin":
    render_detail_page()
else:
    render_live_page()
