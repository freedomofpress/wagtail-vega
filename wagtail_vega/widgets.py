"""Admin form widgets."""

from __future__ import annotations

import json

from django import forms
from django.urls import reverse
from wagtail.admin.telepath import register
from wagtail.admin.telepath.widgets import WidgetAdapter

CODEMIRROR_JS = "wagtail_vega/admin/vendor/codemirror.js"
EDITOR_JS = [
    CODEMIRROR_JS,
    "wagtail_vega/admin/json-source.js",
    "wagtail_vega/admin/data-format.js",
    "wagtail_vega/admin/code-editor.js",
]
EDITOR_CSS = "wagtail_vega/admin/code-editor.css"


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
    """

    MODES = ("json", "spec", "data")

    def __init__(self, attrs=None, mode="json"):
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of {self.MODES}")
        self.mode = mode
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
        return context

    @property
    def media(self):
        return forms.Media(js=EDITOR_JS, css={"all": [EDITOR_CSS]})


class CodeEditorAdapter(WidgetAdapter):
    js_constructor = "wagtail_vega.widgets.CodeEditor"


register(CodeEditorAdapter(), CodeEditor)
