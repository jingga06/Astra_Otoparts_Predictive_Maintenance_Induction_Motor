"""Predictive Maintenance dashboard - PT Astra Otoparts Tbk / WINTEQ, Case 2.

Run with:  streamlit run app/dashboard.py   (from the src/ directory)

Replays cached NASA IMS Bearing pipeline output (see scripts/build_artifacts.py)
snapshot-by-snapshot to show health score, alarm status and RUL behaviour as
a machine degrades. Two views:

  - Fleet Overview: a manager-facing, all-machines-at-once command center -
    the landing page - so a reviewer never has to hunt through a sidebar to
    find which of several machines needs attention right now.
  - Machine Detail: the original single-machine replay (health gauge, trend,
    signal detail, alerts/recommendation) - unchanged from the earlier
    single-page version, just moved into its own function.

Temperature and current are synthetic (see pdm/synthetic_sensors.py) - the
NASA IMS dataset only records vibration - and are disclosed as such wherever
shown.
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
from pdm.data_loader import RUN_SPECS, FS_HZ, load_channel  # noqa: E402
from pdm.features import envelope_spectrum  # noqa: E402

ARTIFACTS_DIR = SRC_ROOT / "artifacts"
FAULT_FREQS = fault_frequencies()

st.set_page_config(
    page_title="Astra Otoparts - Predictive Maintenance",
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
        return f"{days}d {rem_h:.0f}h"
    return f"{hours:.1f}h"


def bearing_label(spec, bearing_id: int, mark_failing: bool = True) -> str:
    tag = " (monitored - known failure)" if mark_failing and bearing_id == spec.failing_bearing else ""
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
        f'<div class="title">Predictive Maintenance &mdash; Induction Motor</div>'
        f'<div class="subtitle">PT Astra Otoparts Tbk &middot; WINTEQ &middot; Case 2 Prototype</div>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )
    st.warning(
        "No precomputed artifacts found yet. Run "
        "`python -m scripts.build_artifacts --all` from the `src/` directory first, "
        "then reload this page."
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
        names += f"; and {len(rest)} more critical machine{'s' if len(rest) > 1 else ''}"
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
            {theme.icon("alert-octagon", 20, "white")}&nbsp; CRITICAL ALERT &mdash; {names}
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
            "Acknowledge & continue monitoring",
            key=f"ack_{context_key}",
            use_container_width=True,
            type="primary",
        ):
            st.session_state["_ack_marker"] = marker
            st.rerun()
    st.caption(
        "If no sound is playing, click anywhere on the page once - browsers block "
        "autoplay audio until the first user interaction."
    )
    return True


# ----------------------------------------------------------------------
# Fleet Overview page
# ----------------------------------------------------------------------
@st.dialog("Quick view")
def render_quick_view_dialog(item: dict) -> None:
    """A floating preview so a manager can glance at one machine's trend
    without leaving Fleet Overview - opens on top of the page, closes back
    to the same overview state, only navigates to Machine Detail if asked."""
    row = item["row"]
    run_key, bearing_id, spec = item["run_key"], item["bearing_id"], item["spec"]
    level = row["alarm_level"]
    color = theme.STATUS_COLOR[level]

    st.markdown(f"#### {item['label']}")
    st.caption(f"{spec.label} · t = {row['elapsed_hours']:.1f}h")
    badge_cls = "status-badge pulse" if level == "CRITICAL" else "status-badge"
    st.markdown(
        f'<div class="{badge_cls}" style="background:{color}1A;color:{color}">'
        f'{theme.icon_for_status(level, 16)} {theme.STATUS_LABEL[level]}</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    m1, m2, m3 = st.columns(3)
    m1.metric("Health score", f"{row['health_score']:.0f}/100")
    if row["rul_status"] == "estimated" and not pd.isna(row["rul_hours"]):
        m2.metric("RUL", fmt_duration(float(row["rul_hours"])))
    else:
        m2.metric("RUL", "Monitoring")
    m3.metric("Vibration RMS", f"{row['rms']:.3f} g")

    df = load_bearing_df(run_key, bearing_id)
    visible = df.iloc[: item["idx"] + 1]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=visible["elapsed_hours"], y=visible["health_score"],
        mode="lines", line=dict(color=theme.COLORS["accent"], width=2), name="Health score",
    ))
    alarm_mask = visible["is_alarm"]
    if alarm_mask.any():
        fig.add_trace(go.Scatter(
            x=visible.loc[alarm_mask, "elapsed_hours"], y=visible.loc[alarm_mask, "health_score"],
            mode="markers", marker=dict(color=theme.COLORS["critical"], size=4), name="Alarm active",
        ))
    fig.update_layout(
        height=220, margin=dict(l=10, r=10, t=25, b=10),
        xaxis_title="Elapsed hours", yaxis_title="Health score", yaxis_range=[0, 105],
        plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
        title=dict(text="Health score trend so far", font=dict(size=12)),
    )
    fig.data[0].update(fill="tozeroy", fillcolor=_rgba(theme.COLORS["accent"], 0.08))
    _style_axes(fig)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown(f"**Reason:** {row['alarm_reason']}")

    st.write("")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Open full detail", key=f"qv_open_{run_key}_{bearing_id}",
                      type="primary", use_container_width=True):
            st.session_state["nav_run_key"] = run_key
            st.session_state["nav_bearing_id"] = bearing_id
            st.session_state["_nav_page_override"] = "Machine Detail"
            st.rerun()
    with b2:
        if st.button("Close", key=f"qv_close_{run_key}_{bearing_id}", use_container_width=True):
            st.rerun()


def render_machine_card(item: dict, param_focus: str) -> None:
    row = item["row"]
    level = row["alarm_level"]
    color = theme.STATUS_COLOR[level]

    if level == "CRITICAL" and row["rul_status"] == "estimated" and not pd.isna(row["rul_hours"]):
        rul_line = f"Critical in {fmt_duration(float(row['rul_hours']))}"
    elif level == "CRITICAL":
        rul_line = "Critical — RUL not stable yet"
    elif row["rul_status"] == "estimated" and not pd.isna(row["rul_hours"]):
        rul_line = f"RUL {fmt_duration(float(row['rul_hours']))}"
    else:
        rul_line = "Monitoring"

    extra = ""
    if param_focus in ("All parameters", "Vibration"):
        extra += f'<div class="kpi-sub metric-mono">Vibration RMS: {row["rms"]:.3f} g</div>'
    if param_focus in ("All parameters", "Temperature") and "temperature_c" in row.index:
        extra += f'<div class="kpi-sub metric-mono">Temperature: {row["temperature_c"]:.1f} &deg;C</div>'
    if param_focus in ("All parameters", "Current") and "current_a" in row.index:
        extra += f'<div class="kpi-sub metric-mono">Current: {row["current_a"]:.2f} A</div>'

    badge_cls = "status-badge pulse" if level == "CRITICAL" else "status-badge"
    st.markdown(
        f"""
        <div class="kpi-card" style="border-top:4px solid {color}">
            <div class="kpi-label">{item['label']}</div>
            <div class="{badge_cls}" style="background:{color}1A;color:{color};margin:6px 0">
                {theme.icon_for_status(level, 16)} {theme.STATUS_LABEL[level]}
            </div>
            <div class="kpi-value" style="font-size:1.4rem">{row['health_score']:.0f}
                <span style="font-size:0.75rem;color:{theme.COLORS['text_muted']}">/100 health</span></div>
            <div class="kpi-sub" style="font-weight:600;color:{theme.COLORS['primary']}">{rul_line}</div>
            {extra}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Quick view", key=f"card_{item['run_key']}_{item['bearing_id']}", use_container_width=True):
        render_quick_view_dialog(item)


