from django import template
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join

from ..conf import get_setting

register = template.Library()

SCRIPTS = [
    "wagtail_vega/vendor/vega.min.js",
    "wagtail_vega/vendor/vega-lite.min.js",
    "wagtail_vega/vendor/vega-embed.min.js",
]


@register.simple_tag(takes_context=True)
def wagtail_vega_assets(context):
    """Output the chart CSS and scripts, once per request.

    Chart blocks call this themselves, so the libraries are only loaded on
    pages that contain a chart. All scripts are external and deferred, with
    no inline JS, so a strict Content-Security-Policy works.
    """
    request = context.get("request")
    if request is not None:
        if getattr(request, "_wagtail_vega_assets", False):
            return ""
        request._wagtail_vega_assets = True

    scripts = list(SCRIPTS)
    if get_setting("CSP_SAFE"):
        scripts.append("wagtail_vega/vendor/vega-interpreter.js")
    scripts.append("wagtail_vega/wagtail-vega.js")
    return format_html(
        '<link rel="stylesheet" href="{}">\n{}',
        static("wagtail_vega/wagtail-vega.css"),
        format_html_join("\n", '<script src="{}" defer></script>', ((static(s),) for s in scripts)),
    )
