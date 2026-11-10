"""Tests that go through the Wagtail admin: create, validate, preview, serve."""

import io
import json

import pytest
from django.urls import reverse
from wagtail.models import Site
from wagtail.test.utils.form_data import nested_form_data, streamfield

from tests.testapp.models import ChartPage

from .conftest import VL

pytestmark = pytest.mark.django_db

BAR = {
    "$schema": VL,
    "data": {"name": "source"},
    "mark": "bar",
    "encoding": {
        "x": {"field": "quarter", "type": "nominal"},
        "y": {"field": "requests", "type": "quantitative"},
    },
}


def list_block(items):
    """Form data for a ListBlock (like wagtail's ``streamfield`` helper)."""
    data = {
        str(i): {"value": value, "deleted": "", "order": str(i), "id": ""}
        for i, value in enumerate(items)
    }
    data["count"] = str(len(items))
    return data


def dataset(name="source", source_type="paste", paste="", document="", url="", format=""):
    return {
        "name": name,
        "source_type": source_type,
        "paste": paste,
        "document": document,
        "url": url,
        "format": format,
    }


SOURCE = "quarter\trequests\nQ1\t1,200\nQ2\t950"


def chart(spec=BAR, data=None, description="", caption="", theme=""):
    if data is None:  # the dataset BAR loads
        data = [dataset(paste=SOURCE)]
    return {
        "spec": json.dumps(spec) if isinstance(spec, dict) else spec,
        "data": list_block(list(data)),
        "description": description,
        "caption": caption,
        "theme": theme,
    }


def page_form(*blocks, title="Charts", slug="charts", publish=True):
    data = nested_form_data(
        {"title": title, "slug": slug, "body": streamfield([("chart", b) for b in blocks])}
    )
    if publish:
        data["action-publish"] = "publish"
    return data


@pytest.fixture
def home():
    return Site.objects.get(is_default_site=True).root_page


@pytest.fixture
def add_url(home):
    return reverse("wagtailadmin_pages:add", args=("testapp", "chartpage", home.pk))


def test_create_and_serve_chart_page(admin_client, add_url):
    form = page_form(
        chart(
            data=[dataset(paste="quarter\trequests\nQ1\t1,200\nQ2\t950")],
            description="Requests per quarter",
            caption="Source: FOIA logs",
        )
    )
    response = admin_client.post(add_url, form)
    assert response.status_code == 302, response.content[:2000]

    page = ChartPage.objects.get(slug="charts")
    assert page.live
    value = page.body[0].value
    assert value["spec"] == BAR
    assert value["data"][0]["source_type"] == "paste"

    html = admin_client.get(page.url).content.decode()
    assert "<wagtail-vega-chart" in html
    assert "Requests per quarter" in html and "Source: FOIA logs" in html
    payload = json.loads(html.split('type="application/json">', 1)[1].split("</script>", 1)[0])
    assert payload["spec"]["datasets"]["source"] == [
        {"quarter": "Q1", "requests": 1200},
        {"quarter": "Q2", "requests": 950},
    ]


@pytest.mark.parametrize(
    "block,message",
    [
        (chart(spec="{not json"), "Enter a valid JSON"),
        (chart(spec={**BAR, "mark": "barr"}), "is not valid under any of the given schemas"),
        (chart(spec={"mark": "bar"}), "The spec needs a"),
        (chart(data=[dataset(paste="")]), "Paste a header row"),
        (chart(data=[dataset(source_type="document")]), "Select a document to load data from"),
        (
            chart(data=[dataset(source_type="url", url="https://evil.example/x.csv")]),
            "can't be loaded from this host",
        ),
        (
            chart(data=[dataset(paste="a\n1"), dataset(paste="a\n2")]),
            "Dataset names must be unique",
        ),
        (chart(data=[dataset(name="has space", paste="a\n1")]), "Use letters, numbers"),
        (chart(data=[]), 'This chart has no dataset called "source". Add one under Data.'),
        (
            chart(data=[dataset(name="sales", paste="a\n1")]),
            'This chart has no dataset called "source". Use one of its datasets (sales)',
        ),
    ],
)
def test_validation_errors_are_shown(admin_client, add_url, block, message):
    response = admin_client.post(add_url, page_form(block))
    assert response.status_code == 200
    assert not ChartPage.objects.exists()
    # Block errors are passed to the StreamField JS as JSON, so quotes and
    # apostrophes may be escaped.
    content = response.content.decode()
    for escaped, char in [("\\u0027", "'"), ("&#x27;", "'"), ("\\u0022", '"'), ("&quot;", '"')]:
        content = content.replace(escaped, char)
    content = content.replace('\\"', '"')
    assert message in content


def test_allowlisted_url_dataset(admin_client, add_url):
    form = page_form(
        chart(
            data=[
                dataset(
                    source_type="url",
                    url="https://vega.github.io/vega-datasets/data/cars.json",
                    format="json",
                    paste="stale,should,be,dropped",
                )
            ]
        )
    )
    assert admin_client.post(add_url, form).status_code == 302
    item = ChartPage.objects.get().body[0].value["data"][0]
    assert item["url"].startswith("https://vega.github.io/")
    assert not item["paste"]


