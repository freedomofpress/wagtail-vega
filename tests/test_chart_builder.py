"""The server side of the chart builder: its button on the spec editor, the
document-rows endpoint it reads documents with, and that the specs it writes
pass validation.

The spec validation endpoint it also uses is tested in test_editor.py.
"""

import html
import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.files.base import ContentFile
from django.urls import NoReverseMatch, reverse
from wagtail.documents import get_document_model

from wagtail_vega.blocks import SpecBlock
from wagtail_vega.builder_strings import builder_strings
from wagtail_vega.validation import spec_problems
from wagtail_vega.widgets import CodeEditor

pytestmark = pytest.mark.django_db

Document = get_document_model()

ROWS = reverse("wagtail_vega_document_rows")
VALIDATE = reverse("wagtail_vega_validate_spec")


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def doc():
    return Document.objects.create(
        title="data", file=ContentFile(b'quarter,requests\nQ1,"1,200"\nQ2,950\n', name="d.csv")
    )


def make_user(django_user_model, username, *permissions):
    user = django_user_model.objects.create_user(username=username, password="pw")
    if permissions:
        group = Group.objects.create(name=f"{username}-group")
        for codename in permissions:
            app_label, codename = codename.split(".")
            group.permissions.add(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )
        user.groups.add(group)
    return user


@pytest.fixture
def no_admin_client(client, django_user_model):
    """Logged in, but can't access the Wagtail admin."""
    client.force_login(make_user(django_user_model, "visitor"))
    return client


@pytest.fixture
def editor_client(client, django_user_model):
    """Can access the admin, but has no document permissions."""
    client.force_login(make_user(django_user_model, "editor", "wagtailadmin.access_admin"))
    return client


# -- Document rows ---------------------------------------------------------------


def test_anonymous_users_are_sent_to_login(client):
    response = client.get(ROWS)
    assert response.status_code == 302
    assert reverse("wagtailadmin_login") in response["Location"]


def test_users_without_admin_access_are_refused(no_admin_client):
    response = no_admin_client.get(ROWS)
    assert response.status_code in (302, 403)


def test_document_rows(admin_client, doc):
    response = admin_client.get(ROWS, {"id": doc.pk})
    assert response.status_code == 200
    # Parsed and typed exactly as for the chart
    assert response.json() == {
        "rows": [{"quarter": "Q1", "requests": 1200}, {"quarter": "Q2", "requests": 950}]
    }


def test_document_rows_json_and_tsv(admin_client):
    tsv = Document.objects.create(title="t", file=ContentFile(b"a\tb\n1,500\tx\n", name="t.tsv"))
    assert admin_client.get(ROWS, {"id": tsv.pk}).json()["rows"] == [{"a": 1500, "b": "x"}]
    js = Document.objects.create(
        title="j", file=ContentFile(b'{"values": [{"a": 1}]}', name="j.json")
    )
    assert admin_client.get(ROWS, {"id": js.pk}).json()["rows"] == [{"a": 1}]


@pytest.mark.parametrize("query", [{}, {"id": ""}, {"id": "x"}])
def test_document_rows_needs_an_id(admin_client, query):
    assert admin_client.get(ROWS, query).status_code == 400


def test_document_rows_missing_document(admin_client):
    assert admin_client.get(ROWS, {"id": 999999}).status_code == 404


def test_document_rows_rejects_other_file_types(admin_client):
    pdf = Document.objects.create(title="p", file=ContentFile(b"%PDF", name="p.pdf"))
    response = admin_client.get(ROWS, {"id": pdf.pk})
    assert response.status_code == 400
    assert ".csv, .tsv or .json" in response.json()["error"]


def test_document_rows_reports_unreadable_data(admin_client):
    bad = Document.objects.create(title="b", file=ContentFile(b"[oops", name="b.json"))
    response = admin_client.get(ROWS, {"id": bad.pk})
    assert response.status_code == 400
    assert response.json()["error"].startswith("Couldn't read this data")


def test_document_rows_needs_document_permission(editor_client, doc):
    response = editor_client.get(ROWS, {"id": doc.pk})
    assert response.status_code == 403
    assert "rows" not in response.json()


def test_document_rows_with_choose_permission(client, django_user_model, doc):
    from wagtail.models import Collection, GroupCollectionPermission

    user = make_user(django_user_model, "chooser", "wagtailadmin.access_admin")
    GroupCollectionPermission.objects.create(
        group=user.groups.get(),
        collection=Collection.get_first_root_node(),
        permission=Permission.objects.get(
            content_type__app_label="wagtaildocs", codename="choose_document"
        ),
    )
    client.force_login(user)
    assert client.get(ROWS, {"id": doc.pk}).status_code == 200


def test_document_rows_is_get_only(admin_client, doc):
    assert admin_client.post(ROWS, {"id": doc.pk}).status_code == 405


