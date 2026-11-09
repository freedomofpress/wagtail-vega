"""Admin form widgets."""

from __future__ import annotations

import json

from django import forms
from django.urls import NoReverseMatch, reverse

from .conf import get_setting


class SpecTextarea(forms.Textarea):
    """The spec textarea plus a button that opens Vega Voyager.

    The textarea stays the source of truth: Voyager's result is written to
    its ``value``, followed by a bubbling ``input`` event, so other editors
    built on top of the textarea can pick the change up.
    """

    template_name = "wagtail_vega/widgets/spec_textarea.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        try:
            urls = {
                "frame": reverse("wagtail_vega:voyager"),
                "rows": reverse("wagtail_vega:document_rows"),
                "validate": reverse("wagtail_vega:validate_spec"),
            }
        except NoReverseMatch:
            # Rendered outside a project with the Wagtail admin URLs
            urls = None
        context["voyager"] = urls and {
            **urls,
            "allowed_hosts": json.dumps(list(get_setting("ALLOWED_DATA_HOSTS"))),
        }
        return context

    @property
    def media(self):
        return forms.Media(
            js=["wagtail_vega/admin/voyager-launcher.js"],
            css={"all": ["wagtail_vega/admin/voyager-launcher.css"]},
        )
