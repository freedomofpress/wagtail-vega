"""Custom dataset source types (#34), in the real admin: the test project's
DonationsDatasetBlock adds "donations" (with a rows URL), "sample"
(registered in the browser by sample-source.js) and "totals" (neither)."""

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest
from django.urls import reverse
from playwright.sync_api import expect

from tests.testapp.demo import create_demo_page, custom_source_chart
from tests.testapp.middleware import DATABASE_LOCK
from tests.testapp.models import ChartPage

from .editor import fill_editor, set_externally

pytestmark = pytest.mark.e2e

DATASET = ".wagtail-vega-dataset"
DIALOG = "dialog.wagtail-vega-builder"
SOURCE_FIELDS = ("paste", "document", "url", "format", "year", "group_by", "points")
CANT_PREVIEW = (
    "“donations” can't be previewed here: data from Yearly totals is only loaded on the site."
)


@pytest.fixture
def custom_page(transactional_db, vega_settings):
    """A page with one chart whose "donations" dataset comes from the
    Donation model (2026: Q1 and Q2), as the site root."""
    return create_demo_page(body=[custom_source_chart()])


@pytest.fixture
def editor(admin_page, live_server, custom_page):
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(custom_page.pk,)))
    expect(admin_page.locator(DATASET)).to_have_count(1)
    return admin_page


def field(scope, name):
    return scope.locator(f'[data-contentpath="{name}"]').first


def dataset(page):
    return page.locator(DATASET).first


def choose_source(page, label):
    field(dataset(page), "source_type").get_by_text(label, exact=True).click()


def assert_visible_fields(page, *names):
    for name in SOURCE_FIELDS:
        if name in names:
            expect(field(dataset(page), name)).to_be_visible()
        else:
            expect(field(dataset(page), name)).to_be_hidden()


def rows_summary(page):
    return dataset(page).locator('[data-wagtail-vega-rows-summary="donations"]')


def spec_field(page):
    return page.locator('[data-contentpath="spec"]').first


def open_builder(page):
    page.locator("wagtail-vega-chart-builder button").first.click()
    dialog = page.locator(DIALOG)
    expect(dialog).to_be_visible()
    return dialog


def builder_spec(page):
    return json.loads(spec_field(page).locator("textarea").input_value())


def test_custom_source_fields_follow_the_toggle(editor, console_errors):
    """The toggle shows each source's fields from the block's source_fields,
    with no script of the project's own."""
    assert_visible_fields(editor, "year", "group_by")
    choose_source(editor, "Paste")
    assert_visible_fields(editor, "paste")
    choose_source(editor, "Sample")
    assert_visible_fields(editor, "points")
    choose_source(editor, "Yearly totals")
    assert_visible_fields(editor)
    choose_source(editor, "URL")
    assert_visible_fields(editor, "url", "format")
    choose_source(editor, "Donations")
    assert_visible_fields(editor, "year", "group_by")
    # The custom fields come straight after the toggle (field_order)
    paths = (
        dataset(editor)
        .locator("[data-contentpath]")
        .evaluate_all("(els) => els.map((el) => el.dataset.contentpath)")
    )
    assert paths[:5] == ["name", "source_type", "year", "group_by", "points"]
    assert console_errors == []


def test_rows_summary_comes_from_the_rows_url(editor, console_errors):
    summary = rows_summary(editor)
    expect(summary).to_have_text("✓ 2 rows · quarter (text), total (number)")
    expect(summary).not_to_have_class(re.compile(r"\bis-error\b"))

    # Its fields are sent as query parameters, repeated for several values
    with editor.expect_request(lambda r: "donation-rows" in r.url and "month" in r.url) as request:
        field(dataset(editor), "group_by").get_by_label("Month").check()
    query = parse_qs(urlparse(request.value.url).query)
    assert query == {"year": ["2026"], "group_by": ["quarter", "month"]}
    expect(summary).to_have_text("✓ 6 rows · quarter (text), month (date), total (number)")

    # The server's error, in the summary's error style
    field(dataset(editor), "year").locator("select").select_option("2025")
    expect(summary).to_have_text("⚠ There are no donations in 2025.")
    expect(summary).to_have_class(re.compile(r"\bis-error\b"))

    # Only shown for its source
    choose_source(editor, "Paste")
    expect(summary).to_be_hidden()
    choose_source(editor, "Donations")
    expect(summary).to_be_visible()
    expect(summary).to_have_text("⚠ There are no donations in 2025.")
    field(dataset(editor), "year").locator("select").select_option("2026")
    expect(summary).to_have_text(re.compile("^✓ 6 rows"))
    assert all("donation-rows" not in error for error in console_errors)