def test_voyager_is_gone():
    """Voyager's page and files were removed with the builder that replaced it."""
    with pytest.raises(NoReverseMatch):
        reverse("wagtail_vega_voyager")
    static = Path(__file__).parent.parent / "wagtail_vega" / "static" / "wagtail_vega"
    assert not (static / "vendor" / "voyager").exists()
    assert not list(static.rglob("voyager*"))


# -- The button ----------------------------------------------------------------------


def render_spec_field(block):
    return block.field.widget.render("spec", "{}", {"id": "spec"})


def builder_config(markup):
    start = markup.index('data-config="') + len('data-config="')
    return json.loads(html.unescape(markup[start : markup.index('"', start)]))


def test_spec_widget_has_builder_button(vega_settings):
    vega_settings["ALLOWED_DATA_HOSTS"] = ["data.example.org"]
    markup = render_spec_field(SpecBlock())
    assert "<wagtail-vega-chart-builder" in markup
    assert 'data-for="spec"' in markup
    assert "Edit chart" in markup
    config = builder_config(markup)
    assert config["rowsUrl"] == ROWS
    assert config["validateUrl"] == VALIDATE
    assert config["allowedHosts"] == ["data.example.org"]
    # The preview's libraries load when the builder first opens
    assert config["scripts"] == [
        "/static/wagtail_vega/vendor/vega.min.js",
        "/static/wagtail_vega/vendor/vega-lite.min.js",
        "/static/wagtail_vega/vendor/vega-embed.min.js",
        "/static/wagtail_vega/wagtail-vega.js",
    ]
    assert config["stylesheet"] == "/static/wagtail_vega/wagtail-vega.css"
    assert config["embedOptions"] == {"actions": False, "renderer": "svg"}


def test_builder_config_has_the_themes():
    """The preview uses the chart's theme, as the page will. (The test
    project's themes, from tests/settings.py.)"""
    config = builder_config(render_spec_field(SpecBlock()))
    assert config["defaultTheme"] == "house"
    house = config["themes"]["house"]
    assert house["config"]["font"] == "Georgia, serif"
    assert house["dark"]["title"] == {"color": "#fff"}
    assert house["fallbacks"] == {"--brand": "#c0392b"}
    assert config["themes"]["538"]["vega_theme"] == "fivethirtyeight"


def test_builder_config_without_themes(vega_settings):
    vega_settings["THEMES"] = {}
    vega_settings["DEFAULT_THEME"] = None
    config = builder_config(render_spec_field(SpecBlock()))
    assert config["themes"] == {}
    assert config["defaultTheme"] is None


def test_spec_widget_is_the_code_editor():
    """The field is still the code editor's textarea, first, because Wagtail
    gives a widget's first element the field's aria-describedby and required,
    which the code editor copies. The editor is told it's shown in the chart
    editor's dialog rather than inline."""
    widget = SpecBlock().field.widget
    assert isinstance(widget, CodeEditor) and widget.mode == "spec" and widget.builder
    assert widget.get_config()["builder"] is True
    markup = render_spec_field(SpecBlock()).strip()
    assert markup.startswith("<textarea")
    assert "data-wagtail-vega-code-editor=" in markup
    assert "&quot;builder&quot;: true" in markup
    assert markup.index("</textarea>") < markup.index("<wagtail-vega-chart-builder")
    # The field: a preview, its problems and the button; no inline JSON
    for part in ("data-field-preview", "data-field-problems", "data-builder-open"):
        assert part in markup
    assert "Use this chart" not in markup


def test_json_blocks_keep_the_inline_editor():
    assert "builder" not in CodeEditor(mode="json").get_config()
    assert "builder" not in SpecBlock(builder=False).field.widget.get_config()


def test_spec_widget_without_builder():
    widget = SpecBlock(builder=False).field.widget
    assert isinstance(widget, CodeEditor) and not widget.builder
    markup = render_spec_field(SpecBlock(builder=False))
    assert "wagtail-vega-chart-builder" not in markup
    assert "data-wagtail-vega-code-editor=" in markup
    assert "chart-builder" not in str(widget.media)


@pytest.mark.parametrize(
    ("value", "first"), [("", True), ("null", True), ("  ", True), ('{"a": 1}', False)]
)
def test_builder_is_the_main_action_for_an_empty_spec(value, first):
    markup = SpecBlock().field.widget.render("spec", value, {"id": "spec"})
    button = markup[markup.index("<button") : markup.index(">", markup.index("<button"))]
    assert ("button-secondary" not in button) is first
    assert ("is-empty" in markup) is first
    prompt = markup[
        markup.index("data-field-empty") : markup.index("</p>", markup.index("data-field-empty"))
    ]
    assert ("hidden" in prompt) is not first
    assert "without writing JSON" in prompt
    preview = markup[markup.index("data-field-preview") :]
    assert preview.startswith("data-field-preview hidden") is first


ADMIN_STATIC = Path(__file__).parent.parent / "wagtail_vega" / "static" / "wagtail_vega" / "admin"


