"""The DatasetBlock editing UI in a real browser.

This is the code most coupled to Wagtail's admin internals (telepath block
definitions and StructBlock markup), so it's the main reason these tests run
against every supported Wagtail version.
"""

import re

import pytest
from django.urls import reverse
from playwright.sync_api import expect

from tests.testapp.models import ChartPage

pytestmark = pytest.mark.e2e

DATASET = ".wagtail-vega-dataset"


@pytest.fixture
def editor(admin_page, live_server, chart_page):
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
    expect(admin_page.locator(DATASET)).to_have_count(3)
    return admin_page


def field(dataset, name):
    return dataset.locator(f'[data-contentpath="{name}"]')


def assert_visible_fields(dataset, *names):
    for name in ("paste", "document", "url", "format"):
        if name in names:
            expect(field(dataset, name)).to_be_visible()
        else:
            expect(field(dataset, name)).to_be_hidden()


def choose_source(dataset, label):
    field(dataset, "source_type").get_by_text(label, exact=True).click()


def test_initial_state_matches_saved_source(editor):
    datasets = editor.locator(DATASET)
    assert_visible_fields(datasets.nth(0), "paste")
    assert_visible_fields(datasets.nth(2), "url", "format")
    expect(field(datasets.nth(2), "url").locator("input")).to_have_value(
        "/static/testapp/weather.csv"
    )


def test_toggle_switches_inputs(editor):
    dataset = editor.locator(DATASET).first
    choose_source(dataset, "Document")
    assert_visible_fields(dataset, "document")
    choose_source(dataset, "URL")
    assert_visible_fields(dataset, "url", "format")
    choose_source(dataset, "Paste")
    assert_visible_fields(dataset, "paste")
    # Switching back doesn't lose what was pasted
    expect(field(dataset, "paste").locator("textarea")).to_have_value(re.compile("^quarter"))


def test_toggle_is_keyboard_accessible(editor):
    dataset = editor.locator(DATASET).first
    field(dataset, "source_type").locator("input[value=paste]").focus()
    editor.keyboard.press("ArrowRight")
    assert_visible_fields(dataset, "document")


def test_paste_summary(editor):
    dataset = editor.locator(DATASET).first
    summary = dataset.locator(".wagtail-vega-summary")
    expect(summary).to_contain_text(
        "Tab-separated (e.g. copied from a spreadsheet) · 6 rows · "
        "quarter (text), agency (text), requests (number)"
    )
    textarea = field(dataset, "paste").locator("textarea")

    textarea.fill("year,count\n2024,10\n2025\n2026,12")
    expect(summary).to_contain_text("Comma-separated · 3 rows")
    expect(summary.locator(".wagtail-vega-summary__warning")).to_have_text(
        "⚠ Line 3 has 1 value but there are 2 columns."
    )

    textarea.fill("[oops")
    expect(summary).to_have_class("wagtail-vega-summary is-error")
    expect(summary).to_contain_text("couldn't be read")

    textarea.fill("")
    expect(summary).to_be_hidden()


def test_new_dataset_defaults_to_paste(editor):
    data_list = editor.locator('[data-contentpath="data"]').first
    data_list.locator("button[data-streamfield-list-add]").last.click()
    expect(editor.locator(DATASET)).to_have_count(4)
    new = data_list.locator(DATASET).last
    expect(field(new, "name").locator("input")).to_have_value("source")
    expect(field(new, "source_type").locator("input[value=paste]")).to_be_checked()
    assert_visible_fields(new, "paste")
    field(new, "paste").locator("textarea").fill('[{"a": 1}]')
    expect(new.locator(".wagtail-vega-summary")).to_contain_text("JSON · 1 row · a (number)")


def save_draft(page):
    page.locator("button.action-save").first.click()
    page.wait_for_load_state("networkidle")


def expect_saved(page):
    expect(page.locator(".messages")).to_contain_text("has been updated")
    expect(page.locator(".messages")).not_to_contain_text("could not be saved")


def test_save_error_keeps_selected_source(editor, chart_page):
    revisions = chart_page.revisions.count()
    dataset = editor.locator(DATASET).first
    choose_source(dataset, "URL")
    field(dataset, "url").locator("input").fill("")
    save_draft(editor)

    dataset = editor.locator(DATASET).first
    expect(field(dataset, "url")).to_contain_text("Enter a URL.")
    expect(field(dataset, "source_type").locator("input[value=url]")).to_be_checked()
    assert_visible_fields(dataset, "url", "format")
    expect(editor.locator(".messages")).to_contain_text("could not be saved")
    assert chart_page.revisions.count() == revisions


def test_save_switches_source_and_drops_stale_input(editor, chart_page):
    dataset = editor.locator(DATASET).first
    field(dataset, "paste").locator("textarea").fill("quarter,requests\nQ1,5")
    choose_source(dataset, "URL")
    field(dataset, "url").locator("input").fill("/static/testapp/weather.csv")
    choose_source(dataset, "Paste")
    choose_source(dataset, "URL")
    save_draft(editor)
    expect_saved(editor)

    revision = ChartPage.objects.get(pk=chart_page.pk).get_latest_revision_as_object()
    data = revision.body[0].value["data"][0]
    assert data["source_type"] == "url"
    assert data["url"] == "/static/testapp/weather.csv"
    assert not data["paste"]
