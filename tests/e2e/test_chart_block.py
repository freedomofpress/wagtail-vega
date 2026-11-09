"""Chart blocks in the admin: labels, empty states, and the check that the
spec only loads datasets the chart has (chart-block.js)."""

import pytest
from django.urls import reverse
from playwright.sync_api import expect

from tests.testapp.models import ChartPage

from .editor import fill_editor

pytestmark = pytest.mark.e2e

TOP_LEVEL = "[data-streamfield-child]:not([data-streamfield-child] [data-streamfield-child])"
SPEC = '[data-contentpath="spec"]'
DATASET = ".wagtail-vega-dataset"


@pytest.fixture
def editor(admin_page, live_server, chart_page):
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
    expect(admin_page.locator(f"{SPEC} .cm-editor")).to_have_count(4)
    return admin_page


def name_input(dataset):
    return dataset.locator('[data-contentpath="name"] input')


def test_chart_blocks_are_labelled_with_their_title(editor):
    blocks = editor.locator(TOP_LEVEL)
    titles = blocks.locator(":scope > section > .w-panel__header .c-sf-block__title")
    # The spec's title, not the first dataset's name ("source")
    expect(titles).to_have_text(
        [
            "Requests by quarter",
            # No title in the spec: the caption
            "A raw Vega spec using the vega:fivethirtyeight theme",
            "Donations (from the database)",
            "Weather (CSV from a URL)",
        ]
    )


def test_spec_must_load_the_charts_datasets(editor, chart_page):
    chart = editor.locator(TOP_LEVEL).first
    spec = chart.locator(SPEC)
    status = spec.locator(".wagtail-vega-code__status")
    expect(spec.locator(".cm-lintRange-error")).to_have_count(0)

    # Renaming the dataset leaves the spec loading one that isn't there
    name_input(chart.locator(DATASET)).fill("requests")
    expect(spec.locator(".cm-lintRange-error")).to_have_text('"source"')
    expect(status).to_have_text(
        'Line 6: This chart has no dataset called "source". '
        "Use one of its datasets (requests), or add one under Data."
    )

    # Adding a dataset with that name fixes it
    data_list = chart.locator('[data-contentpath="data"]').first
    data_list.locator("button[data-streamfield-list-add]").last.click()
    expect(chart.locator(DATASET)).to_have_count(2)
    expect(spec.locator(".cm-lintRange-error")).to_have_count(0)
    expect(status).to_be_hidden()

    # Saving with a missing dataset is an error, shown on the spec
    added = chart.locator(DATASET).last
    name_input(added).fill("other")
    fill_editor(added.locator('[data-contentpath="paste"]'), "a\n1")
    expect(spec.locator(".cm-lintRange-error")).to_have_count(1)
    revisions = chart_page.revisions.count()
    editor.locator("button.action-save").first.click()
    editor.wait_for_load_state("networkidle")
    spec = editor.locator(TOP_LEVEL).first.locator(SPEC)
    expect(spec.locator(".w-field__errors")).to_contain_text(
        'data.name: This chart has no dataset called "source".'
    )
    expect(spec.locator(".cm-lintRange-error")).to_have_text('"source"')
    assert chart_page.revisions.count() == revisions


def test_new_chart_starts_empty_with_examples(editor):
    editor.locator("[data-contentpath='body'] button.c-sf-add-button").first.click()
    editor.get_by_role("option", name="Chart", exact=True).first.click()
    chart = editor.locator(TOP_LEVEL).first
    spec = chart.locator(SPEC)
    expect(spec.locator(".cm-editor")).to_be_visible()
    # Not the JSON text "null"
    expect(spec.locator("textarea")).to_have_value("")
    expect(spec.locator(".cm-placeholder")).to_contain_text("Paste a spec here")
    expect(spec.locator(".cm-placeholder")).to_contain_text('"data": {"name": "source"}')
    paste = chart.locator('[data-contentpath="paste"]')
    expect(paste.locator(".cm-placeholder")).to_contain_text("quarter,requests")

    # The example spec, once typed in, is valid
    fill_editor(
        spec,
        '{"$schema": "https://vega.github.io/schema/vega-lite/v6.json",'
        ' "data": {"name": "source"}, "mark": "bar"}',
    )
    expect(spec.locator(".cm-placeholder")).to_have_count(0)
    expect(spec.locator(".cm-lintRange-error")).to_have_count(0)


def test_source_toggle_and_summary_are_named(editor):
    dataset = editor.locator(DATASET).first
    group = dataset.get_by_role("radiogroup", name="Source")
    expect(group).to_have_count(1)
    expect(group.get_by_role("radio")).to_have_count(3)

    # The editor is described by its help text and the summary
    content = dataset.locator('[data-contentpath="paste"] .cm-content')
    summary = dataset.locator(".wagtail-vega-summary")
    described_by = content.get_attribute("aria-describedby").split()
    assert summary.get_attribute("id") in described_by
    # The ✓ is decoration
    expect(summary.locator("[aria-hidden=true]").first).to_have_text("✓ ")


def test_page_still_saves(editor, chart_page):
    editor.locator("button.action-save").first.click()
    editor.wait_for_load_state("networkidle")
    expect(editor.locator(".messages")).to_contain_text("has been updated")
    body = ChartPage.objects.get(pk=chart_page.pk).get_latest_revision_as_object().body
    assert len(body) == 4
