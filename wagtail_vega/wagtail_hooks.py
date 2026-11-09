from django.urls import include, path
from wagtail import hooks

from . import views


@hooks.register("register_icons")
def register_icons(icons):
    return [*icons, "wagtail_vega/icons/chart.svg"]


@hooks.register("register_admin_urls")
def register_admin_urls():
    urls = [
        path("voyager/", views.voyager, name="voyager"),
        path("document-rows/", views.document_rows, name="document_rows"),
        path("validate-spec/", views.validate_spec, name="validate_spec"),
    ]
    return [path("wagtail-vega/", include((urls, "wagtail_vega"), namespace="wagtail_vega"))]
