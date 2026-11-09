"""Admin form widgets."""

from __future__ import annotations

import json

from django import forms
from django.templatetags.static import static
from django.urls import reverse
from wagtail.admin.telepath import register
from wagtail.admin.telepath.widgets import WidgetAdapter

from .builder_strings import builder_strings
from .conf import get_allowed_hosts, get_setting
from .encoders import VegaJSONEncoder
from .themes import get_themes

CODEMIRROR_JS = "wagtail_vega/admin/vendor/codemirror.js"
EDITOR_JS = [
    CODEMIRROR_JS,
    "wagtail_vega/admin/json-source.js",
    "wagtail_vega/admin/data-format.js",
    "wagtail_vega/admin/code-editor.js",
]
EDITOR_CSS = "wagtail_vega/admin/code-editor.css"
BUILDER_JS = ["wagtail_vega/admin/chart-spec.js", "wagtail_vega/admin/chart-builder.js"]
BUILDER_CSS = "wagtail_vega/admin/chart-builder.css"
# Loaded by the chart builder the first time it opens, for its preview, so
# edit pages don't load the Vega libraries until they're needed
BUILDER_PREVIEW_JS = [
    "wagtail_vega/vendor/vega.min.js",
    "wagtail_vega/vendor/vega-lite.min.js",
    "wagtail_vega/vendor/vega-embed.min.js",
    "wagtail_vega/vendor/vega-interpreter.js",
    "wagtail_vega/wagtail-vega.js",
]
BUILDER_PREVIEW_CSS = "wagtail_vega/wagtail-vega.css"
# The preview draws at most this many rows; the spec always loads them all
BUILDER_PREVIEW_ROWS = 5000


class CodeEditor(forms.Textarea):
    """A textarea that the Wagtail admin enhances with a CodeMirror editor.

    ``mode`` is one of:

    - ``"json"``: JSON with syntax highlighting and live syntax errors.
    - ``"spec"``: a Vega / Vega-Lite spec. As ``"json"``, plus live schema
      and data-host validation against the server (see ``views.py``).
    - ``"data"``: pasted CSV, TSV or JSON. Tabs are shown, lines don't
      wrap, JSON is highlighted, and ragged rows and JSON errors are marked.

    The textarea stays in the form, hidden, and is what gets submitted: the
    editor writes every change back to it. It works in StreamField blocks
    (through the telepath adapter below) and in ordinary forms.

    With ``builder=True`` (``"spec"`` mode only), the field shows a preview
    of the chart, its problems, and an "Edit chart" button instead of the
    inline editor. The button opens the chart editor: visual controls, this
    code editor and a live preview, all on the same spec, which is written to
    the textarea as it changes, firing the usual "input" event (see
    chart-builder.js).
    """

    MODES = ("json", "spec", "data")

    def __init__(self, attrs=None, mode="json", builder=False):
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of {self.MODES}")
        self.mode = mode
        self.builder = builder and mode == "spec"
        if self.builder:
            self.template_name = "wagtail_vega/widgets/spec_editor.html"
        default_attrs = {"rows": 16, "spellcheck": "false", "autocomplete": "off"}
        super().__init__({**default_attrs, **(attrs or {})})

    def get_config(self) -> dict:
        config = {"mode": self.mode, "rows": int(self.attrs.get("rows") or 16)}
        if self.mode == "spec":
            config["validateUrl"] = reverse("wagtail_vega_validate_spec")
        if self.builder:
            # Shown in the chart editor's dialog rather than inline
            config["builder"] = True
        return config

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # The editor's settings travel with the textarea, so the same markup
        # works whether telepath renders it or it's in the page's HTML.
        context["widget"]["attrs"]["data-wagtail-vega-code-editor"] = json.dumps(self.get_config())
        if self.builder:
            context["builder"] = json.dumps(self.builder_config(), cls=VegaJSONEncoder)
            # With no spec yet, the builder is the obvious place to start
            text = value if isinstance(value, str) else ""
            context["builder_first"] = text.strip() in ("", "null")
        return context

    def builder_config(self) -> dict:
        """Settings for the chart builder (chart-builder.js): its endpoints,
        the data host allowlist, the site's themes for the preview, and the
        scripts the preview loads when the builder first opens."""
        themes = {
            name: {
                "config": theme.config,
                "dark": theme.dark,
                "fallbacks": theme.fallbacks,
                "vega_theme": theme.vega_theme,
            }
            for name, theme in get_themes().items()
        }
        return {
            "rowsUrl": reverse("wagtail_vega_document_rows"),
            "validateUrl": reverse("wagtail_vega_validate_spec"),
            "allowedHosts": get_allowed_hosts(),
            "themes": themes,
            "defaultTheme": get_setting("DEFAULT_THEME") or None,
            "embedOptions": get_setting("EMBED_OPTIONS"),
            "scripts": [static(path) for path in BUILDER_PREVIEW_JS],
            "stylesheet": static(BUILDER_PREVIEW_CSS),
            "previewRows": BUILDER_PREVIEW_ROWS,
            "strings": builder_strings(),
        }

    @property
    def media(self):
        js, css = list(EDITOR_JS), [EDITOR_CSS]
        if self.builder:
            js.extend(BUILDER_JS)
            css.append(BUILDER_CSS)
        return forms.Media(js=js, css={"all": css})


class CodeEditorAdapter(WidgetAdapter):
    js_constructor = "wagtail_vega.widgets.CodeEditor"


register(CodeEditorAdapter(), CodeEditor)
