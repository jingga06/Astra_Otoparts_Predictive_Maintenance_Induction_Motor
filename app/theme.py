"""Astra blue design tokens + hand-authored inline SVG icons.

Colors come from the ui-ux-pro-max "Trust & Authority" enterprise design
system query (navy/blue, WCAG AAA, explicitly avoids AI purple/pink
gradients). Status colors (critical/warning/normal) stay semantic
red/amber/green since color-coding alarms is a UX necessity, not a
branding choice. All icons below are hand-authored Feather/Lucide-style
strokes - zero emoji anywhere in this app.
"""

import base64
from functools import lru_cache
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"

COLORS = {
    "primary": "#0F172A",       # navy - headers, primary text
    "secondary": "#334155",      # slate - secondary text
    "accent": "#0369A1",          # Astra blue - CTAs, active states, chart lines
    "accent_light": "#E0F2FE",     # light blue - card backgrounds, chips
    "background": "#F8FAFC",
    "surface": "#FFFFFF",
    "border": "#E2E8F0",
    "text": "#020617",
    "text_muted": "#475569",   # slate-600 - darkest still legible as "muted" (was #64748B/slate-500,
                                 # too light for small caption/label text on a projector)
    "critical": "#DC2626",
    "warning": "#D97706",
    "normal": "#16A34A",
}

STATUS_COLOR = {
    "NORMAL": COLORS["normal"],
    "WARNING": COLORS["warning"],
    "CRITICAL": COLORS["critical"],
}

STATUS_LABEL = {
    "NORMAL": "Normal",
    "WARNING": "Peringatan",
    "CRITICAL": "Kritis",
}

_ICON_PATHS = {
    "check-circle": (
        '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>'
        '<polyline points="22 4 12 14.01 9 11.01"></polyline>'
    ),
    "alert-triangle": (
        '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86'
        'a2 2 0 0 0-3.42 0z"></path>'
        '<line x1="12" y1="9" x2="12" y2="13"></line>'
        '<line x1="12" y1="17" x2="12.01" y2="17"></line>'
    ),
    "alert-octagon": (
        '<polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 '
        '7.86 2"></polygon>'
        '<line x1="12" y1="8" x2="12" y2="12"></line>'
        '<line x1="12" y1="16" x2="12.01" y2="16"></line>'
    ),
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>',
    "clock": (
        '<circle cx="12" cy="12" r="10"></circle>'
        '<polyline points="12 6 12 12 16 14"></polyline>'
    ),
    "tool": (
        '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 '
        '7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>'
    ),
    "database": (
        '<ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>'
        '<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>'
        '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>'
    ),
    "cpu": (
        '<rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect>'
        '<rect x="9" y="9" width="6" height="6"></rect>'
        '<line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line>'
        '<line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line>'
        '<line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line>'
        '<line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line>'
    ),
    "gauge": (
        '<path d="M12 20a8 8 0 1 0-8-8"></path>'
        '<path d="M12 12l4-4"></path>'
        '<path d="M12 20v0"></path>'
    ),
    "settings": (
        '<circle cx="12" cy="12" r="3"></circle>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 '
        '1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 '
        '19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 '
        '.33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 '
        '0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 '
        '1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 '
        '1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 '
        '0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>'
    ),
    "play": '<polygon points="5 3 19 12 5 21 5 3"></polygon>',
    "pause": (
        '<rect x="6" y="4" width="4" height="16"></rect>'
        '<rect x="14" y="4" width="4" height="16"></rect>'
    ),
}


def icon(name: str, size: int = 18, color: str = None, stroke_width: float = 2.0) -> str:
    color = color or COLORS["text"]
    path = _ICON_PATHS.get(name, _ICON_PATHS["activity"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'style="vertical-align:middle;display:inline-block">{path}</svg>'
    )


def icon_for_status(level: str, size: int = 20) -> str:
    mapping = {"NORMAL": "check-circle", "WARNING": "alert-triangle", "CRITICAL": "alert-octagon"}
    return icon(mapping.get(level, "activity"), size=size, color=STATUS_COLOR.get(level, COLORS["text"]))


@lru_cache(maxsize=1)
def _astra_logo_data_uri() -> str:
    data = (_ASSETS_DIR / "astra_logo.png").read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def astra_logo_img(height: int = 28, style: str = "") -> str:
    """The real PT Astra Otoparts wordmark (app/assets/astra_logo.png,
    supplied by the user - not fetched/guessed). Red/dark on transparent -
    used where there's a light background behind it (e.g. the sidebar)."""
    return (
        f'<img src="{_astra_logo_data_uri()}" alt="Astra Otoparts" '
        f'style="height:{height}px;width:auto;display:block;{style}">'
    )


@lru_cache(maxsize=1)
def _astra_globe_data_uri() -> str:
    data = (_ASSETS_DIR / "astra_globe.png").read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def astra_globe_img(height: int = 28, style: str = "") -> str:
    """Icon-only crop of the Astra Otoparts logo (just the ringed globe +
    swoosh, no wordmark, app/assets/astra_globe.png) - for tight spots like
    the topbar where the full wordmark chip is too heavy."""
    return (
        f'<img src="{_astra_globe_data_uri()}" alt="Astra" '
        f'style="height:{height}px;width:auto;display:block;{style}">'
    )


def global_css() -> str:
    c = COLORS
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Lexend:wght@500;600;700;800&family=Source+Sans+3:wght@400;500;600&family=JetBrains+Mono:wght@500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Source Sans 3', -apple-system, sans-serif;
    color: {c["text"]};
    font-size: 1rem;
    line-height: 1.55;
}}
h1, h2, h3, h4, .app-title {{
    font-family: 'Lexend', sans-serif;
    color: {c["primary"]};
    letter-spacing: -0.01em;
}}
#MainMenu, footer, header {{visibility: hidden;}}

