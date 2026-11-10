"""The server side of the chart editor's Voyager mode: Voyager's sandboxed,
admin-only page and its CSP, the VISUAL_EDITOR setting, the widget's
settings for it, and that the specs it converts pass validation.

The conversion itself is tested in tests/js/voyager-spec.test.mjs, and
Voyager in the browser in tests/e2e/test_voyager.py.
"""

import html
import json
from pathlib import Path

import pytest
from django.core import checks
from django.urls import reverse
from wagtail.admin.telepath import JSContext

from wagtail_vega.blocks import SpecBlock
from wagtail_vega.checks import check_visual_editor
from wagtail_vega.validation import spec_problems
from wagtail_vega.views import frame_csp

from .conftest import VL
from .test_chart_builder import builder_config, make_user, render_spec_field

pytestmark = pytest.mark.django_db

FRAME = reverse("wagtail_vega_voyager")
STATIC = Path(__file__).parent.parent / "wagtail_vega" / "static" / "wagtail_vega"


def csp_directives(response):
    return [d.strip() for d in response["Content-Security-Policy"].split(";")]


# -- Access ----------------------------------------------------------------------


def test_anonymous_users_are_sent_to_login(client):
    response = client.get(FRAME)
    assert response.status_code == 302
    assert reverse("wagtailadmin_login") in response["Location"]


def test_users_without_admin_access_are_refused(client, django_user_model):
    client.force_login(make_user(django_user_model, "visitor"))
    response = client.get(FRAME)
    assert response.status_code in (302, 403)


def test_editors_can_use_it(client, django_user_model):
    client.force_login(make_user(django_user_model, "editor", "wagtailadmin.access_admin"))
    assert client.get(FRAME).status_code == 200


def test_get_only(admin_client):
    assert admin_client.post(FRAME).status_code == 405


# -- The page and its CSP ----------------------------------------------------------


def test_voyager_page(admin_client):
    response = admin_client.get(FRAME)
    assert response.status_code == 200
    # Sandboxed even if opened outside the editor's iframe, and cut off
    # from the network: the admin page passes the data in
    csp = csp_directives(response)
    assert csp[0] == "sandbox allow-scripts"
    assert "default-src 'none'" in csp
    assert "connect-src 'none'" in csp
    assert "form-action 'none'" in csp
    assert "base-uri 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    assert "script-src 'self' 'unsafe-eval'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data: blob:" in csp
    assert "font-src 'self' data:" in csp
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    markup = response.content.decode()
    assert "/static/wagtail_vega/vendor/voyager/voyager.js" in markup
    assert "/static/wagtail_vega/vendor/voyager/voyager.css" in markup
    assert "/static/wagtail_vega/admin/voyager-frame.js" in markup
    # Isolated from the admin's own scripts and styles
    assert "wagtailadmin" not in markup
    # Its text, translated on the server
    start = markup.index('data-strings="') + len('data-strings="')
    strings = json.loads(html.unescape(markup[start : markup.index('"', start)]))
    assert strings["notLoaded"] == "Voyager didn't load."


def test_static_files_on_another_origin(admin_client, settings):
    """With static files on a CDN, the page may load them from there (and
    still nothing else)."""
    settings.STATIC_URL = "https://cdn.example.org/static/"
    response = admin_client.get(FRAME)
    csp = csp_directives(response)
    assert "script-src https://cdn.example.org 'unsafe-eval'" in csp
    assert "style-src https://cdn.example.org 'unsafe-inline'" in csp
    assert "img-src https://cdn.example.org data: blob:" in csp
    assert "font-src https://cdn.example.org data:" in csp
    assert "connect-src 'none'" in csp
    assert "default-src 'none'" in csp
    assert "https://cdn.example.org/static/wagtail_vega/vendor/voyager/voyager.js" in (
        response.content.decode()
    )
    assert frame_csp() == response["Content-Security-Policy"]


def test_language(admin_client):
    response = admin_client.get(FRAME)
    assert '<html lang="en' in response.content.decode()


# -- The VISUAL_EDITOR setting ----------------------------------------------------------