def js_keys():
    """Every string key chart-builder.js and chart-spec.js look up."""
    builder = (ADMIN_STATIC / "chart-builder.js").read_text()
    spec = (ADMIN_STATIC / "chart-spec.js").read_text()
    keys = set(re.findall(r'\bt\("([\w.]+)"', builder))
    keys |= set(re.findall(r'key: "([\w.]+)"', spec))
    keys |= {f"suggest.{k}" for k in re.findall(r'\badd\("(\w+)"', spec)}

    def values(name):
        match = re.search(rf"const {name} = \[(.*?)\];", spec, re.S)
        return re.findall(r'"(\w*)"', match.group(1))

    for prefix, name in [
        ("mark", "MARKS"),
        ("type", "TYPES"),
        ("aggregate", "AGGREGATES"),
        ("timeUnit", "TIME_UNITS"),
        ("channel", "CHANNELS"),
        ("channelTitle", "CHANNELS"),
        ("columnType", "TYPES"),
    ]:
        keys |= {f"{prefix}.{v}" for v in values(name)}
    keys |= {f"channelShort.{v}" for v in values("SORT_CHANNELS")}
    arrangements = re.search(r"const ARRANGEMENTS = \[(.*?)\n  \];", spec, re.S).group(1)
    keys |= {f"arrangement.{v or 'stacked'}" for v in re.findall(r'\["(\w*)", \[', arrangements)}
    keys |= {"arrangementHint.bar", "arrangementHint.area"}
    return keys


def test_every_builder_string_is_translatable():
    """The builder's scripts have no English of their own: every key they
    use comes from builder_strings(), which uses gettext."""
    strings = builder_strings()
    missing = js_keys() - set(strings)
    assert not missing
    assert len(js_keys()) > 150
    config = builder_config(render_spec_field(SpecBlock()))
    assert config["strings"] == strings


def test_builder_strings_are_translated(settings):
    from django.utils import translation

    with translation.override("de"):
        strings = builder_strings()
    # No German catalogue ships yet, but the strings go through gettext
    assert strings["undo"] == "Undo changes since opening"
    with patch("wagtail_vega.builder_strings._", lambda s: f"[{s}]"):
        assert builder_strings()["undo"] == "[Undo changes since opening]"


def test_js_strings_fixture_is_current():
    """tests/js/ checks messages against the English strings in this fixture.
    Run with UPDATE_FIXTURES=1 to rewrite it after changing builder_strings.py."""
    fixture = Path(__file__).parent / "js" / "fixtures" / "builder-strings.json"
    if os.environ.get("UPDATE_FIXTURES"):
        fixture.write_text(json.dumps(builder_strings(), indent=2, ensure_ascii=False) + "\n")
    assert json.loads(fixture.read_text()) == builder_strings()


def test_builder_needs_spec_mode():
    assert not CodeEditor(mode="json", builder=True).builder
    assert "wagtail-vega-chart-builder" not in CodeEditor(mode="json", builder=True).render(
        "x", "{}"
    )


def test_spec_widget_media():
    media = str(SpecBlock().field.widget.media)
    assert "wagtail_vega/admin/chart-spec.js" in media
    assert "wagtail_vega/admin/chart-builder.js" in media
    assert "wagtail_vega/admin/chart-builder.css" in media
    # The builder reads pasted data and infers types with data-format.js,
    # part of the editor
    assert media.index("data-format.js") < media.index("chart-spec.js")
    assert media.index("chart-spec.js") < media.index("chart-builder.js")
    # The Vega libraries aren't loaded with the edit page
    assert "vega.min.js" not in media


def test_edit_page_includes_the_builder(admin_client):
    from wagtail.models import Site

    from tests.testapp.models import ChartPage

    home = Site.objects.get(is_default_site=True).root_page
    page = home.add_child(instance=ChartPage(title="c", slug="c", body=[]))
    response = admin_client.get(reverse("wagtailadmin_pages:edit", args=(page.pk,)))
    markup = response.content.decode()
    assert "wagtail_vega/admin/chart-builder.js" in markup
    assert "wagtail-vega-chart-builder" in markup
    assert "vendor/voyager" not in markup


# -- The specs it writes ----------------------------------------------------------------

FIXTURES = json.loads((Path(__file__).parent / "js/fixtures/chart-specs.json").read_text())
SPECS = [(f["name"], f["expected"]) for f in FIXTURES["charts"]] + [
    (f["name"], f["spec"]) for f in FIXTURES["roundTrip"]
]


@pytest.mark.parametrize("spec", [s for _, s in SPECS], ids=[n for n, _ in SPECS])
def test_builder_specs_are_valid(spec, vega_settings):
    """tests/js/chart-spec.test.mjs checks that the builder writes each of
    these specs (and opens and writes back the round-trip ones unchanged);
    here each must pass the checks that saving the page runs, the Vega-Lite
    schema included."""
    assert spec["data"] == {"name": "source"}
    assert "datasets" not in spec
    assert spec_problems(spec) == []