/* -------------------- Legibility pass: darker/bolder/larger muted text --------
   Applies to Streamlit's own caption/widget-label chrome (not just our custom
   classes below) so every small gray label in the app - captions, slider/
   selectbox/multiselect labels, help text - reads clearly on a projector, not
   just on a laptop screen. */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label,
.stMarkdown small {{
    color: {c["text_muted"]} !important;
    font-size: 0.92rem !important;
    font-weight: 600 !important;
    line-height: 1.5 !important;
}}

/* Living background: two soft drifting glows + a slowly panning isometric
   hex/triangle lattice (three 60deg line families - an engineering/PCB feel,
   not a plain spreadsheet grid) - subtle enough not to hurt text contrast,
   but animated so the whole app reads as "alive" instead of a flat page. */
@keyframes astra-bg-drift {{
    0%, 100% {{
        background-position: 0% 0%, 0% 0%, 0px 0px, 0px 0px, 0px 0px, 0 0;
    }}
    50% {{
        background-position: 6% 8%, -6% -8%, 46px 0px, -23px 40px, 23px 40px, 0 0;
    }}
}}
.stApp {{
    background:
        radial-gradient(560px 560px at 10% 12%, {c["accent_light"]}CC 0%, transparent 68%),
        radial-gradient(520px 520px at 92% 82%, #DCEEFF 0%, transparent 65%),
        repeating-linear-gradient(0deg,   rgba(15,23,42,0.07) 0 1px, transparent 1px 46px),
        repeating-linear-gradient(60deg,  rgba(15,23,42,0.07) 0 1px, transparent 1px 46px),
        repeating-linear-gradient(-60deg, rgba(15,23,42,0.07) 0 1px, transparent 1px 46px),
        {c["background"]};
    background-size: auto, auto, auto, auto, auto, auto;
    background-repeat: no-repeat, no-repeat, repeat, repeat, repeat, no-repeat;
    animation: astra-bg-drift 26s ease-in-out infinite;
}}
@media (prefers-reduced-motion: reduce) {{
    .stApp {{ animation: none; }}
}}
.block-container {{padding-top: 1.6rem; max-width: 1220px;}}

/* -------------------- Numeric / data typography -------------------- */
.metric-mono {{
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
}}

/* -------------------- Top bar -------------------- */
.astra-topbar {{
    position: relative; overflow: hidden;
    display: flex; align-items: center; justify-content: space-between;
    padding: 18px 26px; margin-bottom: 20px;
    background:
        radial-gradient(600px 240px at 15% 0%, rgba(255,255,255,0.10) 0%, transparent 60%),
        linear-gradient(115deg, {c["primary"]} 0%, #113B66 45%, {c["accent"]} 100%);
    border-radius: 14px; color: white;
    box-shadow: 0 12px 28px -10px rgba(15, 23, 42, 0.45), 0 2px 6px rgba(15, 23, 42, 0.15);
}}
.astra-topbar::after {{
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background-image: radial-gradient(rgba(255,255,255,0.14) 1px, transparent 1px);
    background-size: 18px 18px;
    -webkit-mask-image: linear-gradient(115deg, rgba(0,0,0,0.5), transparent 65%);
            mask-image: linear-gradient(115deg, rgba(0,0,0,0.5), transparent 65%);
}}
.astra-topbar > div {{ position: relative; z-index: 1; }}
.astra-topbar .title {{ font-family:'Lexend',sans-serif; font-weight:700; font-size:1.35rem; }}
.astra-topbar .subtitle {{ font-size:0.92rem; font-weight:500; opacity:0.92; }}

/* -------------------- KPI / metric cards -------------------- */
.kpi-card {{
    position: relative; background: {c["surface"]}; border: 1px solid {c["border"]};
    border-radius: 16px; padding: 22px 24px; height: 100%;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 10px 24px -16px rgba(15, 23, 42, 0.25);
    transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
}}
.kpi-card:hover {{
    transform: translateY(-3px);
    box-shadow: 0 4px 10px rgba(15, 23, 42, 0.06), 0 18px 32px -14px rgba(15, 23, 42, 0.32);
    border-color: {c["accent"]}55;
}}
.kpi-label {{
    font-size: 0.86rem; text-transform: uppercase; letter-spacing: 0.05em;
    color: {c["text_muted"]}; font-weight: 700; margin-bottom: 10px;
    display:flex; align-items:center; gap:6px;
}}
.kpi-value {{
    font-family: 'JetBrains Mono', 'Lexend', sans-serif; font-size: 2rem; font-weight:700;
    color:{c["primary"]}; font-variant-numeric: tabular-nums; letter-spacing: -0.02em;
}}
.kpi-sub {{ font-size: 0.92rem; color: {c["text_muted"]}; font-weight: 600; margin-top: 6px; }}

/* -------------------- Status badges (with soft glow) -------------------- */
.status-badge {{
    display:inline-flex; align-items:center; gap:8px;
    padding: 7px 16px; border-radius: 999px; font-weight:700; font-size:1rem;
    box-shadow: inset 0 0 0 1px currentColor;
}}
.status-badge.pulse {{ animation: astra-badge-pulse 1.8s ease-in-out infinite; }}
@keyframes astra-badge-pulse {{
    0%, 100% {{ box-shadow: inset 0 0 0 1px currentColor, 0 0 0 0 currentColor; }}
    50% {{ box-shadow: inset 0 0 0 1px currentColor, 0 0 0 6px transparent; }}
}}

.reco-box {{
    border-left: 4px solid {c["accent"]};
    background: linear-gradient(135deg, {c["accent_light"]} 0%, #F0F9FF 100%);
    border-radius: 10px; padding: 16px 18px; font-size: 1rem; font-weight: 500; color:{c["primary"]};
    box-shadow: 0 6px 16px -10px rgba(3, 105, 161, 0.35);
}}

.data-source-caption {{
    display:flex; align-items:center; gap:6px; color:{c["text_muted"]};
    font-size: 0.88rem; font-weight: 600; margin-top: 6px;
}}

/* -------------------- Fleet Overview: attention rows & KPI strip -------------------- */
.attention-row {{
    border-left: 4px solid {c["border"]}; background: {c["surface"]};
    border-radius: 10px; padding: 14px 18px; margin-bottom: 8px; font-size: 1rem;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 6px 16px -12px rgba(15, 23, 42, 0.25);
    transition: transform 150ms ease, box-shadow 150ms ease;
}}
.attention-row:hover {{
    transform: translateX(2px);
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.06), 0 10px 22px -12px rgba(15, 23, 42, 0.3);
}}
.fleet-kpi-value {{
    font-family: 'JetBrains Mono', 'Lexend', sans-serif; font-size: 1.9rem; font-weight: 700;
    color: {c["primary"]}; font-variant-numeric: tabular-nums;
}}
.fleet-kpi-label {{
    font-size: 0.86rem; text-transform: uppercase; letter-spacing: 0.05em;
    color: {c["text_muted"]}; font-weight: 700;
}}

/* -------------------- Tabs -------------------- */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {c["border"]}; }}
.stTabs [data-baseweb="tab"] {{
    font-family:'Lexend',sans-serif; font-weight:700; font-size:1rem;
    color: {c["text_muted"]};
}}
.stTabs [aria-selected="true"] {{ color: {c["accent"]} !important; }}
.stTabs [data-baseweb="tab-highlight"] {{
    background-color: {c["accent"]} !important; height: 3px; border-radius: 3px;
}}

