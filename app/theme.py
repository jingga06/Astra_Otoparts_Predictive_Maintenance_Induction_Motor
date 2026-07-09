"""Astra blue design tokens + hand-authored inline SVG icons.

Colors come from the ui-ux-pro-max "Trust & Authority" enterprise design
system query (navy/blue, WCAG AAA, explicitly avoids AI purple/pink
gradients). Status colors (critical/warning/normal) stay semantic
red/amber/green since color-coding alarms is a UX necessity, not a
branding choice. All icons below are hand-authored Feather/Lucide-style
strokes - zero emoji anywhere in this app.
"""

COLORS = {
    "primary": "#0F172A",       # navy - headers, primary text
    "secondary": "#334155",      # slate - secondary text
    "accent": "#0369A1",          # Astra blue - CTAs, active states, chart lines
    "accent_light": "#E0F2FE",     # light blue - card backgrounds, chips
    "background": "#F8FAFC",
    "surface": "#FFFFFF",
    "border": "#E2E8F0",
    "text": "#020617",
    "text_muted": "#64748B",
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
    "WARNING": "Warning",
    "CRITICAL": "Critical",
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


def global_css() -> str:
    c = COLORS
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Lexend:wght@500;600;700&family=Source+Sans+3:wght@400;500;600&display=swap');

html, body, [class*="css"] {{
    font-family: 'Source Sans 3', -apple-system, sans-serif;
    color: {c["text"]};
}}
h1, h2, h3, h4, .app-title {{
    font-family: 'Lexend', sans-serif;
    color: {c["primary"]};
    letter-spacing: -0.01em;
}}
#MainMenu, footer, header {{visibility: hidden;}}
.block-container {{padding-top: 1.6rem; max-width: 1200px;}}

.astra-topbar {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 20px; margin-bottom: 18px;
    background: linear-gradient(90deg, {c["primary"]} 0%, {c["accent"]} 100%);
    border-radius: 10px; color: white;
}}
.astra-topbar .title {{ font-family:'Lexend',sans-serif; font-weight:600; font-size:1.15rem; }}
.astra-topbar .subtitle {{ font-size:0.8rem; opacity:0.85; }}

.kpi-card {{
    background: {c["surface"]}; border: 1px solid {c["border"]};
    border-radius: 12px; padding: 16px 18px; height: 100%;
}}
.kpi-label {{
    font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em;
    color: {c["text_muted"]}; font-weight: 600; margin-bottom: 6px;
    display:flex; align-items:center; gap:6px;
}}
.kpi-value {{ font-family:'Lexend',sans-serif; font-size: 1.9rem; font-weight:700; color:{c["primary"]}; }}
.kpi-sub {{ font-size: 0.82rem; color: {c["text_muted"]}; margin-top: 4px; }}

.status-badge {{
    display:inline-flex; align-items:center; gap:8px;
    padding: 6px 14px; border-radius: 999px; font-weight:600; font-size:0.92rem;
}}

.reco-box {{
    border-left: 4px solid {c["accent"]}; background: {c["accent_light"]};
    border-radius: 8px; padding: 14px 16px; font-size: 0.92rem; color:{c["primary"]};
}}

.data-source-caption {{
    display:flex; align-items:center; gap:6px; color:{c["text_muted"]};
    font-size: 0.78rem; margin-top: 4px;
}}

.stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
.stTabs [data-baseweb="tab"] {{
    font-family:'Lexend',sans-serif; font-weight:500; font-size:0.9rem;
}}
</style>
"""
