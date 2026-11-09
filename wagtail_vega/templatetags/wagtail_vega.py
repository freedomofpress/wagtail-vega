import json

from django import template
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join

register = template.Library()

SCRIPTS = [
    "wagtail_vega/vendor/vega.min.js",
    "wagtail_vega/vendor/vega-lite.min.js",
    "wagtail_vega/vendor/vega-embed.min.js",
]


def _scripts() -> list[str]:
    scripts = list(SCRIPTS)
    scripts.append("wagtail_vega/wagtail-vega.js")
    return [static(s) for s in scripts]


@register.simple_tag(takes_context=True)
def wagtail_vega_assets(context):
    """Output the chart CSS and scripts, once per request.

    Chart blocks call this themselves, so the libraries are only loaded on
    pages that contain a chart. All scripts are external and deferred, with
    no inline JS, so a strict Content-Security-Policy works.

    Without a request in the context (e.g. ``{{ page.body }}`` rather than
    ``{% include_block %}``), there's no way to know what was already output,
    so each chart gets a small loader script instead. It loads the libraries
    once per page, however many times it's included.
    """
    stylesheet = format_html(
        '<link rel="stylesheet" href="{}">', static("wagtail_vega/wagtail-vega.css")
    )
    request = context.get("request")
    if request is None:
        return format_html(
            '{}\n<script src="{}" data-scripts="{}" defer></script>',
            stylesheet,
            static("wagtail_vega/wagtail-vega-loader.js"),
            json.dumps(_scripts()),
        )
    if getattr(request, "_wagtail_vega_assets", False):
        return ""
    request._wagtail_vega_assets = True
    return format_html(
        "{}\n{}",
        stylesheet,
        format_html_join("\n", '<script src="{}" defer></script>', ((s,) for s in _scripts())),
    )