def test_voyager_is_the_default(vega_settings):
    vega_settings.pop("VISUAL_EDITOR", None)
    config = builder_config(render_spec_field(SpecBlock()))
    assert config["visualEditor"] == "voyager"
    assert config["voyager"] == {"frameUrl": FRAME}
    assert check_visual_editor() == []


def test_simple_by_setting(vega_settings):
    vega_settings["VISUAL_EDITOR"] = "simple"
    config = builder_config(render_spec_field(SpecBlock()))
    assert config["visualEditor"] == "simple"
    # Voyager is still there to choose
    assert config["voyager"] == {"frameUrl": FRAME}
    assert check_visual_editor() == []


def test_unknown_visual_editor_is_reported(vega_settings):
    vega_settings["VISUAL_EDITOR"] = "fancy"
    [error] = check_visual_editor()
    assert isinstance(error, checks.Error)
    assert error.id == "wagtail_vega.E003"
    assert "'fancy'" in error.msg
    # ...and means the default meanwhile
    assert builder_config(render_spec_field(SpecBlock()))["visualEditor"] == "voyager"


# -- The widget ----------------------------------------------------------------------


def test_widget_media():
    media = str(SpecBlock().field.widget.media)
    for name in ("voyager-spec.js", "voyager-editor.js"):
        assert f"wagtail_vega/admin/{name}" in media
        assert media.index(name) < media.index("chart-builder.js")
    # Voyager itself only loads in its iframe, when it's first shown
    assert "vendor/voyager" not in media
    assert "voyager-frame" not in media


def test_telepath_adapter_carries_the_settings(vega_settings):
    """Blocks added in the browser are rendered from telepath's packed
    widget: it has the same settings, Voyager's included."""
    vega_settings["VISUAL_EDITOR"] = "simple"
    ctx = JSContext()
    packed = ctx.pack(SpecBlock())
    markup = json.dumps(packed)
    assert "wagtail-vega-chart-builder" in markup
    assert "visualEditor" in markup and "simple" in markup
    assert FRAME in markup
    media = str(ctx.media)
    assert "voyager-editor.js" in media
    assert "vendor/voyager" not in media


def test_edit_page_doesnt_load_voyager(admin_client):
    from wagtail.models import Site

    from tests.testapp.models import ChartPage

    home = Site.objects.get(is_default_site=True).root_page
    page = home.add_child(instance=ChartPage(title="c", slug="c", body=[]))
    markup = admin_client.get(reverse("wagtailadmin_pages:edit", args=(page.pk,))).content.decode()
    assert "wagtail_vega/admin/voyager-editor.js" in markup
    assert "vendor/voyager" not in markup


def test_vendored_voyager_is_shipped():
    voyager = STATIC / "vendor" / "voyager"
    assert {p.name for p in voyager.iterdir()} == {"voyager.js", "voyager.css", "LICENSES.txt"}
    assert (voyager / "voyager.js").read_text().startswith("/* Vega Voyager")
    assert "datavoyager@2.0.0-alpha.24" in (voyager / "LICENSES.txt").read_text()
    # The icon font is inlined: the sandboxed page couldn't load it without CORS
    css = (voyager / "voyager.css").read_text()
    assert "url(data:font/woff2;base64," in css
    assert "fontawesome-webfont" not in css


# -- The specs it writes -------------------------------------------------------------------

FIXTURES = json.loads((Path(__file__).parent / "js/fixtures/voyager-specs.json").read_text())


@pytest.mark.parametrize("fixture", FIXTURES, ids=[f["name"] for f in FIXTURES])
def test_converted_specs_are_valid_v6(fixture, vega_settings):
    """tests/js/voyager-spec.test.mjs checks that fromVoyagerSpec turns each
    Voyager spec into "expected"; here every "expected" spec must pass the
    checks that saving the page runs."""
    spec = fixture["expected"]
    assert spec["$schema"] == VL
    assert spec["data"] == {"name": fixture["dataset"]}
    assert "values" not in json.dumps(spec)
    assert spec_problems(spec) == []