def render_overview_page() -> None:
    st.markdown(
        f'<div class="astra-topbar"><div style="display:flex;align-items:center;gap:12px">'
        f'{_logo_chip()}<div>'
        f'<div class="title">Fleet Overview &mdash; All Machines</div>'
        f'<div class="subtitle">PT Astra Otoparts Tbk &middot; WINTEQ &middot; Case 2 Prototype</div>'
        f'</div></div>'
        f'<div style="text-align:right;font-size:0.82rem;opacity:0.9">'
        f'8 bearings monitored &middot; 2 production runs</div></div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([2.2, 1])
    with c1:
        pct = st.slider(
            "Fleet time — % elapsed through each machine's monitored run",
            0, 100, value=st.session_state.get("fleet_pct", 78), key="fleet_pct",
            help="All 8 bearings are historical replay data, not live streams - this scrubs "
                 "every machine to the same relative point in its own run, so the whole fleet "
                 "advances together like a live command center.",
        )
    with c2:
        param_focus = st.selectbox(
            "Parameter focus", ["All parameters", "Vibration", "Temperature", "Current"],
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
            reason = f"failure expected in {fmt_duration(float(row['rul_hours']))}"
        else:
            reason = row["alarm_reason"]
        banner_items.append({"label": it["label"], "reason": reason})
    render_critical_banner(banner_items, context_key="overview")

    n_crit = len(critical_items)
    n_warn = sum(1 for it in items if it["row"]["alarm_level"] == "WARNING")
    n_norm = sum(1 for it in items if it["row"]["alarm_level"] == "NORMAL")

    k1, k2, k3, k4 = st.columns(4)
    for col, label, value, color in (
        (k1, "Machines monitored", str(len(items)), theme.COLORS["primary"]),
        (k2, "Critical", str(n_crit), theme.COLORS["critical"]),
        (k3, "Warning", str(n_warn), theme.COLORS["warning"]),
        (k4, "Normal", str(n_norm), theme.COLORS["normal"]),
    ):
        with col:
            st.markdown(
                f'<div class="kpi-card"><div class="fleet-kpi-label">{label}</div>'
                f'<div class="fleet-kpi-value" style="color:{color}">{value}</div></div>',
                unsafe_allow_html=True,
            )

    st.write("")
    st.markdown("#### Needs attention")
    attention = [it for it in items if it["row"]["alarm_level"] != "NORMAL"]
    if not attention:
        st.success("No machines currently in Warning or Critical state at this fleet time.")
    else:
        for it in attention:
            row = it["row"]
            level = row["alarm_level"]
            color = theme.STATUS_COLOR[level]
            if level == "CRITICAL" and row["rul_status"] == "estimated" and not pd.isna(row["rul_hours"]):
                detail = f"Critical → failure expected in {fmt_duration(float(row['rul_hours']))}"
            elif level == "CRITICAL":
                detail = "Critical → escalate immediately, RUL not yet stable"
            else:
                detail = "Warning → schedule inspection this maintenance window"
            row_col1, row_col2 = st.columns([6, 1])
            with row_col1:
                st.markdown(
                    f'<div class="attention-row" style="border-left-color:{color}">'
                    f'<b>{it["label"]}</b> &middot; {it["spec"].label} &nbsp;&mdash;&nbsp; {detail}</div>',
                    unsafe_allow_html=True,
                )
            with row_col2:
                if st.button("Open", key=f"open_{it['run_key']}_{it['bearing_id']}", use_container_width=True):
                    st.session_state["nav_run_key"] = it["run_key"]
                    st.session_state["nav_bearing_id"] = it["bearing_id"]
                    st.session_state["_nav_page_override"] = "Machine Detail"
                    st.rerun()

    st.write("")
    st.markdown("#### All machines")
    only_alerts = st.checkbox("Show only Warning / Critical machines", value=False, key="fleet_only_alerts")

    for run_key, spec in RUN_SPECS.items():
        st.markdown(f"**{spec.label}**")
        group = [it for it in items if it["run_key"] == run_key]
        if only_alerts:
            group = [it for it in group if it["row"]["alarm_level"] != "NORMAL"]
        group.sort(key=lambda it: it["bearing_id"])
        if not group:
            st.caption("All bearings normal in this run at the current fleet time.")
            continue
        cols = st.columns(len(group))
        for col, it in zip(cols, group):
            with col:
                render_machine_card(it, param_focus)
        st.write("")

    st.caption(
        "Temperature and current shown above are synthetic (NASA IMS only records vibration) - "
        "derived from each bearing's own vibration-based health index, not random noise. See the "
        "Sensors tab in Machine Detail for the full trend and methodology note."
    )


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
        f'<b style="font-family:Lexend,sans-serif;color:{theme.COLORS["primary"]}">Replay Controls</b></div>',
        unsafe_allow_html=True,
    )

    run_options = list(RUN_SPECS.keys())
    run_key = st.sidebar.selectbox(
        "Production run", options=run_options,
        format_func=lambda k: RUN_SPECS[k].label, key="detail_run_key",
    )
    spec = RUN_SPECS[run_key]

    bearing_options = list(range(1, spec.n_bearings + 1))
    bearing_id = st.sidebar.selectbox(
        "Machine / bearing", options=bearing_options,
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

    position = st.sidebar.slider("Snapshot position", 0, n - 1, key="pos_slider")

    play_col1, play_col2 = st.sidebar.columns(2)
    if play_col1.button(("Pause" if st.session_state.playing else "Play"), use_container_width=True):
        st.session_state.playing = not st.session_state.playing
        st.rerun()
    if play_col2.button("Reset", use_container_width=True):
        st.session_state._reset_requested = True
        st.rerun()
    speed = st.sidebar.select_slider("Playback speed", options=["1x", "4x", "16x", "64x"],
                                      value=speed, key="_speed")

    st.sidebar.markdown(
        f'<div class="data-source-caption">{theme.icon("database", size=14, color=theme.COLORS["text_muted"])}'
        f' NASA IMS Bearing Dataset (run-to-failure) &middot; Rexnord ZA-2115 &middot; 2000 RPM'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.caption(
        f"Run span: {df['elapsed_hours'].iloc[-1]:.1f} hours across {n} snapshots "
        f"(one snapshot every 10 minutes)."
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
                f"{bearing_label(spec, bearing_id)} escalated to {theme.STATUS_LABEL[curr_level]} "
                f"- {current['alarm_reason']}",
                icon=toast_icon,
            )
        st.session_state["_last_toast_marker"] = _toast_marker

    # Big, hard-to-miss overlay - stays up (with looping alarm tone) until acknowledged.
    if current["alarm_level"] == "CRITICAL":
        if current["rul_status"] == "estimated" and not np.isnan(current["rul_hours"]):
            reason = f"failure expected in {fmt_duration(float(current['rul_hours']))}"
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
        f'<div class="title">Predictive Maintenance &mdash; Induction Motor</div>'
        f'<div class="subtitle">PT Astra Otoparts Tbk &middot; WINTEQ &middot; Case 2 Prototype</div>'
        f'</div></div>'
        f'<div style="text-align:right;font-size:0.82rem;opacity:0.9">'
        f'{bearing_label(spec, bearing_id)}<br>{spec.label} &middot; t = {current["elapsed_hours"]:.1f}h'
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
            f'<div class="kpi-label">{theme.icon("activity", 14, theme.COLORS["text_muted"])} HEALTH SCORE</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with kpi2:
        level = current["alarm_level"]
        color = theme.STATUS_COLOR[level]
        badge_cls = "status-badge pulse" if level == "CRITICAL" else "status-badge"
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{theme.icon("alert-triangle", 14, theme.COLORS["text_muted"])} ALARM STATUS</div>'
            f'<div class="{badge_cls}" style="background:{color}1A;color:{color}">'
            f'{theme.icon_for_status(level, 18)} {theme.STATUS_LABEL[level]}</div>'
            f'<div class="kpi-sub">{current["alarm_reason"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with kpi3:
        if current["rul_status"] == "estimated" and not np.isnan(current["rul_hours"]):
            rul_val = fmt_duration(float(current["rul_hours"]))
            sub = "Estimated Remaining Useful Life"
        else:
            rul_val = "Monitoring"
            sub = "Not stable yet - degradation trend still forming"
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{theme.icon("clock", 14, theme.COLORS["text_muted"])} REMAINING USEFUL LIFE</div>'
            f'<div class="kpi-value">{rul_val}</div>'
            f'<div class="kpi-sub">{sub}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.write("")

    # ----------------------------------------------------------------------
    # Tabs
    # ----------------------------------------------------------------------
    tab_trend, tab_signal, tab_sensors, tab_alerts = st.tabs(
        ["Trend", "Signal Detail", "Sensors", "Alerts & Recommendation"]
    )

    with tab_trend:
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Health Score over time**")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=visible["elapsed_hours"], y=visible["health_score"],
                mode="lines", line=dict(color=theme.COLORS["accent"], width=2), name="Health score",
            ))
            if "health_score_fitted" in visible.columns and visible["health_score_fitted"].notna().any():
                fig.add_trace(go.Scatter(
                    x=visible["elapsed_hours"], y=visible["health_score_fitted"],
                    mode="lines", line=dict(color=theme.COLORS["warning"], width=2, dash="dash"),
                    name="Predicted trajectory",
                ))
            alarm_mask = visible["is_alarm"]
            if alarm_mask.any():
                fig.add_trace(go.Scatter(
                    x=visible.loc[alarm_mask, "elapsed_hours"], y=visible.loc[alarm_mask, "health_score"],
                    mode="markers", marker=dict(color=theme.COLORS["critical"], size=5),
                    name="Alarm active",
                ))
            if len(alarm_idx) and alarm_idx[0] <= position:
                fig.add_vline(
                    x=float(df["elapsed_hours"].iloc[alarm_idx[0]]),
                    line_dash="dash", line_color=theme.COLORS["warning"],
                    annotation_text="Trigger / RUL start", annotation_position="top",
                )
            fig.add_vline(x=float(current["elapsed_hours"]), line_color=theme.COLORS["primary"], line_width=1)
            fig.update_layout(
                height=340, margin=dict(l=10, r=10, t=10, b=10),
                xaxis_title="Elapsed hours", yaxis_title="Health score (0-100)",
                yaxis_range=[0, 105], plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)", showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            )
            fig.data[0].update(fill="tozeroy", fillcolor=_rgba(theme.COLORS["accent"], 0.08))
            _style_axes(fig)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        with c2:
            st.markdown("**Anomaly score vs 3&sigma; threshold**")
            threshold = None
            if (ARTIFACTS_DIR / f"{run_key}_bearing{bearing_id}_models.joblib").exists():
                import joblib
                bundle = joblib.load(ARTIFACTS_DIR / f"{run_key}_bearing{bearing_id}_models.joblib")
                threshold = bundle["anomaly_model"].threshold
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=visible["elapsed_hours"], y=visible["anomaly_score"],
                mode="lines", line=dict(color=theme.COLORS["secondary"], width=2), name="Anomaly score",
            ))
            if threshold is not None:
                fig2.add_hline(
                    y=threshold, line_dash="dash", line_color=theme.COLORS["critical"],
                    annotation_text="3-sigma threshold", annotation_position="top left",
                )
            fig2.add_vline(x=float(current["elapsed_hours"]), line_color=theme.COLORS["primary"], line_width=1)
            fig2.update_layout(
                height=340, margin=dict(l=10, r=10, t=10, b=10),
                xaxis_title="Elapsed hours", yaxis_title="Anomaly score (higher = worse)",
                plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
            )
            fig2.data[0].update(fill="tozeroy", fillcolor=_rgba(theme.COLORS["secondary"], 0.07))
            _style_axes(fig2)
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    with tab_signal:
        x_sig = load_channel(current["filepath"], bearing_id)
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Raw vibration snapshot (first 2000 samples @ 20 kHz)**")
            snippet = x_sig[:2000]
            t_axis = np.arange(len(snippet)) / FS_HZ * 1000  # ms
            fig3 = go.Figure(go.Scatter(x=t_axis, y=snippet, mode="lines",
                                         line=dict(color=theme.COLORS["accent"], width=1)))
            fig3.update_layout(
                height=340, margin=dict(l=10, r=10, t=10, b=10),
                xaxis_title="Time (ms)", yaxis_title="Acceleration (g)", plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)",
            )
            _style_axes(fig3)
            st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})

        with c2:
            st.markdown("**Envelope spectrum (bearing fault fingerprint)**")
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
                xaxis_title="Frequency (Hz)", yaxis_title="Envelope FFT magnitude", plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)",
            )
            _style_axes(fig4)
            st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})
        st.caption(
            "BPFO/BPFI/BSF are the bearing's outer-race, inner-race and ball-spin fault "
            "frequencies, computed from Rexnord ZA-2115 geometry (see pdm/bearing_physics.py)."
        )

    with tab_sensors:
        if "temperature_c" not in df.columns or "current_a" not in df.columns:
            st.info(
                "Temperature/current columns not found. Run "
                "`python -m scripts.add_synthetic_sensors` from the `src/` directory, then reload."
            )
        else:
            st.caption(
                "Temperature and current are synthetic - the NASA IMS dataset only records vibration. "
                "Both are derived from this bearing's own vibration-based health index (a slower thermal/"
                "electrical response and lower gain than vibration, matching how heat and load current "
                "actually build up as bearing friction increases), not independent random noise. They "
                "stand in for real Astra plant sensors until multi-parameter data is available - see "
                "pdm/synthetic_sensors.py."
            )
            healthy_n = max(3, int(0.05 * n))
            specs = {
                "Vibration (RMS)": ("rms", theme.COLORS["accent"], "g"),
                "Temperature": ("temperature_c", theme.COLORS["warning"], "&deg;C"),
                "Current": ("current_a", theme.COLORS["secondary"], "A"),
            }

            # Per-parameter Normal/Elevated read (vs. each column's own healthy
            # 3-sigma baseline) - computed on ALL 3 regardless of the display
            # filter below, so the agreement summary is always complete even
            # if the charts themselves are filtered down to 1-2 parameters.
            elevated_now = {}
            for name, (col_name, _color, _unit) in specs.items():
                thr_now = _healthy_threshold(df, col_name, healthy_n)
                elevated_now[name] = bool(current[col_name] > thr_now)
            elevated_list = [n for n, up in elevated_now.items() if up]

            if not elevated_list:
                agreement = "All three parameters are within their normal range - consistent with a healthy bearing."
                agreement_icon = "check-circle"
            elif elevated_list == ["Vibration (RMS)"]:
                agreement = (
                    "Only vibration is elevated so far - temperature and current have not followed yet. "
                    "That is consistent with early-stage degradation, where vibration is usually the "
                    "first signal to move."
                )
                agreement_icon = "activity"
            elif "Vibration (RMS)" in elevated_list and len(elevated_list) > 1:
                others = " and ".join(n for n in elevated_list if n != "Vibration (RMS)")
                agreement = (
                    f"Vibration AND {others} are elevated together right now - a stronger, corroborating "
                    "signal than vibration alone (though remember temperature/current here are synthetic, "
                    "not independently measured - see the note above)."
                )
                agreement_icon = "alert-triangle"
            else:
                others = " and ".join(elevated_list)
                agreement = (
                    f"{others} read elevated while vibration itself is still within range - "
                    "an inconsistency worth a closer look, but temperature/current are synthetic "
                    "display-only signals here, not part of the actual alarm logic."
                )
                agreement_icon = "alert-triangle"

            st.markdown(
                f'<div class="reco-box">{theme.icon(agreement_icon, 16, theme.COLORS["accent"])}'
                f' &nbsp;{agreement}</div>',
                unsafe_allow_html=True,
            )
            st.write("")

            param_choices = st.multiselect(
                "Parameters to display", ["Vibration (RMS)", "Temperature", "Current"],
                default=["Vibration (RMS)", "Temperature", "Current"], key="sensor_params",
            )
            chosen = [p for p in ["Vibration (RMS)", "Temperature", "Current"] if p in param_choices]
            if chosen:
                cols = st.columns(len(chosen))
                for col, name in zip(cols, chosen):
                    col_name, color, unit = specs[name]
                    with col:
                        badge_color = theme.COLORS["warning"] if elevated_now[name] else theme.COLORS["normal"]
                        badge_text = "ELEVATED" if elevated_now[name] else "NORMAL"
                        st.markdown(
                            f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">'
                            f'<strong>{name} over time</strong>'
                            f'<span class="status-badge" style="background:{badge_color}1A;color:{badge_color};'
                            f'font-size:0.68rem;padding:2px 10px">{badge_text}</span></div>',
                            unsafe_allow_html=True,
                        )
                        thr = _healthy_threshold(df, col_name, healthy_n)
                        fig5 = go.Figure()
                        fig5.add_trace(go.Scatter(
                            x=visible["elapsed_hours"], y=visible[col_name],
                            mode="lines", line=dict(color=color, width=2), name=name,
                        ))
                        fig5.add_hline(
                            y=thr, line_dash="dash", line_color=theme.COLORS["critical"],
                            annotation_text="3-sigma (healthy baseline)", annotation_position="top left",
                        )
                        fig5.add_vline(x=float(current["elapsed_hours"]), line_color=theme.COLORS["primary"], line_width=1)
                        fig5.update_layout(
                            height=300, margin=dict(l=10, r=10, t=10, b=10),
                            xaxis_title="Elapsed hours", yaxis_title=unit, plot_bgcolor="#FBFCFF", paper_bgcolor="rgba(0,0,0,0)",
                        )
                        fig5.data[0].update(fill="tozeroy", fillcolor=_rgba(color, 0.08))
                        _style_axes(fig5)
                        st.plotly_chart(fig5, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Select at least one parameter above to plot its trend.")

    with tab_alerts:
        level = current["alarm_level"]
        color = theme.STATUS_COLOR[level]
        badge_cls = "status-badge pulse" if level == "CRITICAL" else "status-badge"

        st.markdown(
            f'<div class="{badge_cls}" style="background:{color}1A;color:{color};font-size:1.05rem">'
            f'{theme.icon_for_status(level, 22)} {theme.STATUS_LABEL[level]}</div>',
            unsafe_allow_html=True,
        )
        st.write("")
        st.markdown(f"**Reason:** {current['alarm_reason']}")

        if level != "NORMAL" and bearing_id == spec.failing_bearing:
            root_cause = (
                "Bearing outer-race defect (BPFO-dominant envelope energy) - consistent with "
                f"this run's documented failure mode ({spec.failure_mode.replace('_', ' ')})."
            )
        elif level != "NORMAL":
            root_cause = "Elevated multi-parameter deviation - inspect vibration and current readings."
        else:
            root_cause = "No dominant fault signature detected."
        st.markdown(f"**Likely root cause:** {root_cause}")

        st.write("")
        if level == "CRITICAL":
            if current["rul_status"] == "estimated" and not np.isnan(current["rul_hours"]):
                reco = (
                    f"Schedule bearing replacement within the next {fmt_duration(float(current['rul_hours']))}. "
                    "Escalate to maintenance planning now; avoid running to failure."
                )
            else:
                reco = "Escalate to maintenance planning immediately; RUL not yet stable enough to schedule precisely."
        elif level == "WARNING":
            reco = "Increase monitoring frequency and plan an inspection during the next maintenance window."
        else:
            reco = "No action required. Continue routine monitoring."
        st.markdown(f'<div class="reco-box">{theme.icon("tool", 16, theme.COLORS["accent"])} &nbsp;{reco}</div>',
                    unsafe_allow_html=True)

    st.write("")
    st.caption(
        "Methodology: Isolation Forest (trained on healthy data only, 3-sigma threshold) "
        "+ PCA Health Index + exponential RUL fit, triggered at the first persistence/voting-"
        "confirmed alarm + persistence & voting alarm logic scaled to run length. "
        "See docs/Proposal_Final_Case2.docx for full validation results."
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
# Top-level navigation
# ----------------------------------------------------------------------
st.sidebar.markdown(
    f'<div style="margin-bottom:16px">'
    f'{theme.astra_logo_img(30)}'
    f'<div style="font-size:0.7rem;color:{theme.COLORS["text_muted"]};letter-spacing:0.06em;'
    f'text-transform:uppercase;margin-top:6px;font-weight:600">Predictive Maintenance &middot; Case 2</div>'
    f'</div>',
    unsafe_allow_html=True,
)
if st.session_state.get("_nav_page_override"):
    st.session_state["nav_page"] = st.session_state.pop("_nav_page_override")

page = st.sidebar.radio("View", ["Fleet Overview", "Machine Detail"], key="nav_page")
st.sidebar.markdown("---")

if page == "Fleet Overview":
    render_overview_page()
else:
    render_detail_page()
