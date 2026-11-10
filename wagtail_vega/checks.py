"""Django system checks for the WAGTAIL_VEGA settings.

Theme names used by chart blocks (``Meta.theme``) are checked by
``BaseChartBlock.check()``, which Wagtail runs for every StreamField.
"""

from django.core import checks
from django.core.exceptions import ImproperlyConfigured

from .conf import VISUAL_EDITORS, get_setting
from .themes import build_theme


@checks.register()
def check_themes(app_configs=None, **kwargs):
    errors = []
    names = set()
    for name, definition in get_setting("THEMES").items():
        try:
            build_theme(name, definition)
        except ImproperlyConfigured as e:
            errors.append(
                checks.Error(str(e), hint="See the theming docs.", id="wagtail_vega.E001")
            )
        names.add(name)
    default = get_setting("DEFAULT_THEME")
    if default and default not in names:
        errors.append(
            checks.Error(
                f"WAGTAIL_VEGA DEFAULT_THEME {default!r} isn't in THEMES.",
                hint=f"Add a {default!r} theme, or set DEFAULT_THEME to one of: "
                + (", ".join(sorted(names)) or "(no themes defined)"),
                id="wagtail_vega.E002",
            )
        )
    return errors


@checks.register()
def check_visual_editor(app_configs=None, **kwargs):
    value = get_setting("VISUAL_EDITOR")
    if value in VISUAL_EDITORS:
        return []
    return [
        checks.Error(
            f"WAGTAIL_VEGA VISUAL_EDITOR {value!r} isn't one of: {', '.join(VISUAL_EDITORS)}.",
            hint='Use "voyager" (the default) or "simple".',
            id="wagtail_vega.E003",
        )
    ]
