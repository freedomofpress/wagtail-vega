"""Chart themes.

A theme is a Vega ``config`` object, so it can control fonts, colours, axes,
legends and mark defaults. Themes are registered in settings::

    WAGTAIL_VEGA = {
        "THEMES": {
            # A full theme definition
            "house": {
                "label": "House style",
                "config": {"font": "Inter", "range": {"category": ["var(--brand)", "#888"]}},
                "dark": {"background": "#111", "axis": {"labelColor": "#ddd"}},
                "fallbacks": {"--brand": "#c0392b"},
            },
            # A plain dict is treated as the "config"
            "minimal": {"view": {"stroke": None}},
            # A dotted path to a dict defined in Python
            "print": "myproject.charts.PRINT_THEME",
            # One of the themes bundled with vega-embed
            "538": "vega:fivethirtyeight",
        },
        "DEFAULT_THEME": "house",
    }

String values of the form ``var(--token)`` are resolved in the browser from
CSS custom properties on the chart element. On the server (SSR), they are
resolved from ``fallbacks``, or from a ``var(--token, fallback)`` default.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from django.utils.translation import gettext as _

from .conf import get_setting

logger = logging.getLogger(__name__)

BUILTIN_PREFIX = "vega:"
THEME_KEYS = {"label", "config", "dark", "fallbacks", "vega_theme"}
VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*?)\s*)?\)")


@dataclass(frozen=True)
class Theme:
    """A registered chart theme, built from a ``THEMES`` entry by
    :func:`build_theme`.

    ``config`` is merged under the spec's own ``config``, and ``dark`` is
    merged over ``config`` when the page's colour scheme is dark.
    ``fallbacks`` maps CSS custom property names (``"--brand"``) to values
    used when the page doesn't define them, and for server-side rendering.
    """

    name: str
    label: str
    config: dict[str, Any] = field(default_factory=dict)
    dark: dict[str, Any] | None = None
    fallbacks: dict[str, str] = field(default_factory=dict)
    # Name of a theme bundled with vega-embed (e.g. "dark", "fivethirtyeight")
    vega_theme: str | None = None


def build_theme(name: str, definition: Any) -> Theme:
    """Build a :class:`Theme` from a ``THEMES`` entry: a definition dict, a
    plain config dict, a dotted import path, ``"vega:<name>"`` for a theme
    bundled with vega-embed, or a ``Theme``.

    Raises ``ImproperlyConfigured`` for definitions it can't use.
    """
    if isinstance(definition, Theme):
        return definition
    if isinstance(definition, str):
        if definition.startswith(BUILTIN_PREFIX):
            builtin = definition[len(BUILTIN_PREFIX) :]
            return Theme(name=name, label=name, vega_theme=builtin)
        try:
            definition = import_string(definition)
        except ImportError as e:
            raise ImproperlyConfigured(
                f"WAGTAIL_VEGA theme {name!r}: cannot import {definition!r}"
            ) from e
        return build_theme(name, definition)
    if not isinstance(definition, dict):
        raise ImproperlyConfigured(
            f"WAGTAIL_VEGA theme {name!r} must be a dict, dotted path or 'vega:<name>'"
        )
    if not (set(definition) & (THEME_KEYS - {"label"})):
        # A plain Vega config, perhaps with a label (which Vega doesn't use)
        config = {k: v for k, v in definition.items() if k != "label"}
        definition = {
            "config": config,
            **({"label": definition["label"]} if "label" in definition else {}),
        }
    unknown = set(definition) - THEME_KEYS
    if unknown:
        raise ImproperlyConfigured(
            f"WAGTAIL_VEGA theme {name!r} has unknown keys: {sorted(unknown)}"
        )
    return Theme(
        name=name,
        label=definition.get("label", name),
        config=definition.get("config") or {},
        dark=definition.get("dark"),
        fallbacks=definition.get("fallbacks") or {},
        vega_theme=definition.get("vega_theme"),
    )


def get_themes() -> dict[str, Theme]:
    """All themes in the ``THEMES`` setting, keyed by name."""
    return {
        name: build_theme(name, definition) for name, definition in get_setting("THEMES").items()
    }


def get_theme(name: str | None) -> Theme | None:
    """Look up a registered theme, falling back to ``DEFAULT_THEME``."""
    themes = get_themes()
    if name and name in themes:
        return themes[name]
    if name:
        # e.g. an editor's saved choice of a theme that's since been removed
        logger.warning("wagtail-vega: theme %r isn't in THEMES; using the default", name)
    default = get_setting("DEFAULT_THEME")
    if default:
        if default not in themes:
            raise ImproperlyConfigured(f"WAGTAIL_VEGA DEFAULT_THEME {default!r} is not in THEMES")
        return themes[default]
    return None


def theme_choices() -> list[tuple[str, str]]:
    """Choices for the editor-facing theme picker. The blank choice means
    "use the default" and is labelled with the default theme's name."""
    themes = get_themes()
    default = themes.get(get_setting("DEFAULT_THEME") or "")
    blank = _("Site default (%s)") % default.label if default else _("Site default")
    return [("", blank), *((name, theme.label) for name, theme in themes.items())]


# Keys whose contents are data, which var() resolution leaves alone. The
# browser applies the same rule (see wagtail-vega.js).
DATA_KEYS = frozenset({"data", "datasets", "values"})


def resolve_css_vars(value: Any, fallbacks: dict[str, str]) -> Any:
    """Replace ``var(--x)`` strings using ``fallbacks`` (used for SSR).

    Strings are resolved anywhere in the spec except inside data (``data``,
    ``datasets`` and ``values``), matching what the browser does.
    """
    if isinstance(value, dict):
        return {
            k: v if k in DATA_KEYS else resolve_css_vars(v, fallbacks) for k, v in value.items()
        }
    if isinstance(value, list):
        return [resolve_css_vars(v, fallbacks) for v in value]
    if isinstance(value, str) and "var(" in value:

        def sub(m: re.Match) -> str:
            return fallbacks.get(m.group(1)) or m.group(2) or m.group(0)

        return VAR_RE.sub(sub, value)
    return value
