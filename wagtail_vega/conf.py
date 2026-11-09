"""Access to the ``WAGTAIL_VEGA`` settings dict, with defaults."""

from typing import Any

from django.conf import settings

DEFAULTS: dict[str, Any] = {
    # name -> theme definition (dict, dotted path, or "vega:<builtin>")
    "THEMES": {},
    # name of the theme used when neither the block nor the editor picks one
    "DEFAULT_THEME": None,
    # hosts charts may load data from; "*.example.com" matches subdomains.
    # Relative (same-origin) URLs are always allowed.
    "ALLOWED_DATA_HOSTS": [],
    # Use vega-interpreter so charts work without 'unsafe-eval' in CSP
    "CSP_SAFE": False,
    # Render an SVG on the server (requires the "ssr" extra)
    "SSR": False,
    "SSR_CACHE_TIMEOUT": 60 * 60 * 24,
    # Render a <details> table of the chart data for screen readers / no-JS
    "FALLBACK_TABLE": True,
    "FALLBACK_TABLE_MAX_ROWS": 100,
    # Validate specs against the vendored JSON schemas when saving
    "VALIDATE_SCHEMA": True,
    # Default vega-embed options
    "EMBED_OPTIONS": {"actions": False, "renderer": "svg"},
}


def get_setting(name: str) -> Any:
    user = getattr(settings, "WAGTAIL_VEGA", {})
    if name in user:
        return user[name]
    return DEFAULTS[name]
