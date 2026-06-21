"""Signal theme SVG icons — match mockup set."""

from __future__ import annotations

# Heroicons-style 24x24 paths, stroke indigo/coral

def _svg(path: str, *, size: int = 24, stroke: str = "currentColor", fill: str = "none") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="{fill}" stroke="{stroke}" stroke-width="1.75" '
        f'stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
    )


ICON_BRIEFCASE = _svg(
    '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>'
)
ICON_USERS = _svg(
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
    '<circle cx="9" cy="7" r="4"/>'
    '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
)
ICON_SEARCH = _svg(
    '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>'
)
ICON_MAIL = _svg(
    '<rect x="2" y="4" width="20" height="16" rx="2"/>'
    '<path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>'
)
ICON_DOC = _svg(
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
    '<line x1="16" y1="17" x2="8" y2="17"/>'
)
ICON_NETWORK = _svg(
    '<circle cx="12" cy="12" r="2"/>'
    '<circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/>'
    '<circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>'
    '<line x1="8" y1="7" x2="10" y2="10"/><line x1="16" y1="7" x2="14" y2="10"/>'
    '<line x1="8" y1="17" x2="10" y2="14"/><line x1="16" y1="17" x2="14" y2="14"/>'
)
ICON_RADAR = _svg(
    '<circle cx="12" cy="12" r="10"/>'
    '<circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>'
    '<path d="M12 2v4"/><path d="M12 18v4"/>'
)
ICON_LIBRARY = _svg(
    '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
    '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'
)
ICON_SETTINGS = _svg(
    '<circle cx="12" cy="12" r="3"/>'
    '<path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2'
    'M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>'
)
ICON_HOME = _svg(
    '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
    '<polyline points="9 22 9 12 15 12 15 22"/>'
)

STEP_ICONS: dict[str, str] = {
    "role": ICON_BRIEFCASE,
    "people": ICON_USERS,
    "research": ICON_SEARCH,
    "outreach": ICON_MAIL,
    "apply": ICON_DOC,
}

PAGE_ICONS: dict[str, str] = {
    "home": ICON_HOME,
    "scout": ICON_RADAR,
    "library": ICON_LIBRARY,
    "settings": ICON_SETTINGS,
}

INTEGRATION_ICONS: dict[str, str] = {
    "vertex": _svg('<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/>', stroke="#6366f1"),
    "fireworks": _svg('<polygon points="12 2 15 9 22 9 16 14 18 22 12 17 6 22 8 14 2 9 9 9"/>'),
    "jobspy": _svg('<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>'),
    "handshake": _svg('<path d="M17 11h1a3 3 0 0 1 0 6h-1"/><path d="M9 12v6"/><path d="M13 12v6"/>'),
    "careershift": _svg('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/>'),
    "apollo": _svg('<circle cx="12" cy="12" r="10"/><path d="M12 8v8"/><path d="M8 12h8"/>'),
    "tavily": _svg('<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>'),
    "notion": _svg('<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 4v16"/>'),
}
