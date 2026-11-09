"""Admin form widgets."""

from __future__ import annotations

import json

from django import forms
from django.urls import reverse
from wagtail.admin.telepath import register
from wagtail.admin.telepath.widgets import WidgetAdapter

from .conf import get_setting

CODEMIRROR_JS = "wagtail_vega/admin/vendor/codemirror.js"
EDITOR_JS = [
    CODEMIRROR_JS,
    "wagtail_vega/admin/json-source.js",
    "wagtail_vega/admin/data-format.js",
    "wagtail_vega/admin/code-editor.js",
]
EDITOR_CSS = "wagtail_vega/admin/code-editor.css"
VOYAGER_JS = "wagtail_vega/admin/voyager-launcher.js"
VOYAGER_CSS = "wagtail_vega/admin/voyager-launcher.css"


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

    With ``voyager=True`` (``"spec"`` mode only), a "Build chart with
    Voyager" button goes above the editor. It opens Vega Voyager with the
    chart's data and writes the chart it builds to the textarea, firing the
    usual "input" event (see voyager-launcher.js).
    """

    MODES = ("json", "spec", "data")

    def __init__(self, attrs=None, mode="json", voyager=False):
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of {self.MODES}")
        self.mode = mode
        self.voyager = voyager and mode == "spec"
        if self.voyager:
            self.template_name = "wagtail_vega/widgets/spec_editor.html"
        default_attrs = {"rows": 16, "spellcheck": "false", "autocomplete": "off"}
        super().__init__({**default_attrs, **(attrs or {})})

    def get_config(self) -> dict:
        config = {"mode": self.mode, "rows": int(self.attrs.get("rows") or 16)}
        if self.mode == "spec":
            config["validateUrl"] = reverse("wagtail_vega_validate_spec")
        return config

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # The editor's settings travel with the textarea, so the same markup
        # works whether telepath renders it or it's in the page's HTML.
        context["widget"]["attrs"]["data-wagtail-vega-code-editor"] = json.dumps(self.get_config())
        if self.voyager:
            context["voyager"] = self.voyager_config()
        return context

    def voyager_config(self) -> dict:
        return {
            "frame": reverse("wagtail_vega_voyager"),
            "rows": reverse("wagtail_vega_document_rows"),
            "validate": reverse("wagtail_vega_validate_spec"),
            "allowed_hosts": json.dumps(list(get_setting("ALLOWED_DATA_HOSTS"))),
        }

    @property
    def media(self):
        js, css = list(EDITOR_JS), [EDITOR_CSS]
        if self.voyager:
            js.append(VOYAGER_JS)
            css.append(VOYAGER_CSS)
        return forms.Media(js=js, css={"all": css})


class CodeEditorAdapter(WidgetAdapter):
    js_constructor = "wagtail_vega.widgets.CodeEditor"


register(CodeEditorAdapter(), CodeEditor)
