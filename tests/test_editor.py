"""The admin code editor: the widget, its telepath adapters, and the live
spec validation endpoint."""

import json
from pathlib import Path

import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from wagtail.admin.telepath import JSContext

from wagtail_vega.blocks import DatasetBlock, JSONBlock, PastedDataBlock, SpecBlock
from wagtail_vega.validation import SpecProblem, spec_problems
from wagtail_vega.widgets import CodeEditor

from .conftest import VL

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "wagtail_vega/static/wagtail_vega/admin/vendor"


def editor_config(html):
    """The JSON config on a rendered CodeEditor textarea."""
    from html import unescape

    attr = html.split('data-wagtail-vega-code-editor="', 1)[1].split('"', 1)[0]
    return json.loads(unescape(attr))


# -- Widget -------------------------------------------------------------------


def test_widget_renders_a_textarea_with_its_config():
    html = CodeEditor(attrs={"rows": 8}, mode="data").render("paste", "a\tb", {"id": "id_paste"})
    assert html.startswith("<textarea")
    assert 'name="paste"' in html and ">\na\tb</textarea>" in html
    assert 'spellcheck="false"' in html
    assert editor_config(html) == {"mode": "data", "rows": 8}


def test_spec_mode_points_at_the_validation_endpoint():
    html = CodeEditor(mode="spec").render("spec", "{}")
    assert editor_config(html) == {
        "mode": "spec",
        "rows": 16,
        "validateUrl": reverse("wagtail_vega_validate_spec"),
    }


def test_unknown_mode():
    with pytest.raises(ValueError):
        CodeEditor(mode="python")


def test_widget_media():
    media = str(CodeEditor().media)
    for path in (
        "admin/vendor/codemirror.js",
        "admin/json-source.js",
        "admin/data-format.js",
        "admin/code-editor.js",
        "admin/code-editor.css",
    ):
        assert f"wagtail_vega/{path}" in media
    # CodeMirror and the helpers load before the editor that uses them
    assert (
        media.index("codemirror.js")
        < media.index("json-source.js")
        < media.index("data-format.js")
        < media.index("code-editor.js")
    )


def test_widget_telepath_adapter():
    ctx = JSContext()
    packed = ctx.pack(CodeEditor(mode="json"))
    assert packed["_type"] == "wagtail_vega.widgets.CodeEditor"
    html = packed["_args"][0]
    assert 'name="__NAME__"' in html and 'id="__ID__"' in html
    media = str(ctx.media)
    # Wagtail's Widget, which the editor's JS class extends, loads first
    assert media.index("wagtailadmin/js/telepath/widgets.js") < media.index("code-editor.js")


@pytest.mark.parametrize(
    "block,mode",
    [(JSONBlock(), "json"), (SpecBlock(), "spec"), (DatasetBlock().child_blocks["paste"], "data")],
)
def test_blocks_use_the_editor(block, mode):
    assert isinstance(block.field.widget, CodeEditor)
    assert block.field.widget.mode == mode


def test_json_blocks_pass_errors_to_the_editor():
    for block in (JSONBlock(), SpecBlock()):
        ctx = JSContext()
        packed = ctx.pack(block)
        assert packed["_type"] == "wagtail_vega.blocks.CodeFieldBlock"
        assert "wagtail_vega/admin/code-editor.js" in str(ctx.media)


def test_json_block_keeps_its_rows_and_class():
    widget = JSONBlock(rows=6).field.widget
    assert widget.attrs["rows"] == 6
    assert widget.attrs["class"] == "wagtail-vega-json"


def test_pasted_data_block_is_a_text_block_in_migrations():
    block = PastedDataBlock(required=False, rows=8)
    path, _args, kwargs = block.deconstruct()
    assert path == "wagtail.blocks.TextBlock"
    assert kwargs["rows"] == 8
    assert block.get_searchable_content("a,b") == ["a,b"]


def test_dataset_block_loads_the_data_helpers():
    ctx = JSContext()
    ctx.pack(DatasetBlock())
    media = str(ctx.media)
    assert media.index("data-format.js") < media.index("dataset-block.js")
    assert "code-editor.js" in media


def test_vendored_codemirror_matches_package_json():
    package = json.loads((ROOT / "package.json").read_text())
    bundled = json.loads((VENDOR / "codemirror.VERSIONS.json").read_text())
    for name, version in package["devDependencies"].items():
        if name != "esbuild":
            assert bundled[name] == version, name
    bundle = (VENDOR / "codemirror.js").read_text()
    assert bundle.startswith("/* CodeMirror 6 for wagtail-vega")
    assert "wagtailVegaCodeMirror" in bundle
    assert (VENDOR / "codemirror.LICENSE").exists()


