"""The admin endpoints and widget behind "Build chart with Voyager"."""

import json
from pathlib import Path

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.files.base import ContentFile
from django.test import Client
from django.urls import reverse
from wagtail.documents import get_document_model

from wagtail_vega.blocks import SpecBlock
from wagtail_vega.validation import spec_errors
from wagtail_vega.views import FRAME_CSP

from .conftest import VL

pytestmark = pytest.mark.django_db

Document = get_document_model()

FRAME = reverse("wagtail_vega:voyager")
ROWS = reverse("wagtail_vega:document_rows")
VALIDATE = reverse("wagtail_vega:validate_spec")


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


def post_spec(client, spec, **extra):
    return client.post(
        VALIDATE, json.dumps({"spec": spec}), content_type="application/json", **extra
    )


# -- Access ------------------------------------------------------------------


@pytest.mark.parametrize("url", [FRAME, ROWS, VALIDATE])
def test_anonymous_users_are_sent_to_login(client, url):
    response = client.get(url)
    assert response.status_code == 302
    assert reverse("wagtailadmin_login") in response["Location"]


@pytest.mark.parametrize("url", [FRAME, ROWS, VALIDATE])
def test_users_without_admin_access_are_refused(no_admin_client, url):
    response = no_admin_client.get(url)
    assert response.status_code in (302, 403)
    assert response.status_code != 200


# -- The Voyager page ----------------------------------------------------------


def test_voyager_page(admin_client):
    response = admin_client.get(FRAME)
    assert response.status_code == 200
    # Sandboxed even if opened outside the lightbox's iframe
    assert response["Content-Security-Policy"] == FRAME_CSP == "sandbox allow-scripts"
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    html = response.content.decode()
    assert "wagtail_vega/vendor/voyager/voyager.js" in html
    assert "wagtail_vega/vendor/voyager/voyager.css" in html
    assert "wagtail_vega/admin/voyager-frame.js" in html
    # Isolated from the admin's own scripts and styles
    assert "wagtailadmin" not in html


def test_voyager_page_is_get_only(admin_client):
    assert admin_client.post(FRAME).status_code == 405


def test_voyager_page_for_editors(editor_client):
    assert editor_client.get(FRAME).status_code == 200


# -- Document rows ---------------------------------------------------------------


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


# -- Spec validation ---------------------------------------------------------------


def test_validate_spec(admin_client, vl_bar):
    response = post_spec(admin_client, vl_bar)
    assert response.status_code == 200
    assert response.json() == {"errors": []}


@pytest.mark.parametrize(
    "spec,message",
    [
        ({"mark": "bar"}, '"$schema"'),
        ([], "must be a JSON object"),
        ({"$schema": VL, "mark": "nope"}, "nope"),
        ({"$schema": VL, "data": {"url": "https://evil.example/x.csv"}, "mark": "bar"}, "evil"),
    ],
)
def test_validate_spec_errors(admin_client, vega_settings, spec, message):
    errors = post_spec(admin_client, spec).json()["errors"]
    assert errors and message in " ".join(errors)


def test_validate_spec_matches_spec_block(admin_client, vega_settings):
    """The endpoint runs the same checks as saving the page."""
    from django.core.exceptions import ValidationError

    spec = {"$schema": VL, "data": {"url": "https://evil.example/x.csv"}, "mark": "bar"}
    with pytest.raises(ValidationError) as e:
        SpecBlock().clean(spec)
    assert post_spec(admin_client, spec).json()["errors"] == e.value.messages


@pytest.mark.parametrize("body", ["not json", "[]", '{"no": "spec"}'])
def test_validate_spec_bad_request(admin_client, body):
    response = admin_client.post(VALIDATE, body, content_type="application/json")
    assert response.status_code == 400


def test_validate_spec_is_post_only(admin_client):
    assert admin_client.get(VALIDATE).status_code == 405


def test_validate_spec_needs_csrf_token(admin_user, vl_bar):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    assert post_spec(client, vl_bar).status_code == 403

    # With the token (as the admin's JS sends it)
    client.get(reverse("wagtailadmin_home"))
    token = client.cookies["csrftoken"].value
    response = post_spec(client, vl_bar, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200
    assert response.json() == {"errors": []}


# -- The widget ----------------------------------------------------------------------


def render_spec_field(block):
    return block.field.widget.render("spec", "{}", {"id": "spec"})


def test_spec_widget_has_voyager_button(vega_settings):
    vega_settings["ALLOWED_DATA_HOSTS"] = ["data.example.org"]
    html = render_spec_field(SpecBlock())
    assert "<wagtail-vega-voyager" in html
    assert f'data-frame-url="{FRAME}"' in html
    assert f'data-rows-url="{ROWS}"' in html
    assert f'data-validate-url="{VALIDATE}"' in html
    assert 'data-allowed-hosts="[&quot;data.example.org&quot;]"' in html
    assert 'name="spec"' in html and "<textarea" in html
    assert "Build chart with Voyager" in html


def test_spec_widget_without_voyager():
    html = render_spec_field(SpecBlock(voyager=False))
    assert "wagtail-vega-voyager" not in html
    assert "<textarea" in html


def test_spec_widget_media():
    media = str(SpecBlock().field.widget.media)
    assert "wagtail_vega/admin/voyager-launcher.js" in media
    assert "wagtail_vega/admin/voyager-launcher.css" in media
    # Voyager's own assets load only inside its iframe
    assert "vendor/voyager" not in media


def test_spec_widget_without_admin_urls(settings):
    """Rendering outside a project with the admin URLs leaves the button out."""
    settings.ROOT_URLCONF = "tests.urls_no_admin"
    from django.urls import clear_url_caches

    clear_url_caches()
    try:
        html = render_spec_field(SpecBlock())
    finally:
        clear_url_caches()
    assert "wagtail-vega-voyager" not in html
    assert "<textarea" in html


def test_edit_page_includes_launcher(admin_client):
    from wagtail.models import Site

    from tests.testapp.models import ChartPage

    home = Site.objects.get(is_default_site=True).root_page
    page = home.add_child(instance=ChartPage(title="c", slug="c", body=[]))
    response = admin_client.get(reverse("wagtailadmin_pages:edit", args=(page.pk,)))
    html = response.content.decode()
    assert "wagtail_vega/admin/voyager-launcher.js" in html
    assert "wagtail-vega-voyager" in html


# -- Spec conversion fixtures ------------------------------------------------------

FIXTURES = json.loads((Path(__file__).parent / "js/fixtures/voyager-specs.json").read_text())


@pytest.mark.parametrize("fixture", FIXTURES, ids=[f["name"] for f in FIXTURES])
def test_converted_specs_are_valid_v6(fixture, vega_settings):
    """tests/js/voyager-launcher.test.mjs checks that fromVoyagerSpec turns each
    Voyager spec into "expected"; here every "expected" spec must pass the
    checks that saving the page runs."""
    spec = fixture["expected"]
    assert spec["$schema"] == VL
    assert spec["data"] == {"name": fixture["dataset"]}
    assert spec_errors(spec) == []