def test_edit_view_loads_admin_assets_and_theme_labels(admin_client, add_url):
    assert admin_client.post(add_url, page_form(chart(), publish=False)).status_code == 302
    page = ChartPage.objects.get()
    html = admin_client.get(reverse("wagtailadmin_pages:edit", args=(page.pk,))).content.decode()
    assert "wagtail_vega/admin/dataset-block.js" in html
    assert "wagtail_vega/admin/dataset-block.css" in html
    assert "wagtail_vega.blocks.DatasetBlock" in html
    assert "Site default (House style)" in html
    assert "Detect from the URL" in html


def test_chart_icon_is_registered(admin_client):
    html = admin_client.get(reverse("wagtailadmin_home")).content.decode()
    sprite_url = html.split('data-icon-url="', 1)[1].split('"', 1)[0]
    assert "icon-wagtail-vega-chart" in admin_client.get(sprite_url).content.decode()


def test_preview_renders_chart(admin_client, add_url):
    assert admin_client.post(add_url, page_form(chart(), publish=False)).status_code == 302
    page = ChartPage.objects.get()
    preview_url = reverse("wagtailadmin_pages:preview_on_edit", args=(page.pk,))
    form = page_form(
        chart(data=[dataset(paste="quarter,requests\nQ9,42")], description="Preview me"),
        publish=False,
    )
    assert admin_client.post(preview_url, form).json()["is_valid"]
    html = admin_client.get(preview_url).content.decode()
    assert "<wagtail-vega-chart" in html and "Preview me" in html
    assert '"Q9"' in html


# -- Wagtail API (#9) -------------------------------------------------------------


def test_api_representation(client, home):
    import datetime
    from decimal import Decimal

    from tests.testapp.models import Donation

    Donation.objects.create(month=datetime.date(2026, 1, 1), total=Decimal("12.50"))
    donations_spec = {**BAR, "data": {"name": "donations"}}
    page = home.add_child(
        instance=ChartPage(
            title="API",
            slug="api",
            body=[
                (
                    "chart",
                    {
                        "spec": BAR,
                        "data": [
                            {
                                "name": "source",
                                "source_type": "paste",
                                "paste": "quarter,requests\nQ1,5",
                            }
                        ],
                        "description": "Requests",
                        "caption": "FOIA logs",
                        "theme": "",
                    },
                ),
                ("donations_chart", {"spec": donations_spec, "description": "", "caption": ""}),
            ],
        )
    )
    response = client.get(f"/api/v2/pages/{page.pk}/")
    assert response.status_code == 200
    chart, donations = (block["value"] for block in response.json()["body"])

    # The final spec, ready for vega-embed: data injected, theme merged
    assert chart["kind"] == "vega-lite"
    assert chart["spec"]["datasets"]["source"] == [{"quarter": "Q1", "requests": 5}]
    assert chart["spec"]["config"]["font"] == "Georgia, serif"  # the test project's theme
    assert chart["darkConfig"]["axis"]["labelColor"] == "#ddd"
    assert chart["embed"]["defaultStyle"] is False
    assert chart["description"] == "Requests" and chart["caption"] == "FOIA logs"
    assert "vega.github.io" in chart["allowedHosts"]
    # Data from code, JSON-encoded the same way as on the page
    assert donations["spec"]["datasets"]["donations"] == [{"month": "2026-01-01", "total": 12.5}]
    # The raw editor input isn't exposed
    assert "paste" not in json.dumps(chart)


def test_javascript_catalogue(admin_client, client):
    """The admin scripts' translations (#8): Django's JavaScriptCatalog for
    wagtail_vega, admin only."""
    url = reverse("wagtail_vega_jsi18n")
    response = admin_client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/javascript")
    assert b"django.catalog" in response.content
    assert client.get(url).status_code == 302  # login required


def test_edit_page_loads_the_catalogue_before_admin_scripts(admin_client, add_url):
    assert admin_client.post(add_url, page_form(chart(), publish=False)).status_code == 302
    page = ChartPage.objects.get()
    html = admin_client.get(reverse("wagtailadmin_pages:edit", args=(page.pk,))).content.decode()
    catalogue = html.index(reverse("wagtail_vega_jsi18n"))
    assert catalogue < html.index("wagtail_vega/admin/data-format.js")
    assert catalogue < html.index("wagtail_vega/admin/json-source.js")


def test_seed_sandbox_can_run_again(db):
    """Re-seeding replaces the demo page even though it's the site's root
    (deleting it used to delete the Site, and the second run failed)."""
    from django.core.management import call_command
    from wagtail.models import Site

    call_command("seed_sandbox", stdout=io.StringIO())
    call_command("seed_sandbox", stdout=io.StringIO())
    site = Site.objects.get(is_default_site=True)
    assert site.root_page.specific.title == "Chart examples"
    assert ChartPage.objects.count() >= 1