def test_builder_previews_rows_from_the_rows_url_and_saves(
    editor, custom_page, live_server, console_errors
):
    set_externally(spec_field(editor), "")
    dialog = open_builder(editor)
    expect(dialog.locator("[data-chart] svg")).to_have_count(1)
    expect(dialog.locator("[data-errors] li")).to_have_count(0)
    # The suggested chart is built from the rows' columns, and loads the
    # dataset by name
    spec = builder_spec(editor)
    assert spec["data"] == {"name": "donations"}
    assert "datasets" not in spec
    fields = {channel.get("field") for channel in spec["encoding"].values()}
    assert fields <= {"quarter", "total", None} and fields & {"quarter", "total"}
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)

    editor.keyboard.press("ControlOrMeta+s")
    expect(editor.locator(".messages")).to_contain_text("has been updated")
    expect(editor.locator(".messages")).not_to_contain_text("could not be saved")
    with DATABASE_LOCK:
        revision = ChartPage.objects.get(pk=custom_page.pk).get_latest_revision()
        saved = revision.as_object().body[0].value
        assert saved["spec"] == spec
        item = saved["data"][0]
        assert item["source_type"] == "donations" and item["group_by"] == ["quarter"]
        assert not item["paste"]
        revision.publish()

    # On the site, with the rows from the server
    editor.goto(live_server.url + "/")
    chart = editor.locator("wagtail-vega-chart").first
    expect(chart).to_have_class(re.compile(r"\bis-rendered\b"), timeout=15_000)
    expect(chart.locator("svg")).to_have_count(1)
    payload = json.loads(editor.locator('script[id$="-payload"]').first.text_content())
    assert payload["spec"]["datasets"]["donations"] == [
        {"quarter": "Q1", "total": 391.5},
        {"quarter": "Q2", "total": 831.5},
    ]
    assert console_errors == []


def test_builder_uses_a_registered_source(editor, console_errors):
    """ "sample" has no rows URL; sample-source.js registers it."""
    choose_source(editor, "Sample")
    field(dataset(editor), "points").locator("input").fill("4")
    # No summary for it (it has no rows URL)
    expect(dataset(editor).locator(".wagtail-vega-summary:visible")).to_have_count(0)
    set_externally(spec_field(editor), "")
    dialog = open_builder(editor)
    expect(dialog.locator("[data-chart] svg")).to_have_count(1)
    expect(dialog.locator("[data-errors] li")).to_have_count(0)
    spec = builder_spec(editor)
    assert spec["data"] == {"name": "donations"}
    fields = {channel.get("field") for channel in spec["encoding"].values()}
    assert fields & {"x", "y"}
    # The preview has the registered source's four rows
    marks = dialog.locator("[data-chart] svg .mark-symbol path, [data-chart] svg .mark-rect path")
    expect(marks).to_have_count(4)
    assert console_errors == []


def test_source_without_rows_cant_be_previewed(editor, console_errors):
    """A source with neither a rows URL nor a registered script gets a note,
    and its dataset never falls back to the pasted data."""
    choose_source(editor, "Paste")
    fill_editor(field(dataset(editor), "paste"), "quarter,total\nQ9,1")
    choose_source(editor, "Yearly totals")
    requests = []
    editor.on("request", lambda r: "donation-rows" in r.url and requests.append(r.url))

    dialog = open_builder(editor)
    expect(dialog.locator("[data-errors]")).to_contain_text(CANT_PREVIEW)
    expect(dialog.locator("[data-chart] svg")).to_have_count(0)
    # Nothing from the (hidden) pasted data is used
    expect(dialog).not_to_contain_text("Q9")
    assert requests == []
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    # The field's own preview says the same
    status = spec_field(editor).locator("[data-field-status]")
    expect(status).to_contain_text(CANT_PREVIEW)
    assert console_errors == []