# -- Validation ---------------------------------------------------------------

BAR = {
    "$schema": VL,
    "data": {"name": "source"},
    "mark": "bar",
    "encoding": {"x": {"field": "a", "type": "nominl"}},
}


def test_spec_problems_have_paths(vega_settings):
    vega_settings["ALLOWED_DATA_HOSTS"] = ["ok.org"]
    spec = {**BAR, "layer": [{"data": {"url": "https://evil.org/x.csv"}}]}
    problems = spec_problems(spec)
    assert problems[0].path == ("encoding", "x", "type")
    assert str(problems[0]).startswith("encoding.x.type: 'nominl' is not valid")
    assert problems[-1] == SpecProblem(
        ("layer", 0, "data", "url"), "Loading data from https://evil.org/x.csv is not allowed."
    )


def test_spec_problems_without_a_path(vega_settings):
    assert spec_problems([1]) == [SpecProblem((), "The spec must be a JSON object.")]
    (problem,) = spec_problems({"mark": "bar"})
    assert problem.path == () and str(problem).startswith('The spec needs a "$schema"')
    (problem,) = spec_problems({"$schema": "https://example.org/x.json"})
    assert problem.path == ("$schema",)


# -- Endpoint -----------------------------------------------------------------

URL = "/admin/wagtail-vega/validate-spec/"


def post(client, spec, **headers):
    body = spec if isinstance(spec, str) else json.dumps(spec)
    return client.post(URL, body, content_type="application/json", **headers)


@pytest.mark.django_db
def test_endpoint_url():
    assert reverse("wagtail_vega_validate_spec") == URL


@pytest.mark.django_db
def test_endpoint_returns_errors_with_paths(admin_client, vega_settings):
    response = post(admin_client, {**BAR, "data": {"url": "https://evil.org/x.csv"}})
    assert response.status_code == 200
    errors = response.json()["errors"]
    assert errors[0]["path"] == ["encoding", "x", "type"]
    assert errors[0]["message"].startswith("'nominl' is not valid")
    assert {
        "path": ["data", "url"],
        "message": "Loading data from https://evil.org/x.csv is not allowed.",
    } in errors


@pytest.mark.django_db
def test_endpoint_valid_spec(admin_client, vega_settings, vl_bar):
    assert post(admin_client, vl_bar).json() == {"errors": []}


@pytest.mark.django_db
def test_endpoint_matches_save_settings(admin_client, vega_settings):
    vega_settings["VALIDATE_SCHEMA"] = False
    assert post(admin_client, BAR).json() == {"errors": []}
    vega_settings["ALLOWED_DATA_HOSTS"] = ["evil.org"]
    assert post(admin_client, {**BAR, "data": {"url": "https://evil.org/x"}}).json() == {
        "errors": []
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body,status,message",
    [
        ("{oops", 400, "Enter a valid JSON."),
        (b"\xff", 400, "Enter a valid JSON."),
        ("[1, 2]", 200, "The spec must be a JSON object."),
        ('{"mark": "bar"}', 200, 'The spec needs a "$schema"'),
    ],
)
def test_endpoint_error_paths(admin_client, vega_settings, body, status, message):
    response = admin_client.post(URL, body, content_type="application/json")
    assert response.status_code == status
    (error,) = response.json()["errors"]
    assert error["path"] == [] and error["message"].startswith(message)


@pytest.mark.django_db
def test_endpoint_is_post_only(admin_client):
    assert admin_client.get(URL).status_code == 405


@pytest.mark.django_db
def test_endpoint_needs_login(client):
    response = post(client, BAR)
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]
    assert post(client, BAR, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code in (302, 403)


@pytest.mark.django_db
def test_endpoint_needs_admin_access(client, django_user_model):
    user = django_user_model.objects.create_user("reader", password="pw")
    client.force_login(user)
    assert post(client, BAR, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code == 403
    assert post(client, BAR).status_code == 302

    # Any user who can use the Wagtail admin can use it (editors and
    # moderators usually aren't Django staff)
    user.user_permissions.add(Permission.objects.get(codename="access_admin"))
    user = django_user_model.objects.get(pk=user.pk)
    client.force_login(user)
    assert post(client, BAR).status_code == 200


@pytest.mark.django_db
def test_endpoint_checks_csrf(admin_user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    assert post(client, BAR).status_code == 403

    client.get(reverse("wagtailadmin_home"))
    token = client.cookies["csrftoken"].value
    response = post(client, BAR, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200
    assert response.json()["errors"]
