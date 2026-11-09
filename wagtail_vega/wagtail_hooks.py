from django.urls import path
from django.views.i18n import JavaScriptCatalog
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
        # Translations for the admin scripts' messages (djangojs domain)
        path(
            "wagtail-vega/jsi18n/",
            JavaScriptCatalog.as_view(packages=["wagtail_vega"]),
            name="wagtail_vega_jsi18n",
        ),
        path(
            "wagtail-vega/document-rows/",
            views.document_rows,
            name="wagtail_vega_document_rows",
        ),
    ]
