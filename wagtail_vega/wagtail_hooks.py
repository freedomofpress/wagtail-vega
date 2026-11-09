from django.urls import path
from wagtail import hooks

from . import views


@hooks.register("register_icons")
def register_icons(icons):
    return [*icons, "wagtail_vega/icons/chart.svg"]


@hooks.register("register_admin_urls")
def register_admin_urls():
    return [
        path(
            "wagtail-vega/validate-spec/",
            views.validate_spec,
            name="wagtail_vega_validate_spec",
        ),
        path(
            "wagtail-vega/document-rows/",
            views.document_rows,
            name="wagtail_vega_document_rows",
        ),
    ]