/* -------------------- Buttons -------------------- */
.stButton > button {{
    border-radius: 10px !important; font-weight: 600 !important;
    transition: transform 150ms ease, box-shadow 150ms ease !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}}
.stButton > button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 8px 16px -8px rgba(15, 23, 42, 0.35);
}}
.stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, {c["accent"]} 0%, #0C4A6E 100%) !important;
    border: none !important;
}}

/* -------------------- Sidebar nav as a pill segmented control -------------------- */
section[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);
    border-right: 1px solid {c["border"]};
}}
div[data-testid="stRadio"] label {{
    padding: 9px 14px; border-radius: 9px; margin-bottom: 2px;
    transition: background-color 150ms ease, color 150ms ease; cursor: pointer;
}}
div[data-testid="stRadio"] label:hover {{ background: {c["accent_light"]}; }}
div[data-testid="stRadio"] label:has(input:checked) {{
    background: {c["accent_light"]}; font-weight: 700; color: {c["accent"]};
}}

/* -------------------- Dialog (Quick view modal) -------------------- */
div[data-testid="stDialog"] > div {{
    border-radius: 18px !important;
    box-shadow: 0 24px 64px -20px rgba(15, 23, 42, 0.55) !important;
}}

/* -------------------- Sliders -------------------- */
div[data-testid="stSlider"] [role="slider"] {{
    box-shadow: 0 0 0 5px {c["accent_light"]} !important;
}}
</style>
"""
