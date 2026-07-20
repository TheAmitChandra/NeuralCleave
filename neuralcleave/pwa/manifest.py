"""PWA Web App Manifest builder.

Produces a W3C-compliant Web Application Manifest dict that the browser
uses to install NeuralCleave as a Progressive Web App on any device.

Spec: https://www.w3.org/TR/appmanifest/
"""

from __future__ import annotations

from typing import Any

# Inline SVG icon — no external file dependency.
# 192 and 512 px logical sizes; SVG is resolution-independent.
APP_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
    '<rect width="512" height="512" rx="80" fill="#1a1a2e"/>'
    '<circle cx="256" cy="196" r="90" fill="#4a9eff"/>'
    '<path d="M110 390 Q256 490 402 390 Q345 305 256 305 Q167 305 110 390Z" fill="#4a9eff"/>'
    '<circle cx="256" cy="196" r="44" fill="#0f0f23"/>'
    '<circle cx="242" cy="188" r="13" fill="#4a9eff"/>'
    "</svg>"
)

THEME_COLOR = "#1a1a2e"
BACKGROUND_COLOR = "#0f0f23"


def build_manifest(base_url: str = "") -> dict[str, Any]:
    """Return the PWA manifest as a plain dict (JSON-serializable).

    Args:
        base_url: Optional base URL prefix (unused by default; kept for
                  future absolute-URL support).
    """
    return {
        "name": "NeuralCleave",
        "short_name": "NeuralCleave",
        "description": "Your personal AI assistant — chat, automate, and remember.",
        "start_url": "/app",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "theme_color": THEME_COLOR,
        "background_color": BACKGROUND_COLOR,
        "lang": "en",
        "dir": "ltr",
        "categories": ["productivity", "utilities"],
        "icons": [
            {
                "src": "/app-icon-192.svg",
                "sizes": "192x192",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            },
            {
                "src": "/app-icon-512.svg",
                "sizes": "512x512",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            },
        ],
        "shortcuts": [
            {
                "name": "New Conversation",
                "short_name": "Chat",
                "description": "Start a new AI conversation",
                "url": "/app?new=1",
                "icons": [{"src": "/app-icon-192.svg", "sizes": "192x192"}],
            },
        ],
        "screenshots": [],
        "prefer_related_applications": False,
    }
