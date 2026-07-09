"""Predictive Maintenance dashboard - PT Astra Otoparts Tbk / WINTEQ, Case 2.

Run with:  streamlit run app/dashboard.py   (from the src/ directory)

Replays cached NASA IMS Bearing pipeline output (see scripts/build_artifacts.py)
snapshot-by-snapshot to show health score, alarm status and RUL behaviour as
a machine degrades - the exact "one machine, alarm + RUL as it crosses the
3-sigma threshold" prototype requested for the bootcamp review.
"""

import sys
import time
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
# Data loading
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


# ----------------------------------------------------------------------
# Guard: artifacts not built yet
# ----------------------------------------------------------------------
if not artifacts_available():
    st.markdown(
        '<div class="astra-topbar"><div>'
        '<div class="title">Predictive Maintenance &mdash; Induction Motor</div>'
        '<div class="subtitle">PT Astra Otoparts Tbk &middot; WINTEQ &middot; Case 2 Prototype</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    st.warning(
        "No precomputed artifacts found yet. Run "
        "`python -m scripts.build_artifacts --all` from the `src/` directory first, "
        "then reload this page."
    )
    st.stop()


# ----------------------------------------------------------------------
# Sidebar controls
# ----------------------------------------------------------------------
st.sidebar.markdown(
    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
    f'{theme.icon("settings", size=18, color=theme.COLORS["accent"])}'
    f'<b style="font-family:Lexend,sans-serif;color:{theme.COLORS["primary"]}">Replay Controls</b></div>',
    unsafe_allow_html=True,
)

run_options = list(RUN_SPECS.keys())
run_key = st.sidebar.selectbox(
    "Production run",
    options=run_options,
    format_func=lambda k: RUN_SPECS[k].label,
)
spec = RUN_SPECS[run_key]

bearing_options = list(range(1, spec.n_bearings + 1))


def bearing_label(b: int) -> str:
    tag = " (monitored - known failure)" if b == spec.failing_bearing else ""
    return f"Motor Conveyor - Bearing {b}{tag}"


bearing_id = st.sidebar.selectbox(
    "Machine / bearing",
    options=bearing_options,
    index=bearing_options.index(spec.failing_bearing),
    format_func=bearing_label,
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
# every rerun, and not on every row, only on the actual transition. This is
# the "automated alert" behaviour requested in the Case 2 brief.
# ----------------------------------------------------------------------
_SEVERITY = {"NORMAL": 0, "WARNING": 1, "CRITICAL": 2}
_toast_marker = (state_key, position)
if position > 0 and st.session_state.get("_last_toast_marker") != _toast_marker:
    prev_level = df.iloc[position - 1]["alarm_level"]
    curr_level = current["alarm_level"]
    if _SEVERITY.get(curr_level, 0) > _SEVERITY.get(prev_level, 0):
        toast_icon = ":material/error:" if curr_level == "CRITICAL" else ":material/warning:"
        st.toast(
            f"{bearing_label(bearing_id)} status naik ke {theme.STATUS_LABEL[curr_level]} "
            f"- {current['alarm_reason']}",
            icon=toast_icon,
        )
    st.session_state["_last_toast_marker"] = _toast_marker

# ----------------------------------------------------------------------
# Top bar
# ----------------------------------------------------------------------
st.markdown(
    f'<div class="astra-topbar"><div>'
    f'<div class="title">Predictive Maintenance &mdash; Induction Motor</div>'
    f'<div class="subtitle">PT Astra Otoparts Tbk &middot; WINTEQ &middot; Case 2 Prototype</div>'
    f'</div>'
    f'<div style="text-align:right;font-size:0.82rem;opacity:0.9">'
    f'{bearing_label(bearing_id)}<br>{spec.label} &middot; t = {current["elapsed_hours"]:.1f}h'
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
        number={"suffix": "", "font": {"size": 30, "color": theme.COLORS["primary"]}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": theme.COLORS["accent"]},
            "bgcolor": "white",
            "steps": [
                {"range": [0, 40], "color": "#FEE2E2"},
                {"range": [40, 70], "color": "#FEF3C7"},
                {"range": [70, 100], "color": "#DCFCE7"},
            ],
        },
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(height=170, margin=dict(l=20, r=20, t=10, b=0))
    st.markdown(
        f'<div class="kpi-label">{theme.icon("activity", 14, theme.COLORS["text_muted"])} HEALTH SCORE</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with kpi2:
    level = current["alarm_level"]
    color = theme.STATUS_COLOR[level]
    st.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{theme.icon("alert-triangle", 14, theme.COLORS["text_muted"])} ALARM STATUS</div>'
        f'<div class="status-badge" style="background:{color}1A;color:{color}">'
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
tab_trend, tab_signal, tab_alerts = st.tabs(["Trend", "Signal Detail", "Alerts & Recommendation"])

with tab_trend:
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Health Score over time**")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=visible["elapsed_hours"], y=visible["health_score"],
            mode="lines", line=dict(color=theme.COLORS["accent"], width=2), name="Health score",
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
            yaxis_range=[0, 105], plot_bgcolor="white", showlegend=False,
        )
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
            plot_bgcolor="white", showlegend=False,
        )
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
            xaxis_title="Time (ms)", yaxis_title="Acceleration (g)", plot_bgcolor="white",
        )
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
            xaxis_title="Frequency (Hz)", yaxis_title="Envelope FFT magnitude", plot_bgcolor="white",
        )
        st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})
    st.caption(
        "BPFO/BPFI/BSF are the bearing's outer-race, inner-race and ball-spin fault "
        "frequencies, computed from Rexnord ZA-2115 geometry (see pdm/bearing_physics.py)."
    )

with tab_alerts:
    level = current["alarm_level"]
    color = theme.STATUS_COLOR[level]

    st.markdown(
        f'<div class="status-badge" style="background:{color}1A;color:{color};font-size:1.05rem">'
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
# Auto-play loop - the actual position advance happens at the TOP of the
# script (before the slider widget is created); this just paces the reruns.
# ----------------------------------------------------------------------
if st.session_state.playing and position < n - 1:
    speed_map = {"1x": 0.6, "4x": 0.25, "16x": 0.08, "64x": 0.02}
    time.sleep(speed_map[speed])
    st.rerun()
