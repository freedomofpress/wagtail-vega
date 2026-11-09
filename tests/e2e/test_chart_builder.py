"""The chart builder, end to end: the real Wagtail admin, driven with the
keyboard only (Tab, typing, Space, Enter and Esc), then the saved page's
spec and its chart on the site."""

import json
import re

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from playwright.sync_api import expect
from wagtail.documents import get_document_model
from wagtail.models import Collection

from tests.testapp.demo import BAR
from tests.testapp.models import ChartPage

from .editor import fill_editor, set_externally

pytestmark = pytest.mark.e2e

VL = "https://vega.github.io/schema/vega-lite/v6.json"
LAUNCHER = "wagtail-vega-chart-builder"
DIALOG = "dialog.wagtail-vega-builder"
# The demo page's blocks
REQUESTS, VEGA, DONATIONS, WEATHER = range(4)


@pytest.fixture
def editor(admin_page, live_server, chart_page):
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
    expect(admin_page.locator(LAUNCHER)).to_have_count(4)
    return admin_page


# -- Helpers ------------------------------------------------------------------------


def spec_field(page, index=0):
    return page.locator('[data-contentpath="spec"]').nth(index)


def spec_textarea(page, index=0):
    # Hidden behind the code editor, but still the field's value
    return spec_field(page, index).locator("textarea")


def editor_text(page, index=0):
    return spec_textarea(page, index).evaluate(
        "(t) => t.wagtailVegaEditor.view.state.doc.toString()"
    )


def trigger(page, index=0):
    return page.locator(LAUNCHER).nth(index).locator("button")


def open_builder(page, index=0):
    """Open the builder from its button, with the keyboard."""
    trigger(page, index).focus()
    page.keyboard.press("Enter")
    dialog = page.locator(DIALOG)
    expect(dialog).to_be_visible()
    return dialog


def control(dialog, prop, channel=None):
    scope = dialog.locator(f'[data-channel="{channel}"]' if channel else "[data-controls]")
    return scope.locator(f'[data-prop="{prop}"]')


def tab_to(page, locator, limit=150):
    """Move focus to `locator` with Tab (or Shift+Tab if it's earlier in the
    page), as a keyboard user would. Fails if Tab never gets there."""
    expect(locator).to_be_visible()
    for _ in range(limit):
        if locator.evaluate("(el) => el === document.activeElement"):
            return
        before = locator.evaluate(
            "(el) => Boolean(document.activeElement && document.activeElement !== document.body"
            " && (el.compareDocumentPosition(document.activeElement)"
            " & Node.DOCUMENT_POSITION_FOLLOWING))"
        )
        page.keyboard.press("Shift+Tab" if before else "Tab")
    raise AssertionError(f"Tab never reached {locator}")


def choose(page, select, label):
    """Pick an option by typing its label into the focused select."""
    tab_to(page, select)
    current = select.locator("option:checked").text_content()
    # Typing searches from the option after the selected one, so typing
    # "Stacked" with "Stacked" selected would pick "Stacked to 100%"
    if current != label and not current.startswith(f"{label} ("):
        page.keyboard.type(label)
    expect(select.locator("option:checked")).to_have_text(re.compile("^" + re.escape(label)))


def check(page, checkbox, on=True):
    tab_to(page, checkbox)
    if checkbox.is_checked() != on:
        page.keyboard.press("Space")
    expect(checkbox).to_be_checked(checked=on)


def type_into(page, field, text):
    tab_to(page, field)
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type(text)


def press(page, button):
    tab_to(page, button)
    page.keyboard.press("Enter")


def wait_for_preview(dialog):
    expect(dialog.locator("[data-chart] svg")).to_have_count(1)


def count_input_events(page, index=0):
    page.evaluate(
        """(i) => {
            const t = document.querySelectorAll('[data-contentpath="spec"] textarea')[i];
            window.__inputEvents = 0;
            t.addEventListener("input", (e) => { if (e.bubbles) window.__inputEvents++; });
        }""",
        index,
    )


# -- Building each common chart with the keyboard ---------------------------------------

M = "mark"
# (block, steps, expected spec minus $schema/data/width): each step is
# (prop, channel or None, label) for a select, or ("check", prop) or
# ("text", prop, channel, text) or ("press", selector)
CHARTS = {
    "bar": (
        REQUESTS,
        [
            (M, None, "Bar"),
            ("field", "x", "quarter"),
            ("field", "y", "requests"),
            ("aggregate", "y", "Sum"),
            ("field", "color", "None"),
        ],
        {
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": "quarter", "type": "nominal"},
                "y": {"field": "requests", "type": "quantitative", "aggregate": "sum"},
            },
        },
    ),
    "grouped bar": (
        REQUESTS,
        [(M, None, "Bar"), ("field", "color", "agency"), ("arrangement", None, "Side by side")],
        {
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": "quarter", "type": "nominal"},
                "y": {"field": "requests", "type": "quantitative", "aggregate": "sum"},
                "xOffset": {"field": "agency"},
                "color": {"field": "agency", "type": "nominal"},
            },
        },
    ),
    "stacked bar": (
        REQUESTS,
        [("field", "color", "agency"), ("arrangement", None, "Stacked")],
        {
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": "quarter", "type": "nominal"},
                "y": {"field": "requests", "type": "quantitative", "aggregate": "sum"},
                "color": {"field": "agency", "type": "nominal"},
            },
        },
    ),
    "normalised stacked bar": (
        REQUESTS,
        [("field", "color", "agency"), ("arrangement", None, "Stacked to 100%")],
        {
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": "quarter", "type": "nominal"},
                "y": {
                    "field": "requests",
                    "type": "quantitative",
                    "aggregate": "sum",
                    "stack": "normalize",
                },
                "color": {"field": "agency", "type": "nominal"},
            },
        },
    ),
    "line over time": (
        WEATHER,
        [(M, None, "Line"), ("field", "x", "date"), ("field", "y", "temp_max")],
        {
            "mark": {"type": "line", "tooltip": True},
            "encoding": {
                "x": {"field": "date", "type": "temporal"},
                "y": {"field": "temp_max", "type": "quantitative"},
            },
        },
    ),
    "multi-series line": (
        WEATHER,
        [
            (M, None, "Line"),
            ("field", "x", "date"),
            ("timeUnit", "x", "Year and month"),
            ("field", "y", "temp_max"),
            ("aggregate", "y", "Mean"),
            ("field", "color", "weather"),
            ("check", "point"),
        ],
        {
            "mark": {"type": "line", "tooltip": True, "point": True},
            "encoding": {
                "x": {"field": "date", "type": "temporal", "timeUnit": "utcyearmonth"},
                "y": {"field": "temp_max", "type": "quantitative", "aggregate": "mean"},
                "color": {"field": "weather", "type": "nominal"},
            },
        },
    ),
    "stacked area": (
        WEATHER,
        [
            (M, None, "Area"),
            ("field", "x", "date"),
            ("timeUnit", "x", "Year and month"),
            ("field", "y", "precipitation"),
            ("aggregate", "y", "Sum"),
            ("field", "color", "weather"),
        ],
        {
            "mark": {"type": "area", "tooltip": True},
            "encoding": {
                "x": {"field": "date", "type": "temporal", "timeUnit": "utcyearmonth"},
                "y": {"field": "precipitation", "type": "quantitative", "aggregate": "sum"},
                "color": {"field": "weather", "type": "nominal"},
            },
        },
    ),
    "scatter plot with colour and size": (
        WEATHER,
        [
            (M, None, "Point"),
            ("field", "x", "temp_min"),
            ("field", "y", "temp_max"),
            ("field", "color", "weather"),
            ("field", "size", "wind"),
        ],
        {
            "mark": {"type": "point", "tooltip": True},
            "encoding": {
                "x": {"field": "temp_min", "type": "quantitative"},
                "y": {"field": "temp_max", "type": "quantitative"},
                "color": {"field": "weather", "type": "nominal"},
                "size": {"field": "wind", "type": "quantitative"},
            },
        },
    ),
    "pie": (
        REQUESTS,
        [
            (M, None, "Arc"),
            ("field", "theta", "requests"),
            ("aggregate", "theta", "Sum"),
            ("field", "color", "agency"),
        ],
        {
            "mark": {"type": "arc", "tooltip": True},
            "encoding": {
                "theta": {"field": "requests", "type": "quantitative", "aggregate": "sum"},
                "color": {"field": "agency", "type": "nominal"},
            },
        },
    ),
    "donut": (
        REQUESTS,
        [
            (M, None, "Arc"),
            ("field", "theta", "requests"),
            ("aggregate", "theta", "Sum"),
            ("field", "color", "quarter"),
            ("check", "donut"),
        ],
        {
            "mark": {"type": "arc", "tooltip": True, "innerRadius": 50},
            "encoding": {
                "theta": {"field": "requests", "type": "quantitative", "aggregate": "sum"},
                "color": {"field": "quarter", "type": "nominal"},
            },
        },
    ),
    "heatmap": (
        WEATHER,
        [
            (M, None, "Rectangle"),
            ("field", "x", "date"),
            ("type", "x", "Ordered"),
            ("timeUnit", "x", "Month (all"),
            ("field", "y", "weather"),
            ("field", "color", "precipitation"),
            ("aggregate", "color", "Mean"),
        ],
        {
            "mark": {"type": "rect", "tooltip": True},
            "encoding": {
                "x": {"field": "date", "type": "ordinal", "timeUnit": "utcmonth"},
                "y": {"field": "weather", "type": "nominal"},
                "color": {"field": "precipitation", "type": "quantitative", "aggregate": "mean"},
            },
        },
    ),
    "column facets": (
        REQUESTS,
        [("field", "x", "agency"), ("field", "column", "quarter"), ("field", "row", "None")],
        {
            "width": None,
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": "agency", "type": "nominal"},
                "y": {"field": "requests", "type": "quantitative", "aggregate": "sum"},
                "column": {"field": "quarter", "type": "nominal"},
            },
        },
    ),
    "row facets": (
        WEATHER,
        [
            (M, None, "Bar"),
            ("field", "x", "weather"),
            ("field", "y", "Count of rows"),
            ("field", "row", "date"),
            ("timeUnit", "row", "Year"),
        ],
        {
            "width": None,
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": "weather", "type": "nominal"},
                "y": {"type": "quantitative", "aggregate": "count"},
                "row": {"field": "date", "type": "temporal", "timeUnit": "utcyear"},
            },
        },
    ),
    "titles, then swap x and y": (
        REQUESTS,
        [
            ("text", "chartTitle", None, "Requests by quarter"),
            ("text", "title", "x", "Quarter"),
            ("press", "[data-swap]"),
        ],
        {
            "title": "Requests by quarter",
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": "requests", "type": "quantitative", "aggregate": "sum"},
                "y": {"field": "quarter", "type": "nominal", "title": "Quarter"},
            },
        },
    ),
}


def run_steps(page, dialog, steps):
    for step in steps:
        if step[0] == "check":
            check(page, control(dialog, step[1]))
        elif step[0] == "text":
            _, prop, channel, text = step
            type_into(page, control(dialog, prop, channel), text)
        elif step[0] == "press":
            press(page, dialog.locator(step[1]))
        else:
            prop, channel, label = step
            choose(page, control(dialog, prop, channel), label)


def expected_spec(dataset, expected):
    spec = {"$schema": VL, "width": "container", "data": {"name": dataset}, **expected}
    return {k: v for k, v in spec.items() if v is not None}


@pytest.mark.parametrize("name", list(CHARTS))
def test_build_with_the_keyboard_and_save(name, editor, chart_page, live_server, console_errors):
    block, steps, expected = CHARTS[name]
    dataset = "source" if block == REQUESTS else "weather"
    expected = expected_spec(dataset, expected)
    # Start from an empty spec field
    set_externally(spec_field(editor, block), "")
    count_input_events(editor, block)

    dialog = open_builder(editor, block)
    expect(control(dialog, "mark")).to_be_focused()
    expect(dialog.locator("[role=status]")).to_contain_text("Started from a suggested chart")
    run_steps(editor, dialog, steps)
    wait_for_preview(dialog)
    # The spec, shown under the preview, is updated as each control changes
    assert json.loads(dialog.locator("[data-json]").text_content()) == expected
    press(editor, dialog.get_by_role("button", name="Use this chart"))

    # The field was empty, so no confirmation is needed
    expect(dialog).to_have_count(0)
    expect(trigger(editor, block)).to_be_focused()
    spec = json.loads(spec_textarea(editor, block).input_value())
    assert spec == expected
    assert editor_text(editor, block) == spec_textarea(editor, block).input_value()
    assert editor.evaluate("window.__inputEvents") == 1

    # Save the draft (Ctrl/Cmd+S) and check what was saved
    editor.keyboard.press("ControlOrMeta+s")
    expect(editor.locator(".messages")).to_contain_text("has been updated")
    expect(editor.locator(".messages")).not_to_contain_text("could not be saved")
    page_obj = ChartPage.objects.get(pk=chart_page.pk)
    assert page_obj.get_latest_revision_as_object().body[block].value["spec"] == expected

    # The chart renders on the site
    page_obj.get_latest_revision().publish()
    editor.goto(live_server.url + "/")
    chart = editor.locator("wagtail-vega-chart").nth(block)
    expect(chart).to_have_class(re.compile(r"\bis-rendered\b"), timeout=15_000)
    expect(chart.locator("svg")).to_have_count(1)
    assert console_errors == []


# -- The lightbox ------------------------------------------------------------------------


def test_opens_the_fields_chart(editor, console_errors):
    dialog = open_builder(editor)
    expect(dialog).to_have_attribute("aria-labelledby", re.compile("-title$"))
    expect(dialog.get_by_role("heading", name="Build a chart")).to_be_visible()
    expect(dialog.locator("[role=status]")).to_contain_text("Opened the field's chart.")
    # Focus moves to the first control
    expect(control(dialog, "mark")).to_be_focused()
    # Grouped bars open as grouped bars (Voyager made them stacked)
    expect(control(dialog, "mark")).to_have_value("bar")
    expect(control(dialog, "arrangement")).to_have_value("grouped")
    expect(control(dialog, "field", "color")).to_have_value("agency")
    expect(control(dialog, "chartTitle")).to_have_value("Requests by quarter")
    # The hidden axis title isn't something the builder edits: it's kept,
    # and listed
    expect(dialog.locator("[data-kept]")).to_contain_text("encoding.x.title")
    expect(control(dialog, "title", "x")).to_have_attribute(
        "placeholder", "None (kept from the spec)"
    )
    # One dataset: no picker
    expect(dialog.locator("[data-dataset-picker]")).to_be_hidden()
    wait_for_preview(dialog)
    # The preview uses the chart's theme (the site default, "house")
    expect(dialog.locator("[data-chart] svg text").first).to_have_attribute(
        "font-family", re.compile("Georgia")
    )
    assert editor.evaluate("document.activeElement.closest('dialog') !== null")
    assert console_errors == []


def test_using_an_unchanged_chart_changes_nothing(editor):
    textarea = spec_textarea(editor)
    original = textarea.input_value()
    count_input_events(editor)
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    press(editor, dialog.get_by_role("button", name="Use this chart"))
    expect(dialog).to_have_count(0)
    assert textarea.input_value() == original
    assert editor.evaluate("window.__inputEvents") == 0
    expect(trigger(editor)).to_be_focused()
    expect(editor.locator(LAUNCHER).first.locator("[data-builder-note]")).to_have_text(
        "The chart wasn't changed."
    )


def test_confirms_before_replacing_a_spec(editor):
    textarea = spec_textarea(editor)
    original = textarea.input_value()
    count_input_events(editor)
    dialog = open_builder(editor)
    # Stacked rather than grouped bars
    choose(editor, control(dialog, "arrangement"), "Stacked")
    use = dialog.get_by_role("button", name="Use this chart")
    press(editor, use)

    replace = dialog.get_by_role("button", name="Replace spec")
    expect(replace).to_be_focused()
    expect(dialog).to_contain_text("This replaces the spec that's in the field now.")
    assert textarea.input_value() == original

    press(editor, dialog.get_by_role("button", name="Keep editing"))
    expect(replace).to_be_hidden()
    expect(use).to_be_focused()
    assert textarea.input_value() == original

    press(editor, use)
    expect(replace).to_be_focused()
    editor.keyboard.press("Enter")
    expect(dialog).to_have_count(0)
    spec = json.loads(textarea.input_value())
    # Only the grouping changed: everything else, including what the builder
    # doesn't edit, is as it was
    assert spec == {**BAR, "encoding": {k: v for k, v in BAR["encoding"].items() if k != "xOffset"}}
    assert editor.evaluate("window.__inputEvents") == 1
    assert editor_text(editor) == textarea.input_value()
    expect(editor.locator(LAUNCHER).first.locator("[data-builder-note]")).to_have_text(
        "The chart is now in the spec field."
    )

    # ...and one Ctrl/Cmd+Z in the code editor brings the old spec back
    spec_field(editor).locator(".cm-content").focus()
    editor.keyboard.press("ControlOrMeta+z")
    expect(textarea).to_have_value(original)


def test_cancel_and_escape_leave_the_field_unchanged(editor):
    textarea = spec_textarea(editor)
    original = textarea.input_value()
    count_input_events(editor)

    # Cancel button
    dialog = open_builder(editor)
    choose(editor, control(dialog, "mark"), "Line")
    press(editor, dialog.get_by_role("button", name="Cancel"))
    expect(dialog).to_have_count(0)
    expect(trigger(editor)).to_be_focused()

    # Escape, from a select
    dialog = open_builder(editor)
    choose(editor, control(dialog, "field", "x"), "agency")
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(trigger(editor)).to_be_focused()

    # Escape, from a text field
    dialog = open_builder(editor)
    type_into(editor, control(dialog, "chartTitle"), "Changed")
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(trigger(editor)).to_be_focused()

    # The close button
    dialog = open_builder(editor)
    press(editor, dialog.get_by_role("button", name="Close without using the chart"))
    expect(dialog).to_have_count(0)
    expect(trigger(editor)).to_be_focused()

    assert textarea.input_value() == original
    assert editor.evaluate("window.__inputEvents") == 0
    assert editor.locator(DIALOG).count() == 0


def test_changes_list_what_they_remove(editor):
    dialog = open_builder(editor)
    dropped = dialog.locator("[data-dropped]")
    expect(dropped).to_be_empty()
    # x's kept settings belong to its field: changing it removes them...
    choose(editor, control(dialog, "field", "x"), "agency")
    expect(dropped).to_contain_text("Your changes remove these parts of the spec:")
    expect(dropped).to_contain_text("encoding.x.title")
    # ...and changing it back restores them
    editor.wait_for_timeout(1100)  # let the select's type-ahead search end
    choose(editor, control(dialog, "field", "x"), "quarter")
    expect(dropped).to_be_empty()
    expect(dialog.locator("[data-kept]")).to_contain_text("encoding.x.title")


def test_lightbox_is_modal(editor):
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    assert editor.evaluate("document.querySelector('dialog').matches(':modal')")
    assert editor.evaluate("document.elementFromPoint(5, 5) === document.querySelector('dialog')")
    # Tabbing on from the last control doesn't reach the page behind
    dialog.get_by_role("button", name="Use this chart").focus()
    editor.keyboard.press("Tab")
    assert editor.evaluate(
        "!document.activeElement || document.activeElement === document.body"
        " || document.activeElement.closest('dialog') !== null"
    )


def test_controls_are_labelled(editor):
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    unlabelled = dialog.evaluate(
        """(d) => [...d.querySelectorAll("select, input")]
            .filter((el) => !el.closest("[hidden]") && !el.labels?.length)
            .map((el) => el.outerHTML.slice(0, 80))"""
    )
    assert unlabelled == []
    expect(dialog.get_by_label("Chart type")).to_have_value("bar")
    expect(dialog.get_by_role("group", name="X axis (horizontal)")).to_be_visible()
    expect(dialog.get_by_role("group", name="Colour")).to_be_visible()


def test_suggestions(editor):
    set_externally(spec_field(editor), "")
    dialog = open_builder(editor)
    suggestions = dialog.locator("[data-suggestions]")
    expect(suggestions).to_have_attribute("open", "")
    press(editor, dialog.get_by_role("button", name="Pie: share of requests by agency"))
    expect(control(dialog, "mark")).to_have_value("arc")
    expect(control(dialog, "field", "theta")).to_have_value("requests")
    expect(dialog.locator("[role=status]")).to_contain_text("Chart set to")
    wait_for_preview(dialog)


def test_preview_in_dark_mode(editor):
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    title = dialog.locator("[data-chart] svg .role-title text")
    expect(title).to_have_attribute("fill", "#111")
    # The house theme has dark settings, so the preview offers them
    choose(editor, dialog.get_by_label("Colours"), "Dark mode")
    expect(title).to_have_attribute("fill", "#fff")


def test_cant_open_a_vega_spec(editor):
    textarea = spec_textarea(editor, VEGA)
    original = textarea.input_value()
    dialog = open_builder(editor, VEGA)
    start = dialog.get_by_role("button", name="Start a new chart")
    expect(start).to_be_focused()
    expect(dialog.locator("[data-problem]")).to_contain_text(
        "The builder can't open the spec that's in the field: it's a Vega spec"
    )
    expect(dialog.locator("[data-controls]")).to_be_hidden()
    expect(dialog.get_by_role("button", name="Use this chart")).to_be_disabled()
    editor.keyboard.press("Enter")
    expect(control(dialog, "mark")).to_be_focused()
    wait_for_preview(dialog)
    press(editor, dialog.get_by_role("button", name="Use this chart"))
    # The new chart replaces the Vega spec only when confirmed
    expect(dialog.get_by_role("button", name="Replace spec")).to_be_focused()
    assert textarea.input_value() == original
    editor.keyboard.press("Enter")
    expect(dialog).to_have_count(0)
    assert json.loads(textarea.input_value())["$schema"] == VL


def test_cant_open_layers(editor):
    layered = {"$schema": VL, "data": {"name": "source"}, "layer": [{"mark": "bar"}]}
    set_externally(spec_field(editor), json.dumps(layered))
    dialog = open_builder(editor)
    expect(dialog.locator("[data-problem]")).to_contain_text("it combines several views")
    press(editor, dialog.get_by_role("button", name="Cancel"))
    assert json.loads(spec_textarea(editor).input_value()) == layered


def test_disabled_when_data_comes_from_code(editor):
    launcher = editor.locator(LAUNCHER).nth(DONATIONS)
    button = launcher.locator("button")
    expect(button).to_be_disabled()
    note = launcher.locator("[data-builder-note]")
    expect(note).to_have_text(
        "The chart builder works with datasets added in this form. "
        "This chart's data comes from code."
    )
    expect(button).to_have_attribute("aria-describedby", note.get_attribute("id"))


def test_url_dataset(editor, console_errors):
    dialog = open_builder(editor, WEATHER)
    wait_for_preview(dialog)
    expect(control(dialog, "field", "x")).to_contain_text("precipitation (number)")
    assert console_errors == []


def test_url_dataset_on_a_disallowed_host(editor):
    data = editor.locator('[data-contentpath="data"]').nth(2)
    data.locator('[data-contentpath="url"] input').fill("https://evil.example/data.csv")
    dialog = open_builder(editor, WEATHER)
    expect(dialog.locator("[data-errors]")).to_contain_text(
        "Data can't be loaded from https://evil.example/data.csv."
    )
    expect(dialog.get_by_role("button", name="Use this chart")).to_be_disabled()


def test_document_dataset(editor, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    if not Collection.get_first_root_node():  # flushed by an earlier e2e test
        Collection.add_root(name="Root")
    doc = get_document_model().objects.create(
        title="sales", file=ContentFile(b"region,sales\nNorth,10\nSouth,20\n", name="sales.csv")
    )
    dataset = editor.locator(".wagtail-vega-dataset").first
    dataset.locator('[data-contentpath="source_type"]').get_by_text("Document", exact=True).click()
    # Stand in for the document chooser modal
    dataset.locator('[data-contentpath="document"] input[type="hidden"]').evaluate(
        "(el, pk) => { el.value = pk; }", str(doc.pk)
    )
    set_externally(spec_field(editor), "")
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    expect(control(dialog, "field", "x")).to_have_value("region")
    expect(control(dialog, "field", "y")).to_have_value("sales")


def test_several_datasets_offer_a_picker(editor):
    data_list = editor.locator('[data-contentpath="data"]').first
    data_list.locator("button[data-streamfield-list-add]").last.click()
    new = data_list.locator(".wagtail-vega-dataset").last
    new.locator('[data-contentpath="name"] input').fill("budget")
    fill_editor(new.locator('[data-contentpath="paste"]'), "year,amount\n2025,100\n2026,120")

    dialog = open_builder(editor)
    picker = dialog.get_by_label("Dataset")
    expect(picker).to_be_visible()
    expect(picker).to_have_value("source")  # the one the spec refers to
    wait_for_preview(dialog)

    choose(editor, picker, "budget")
    expect(dialog.locator("[role=status]")).to_contain_text("doesn't have the fields")
    expect(control(dialog, "field", "x")).to_contain_text("amount (number)")
    choose(editor, control(dialog, "field", "x"), "year")
    choose(editor, control(dialog, "field", "y"), "amount")
    press(editor, dialog.get_by_role("button", name="Use this chart"))
    press(editor, dialog.get_by_role("button", name="Replace spec"))
    expect(dialog).to_have_count(0)
    spec = json.loads(spec_textarea(editor).input_value())
    assert spec["data"] == {"name": "budget"}
    # The parts of the spec the builder doesn't edit are kept
    assert spec["title"] == "Requests by quarter"


def test_new_chart_blocks_get_the_button(editor):
    """Blocks added after page load (telepath-rendered) get a working button."""
    editor.locator("button.c-sf-add-button").last.click()
    editor.get_by_role("option", name=re.compile(r"^Chart$")).click()
    launchers = editor.locator(LAUNCHER)
    expect(launchers).to_have_count(5)
    new = launchers.last
    new.locator("button").focus()
    editor.keyboard.press("Enter")
    # A new chart starts with one empty dataset
    note = new.locator("[data-builder-note]")
    expect(note).to_have_text(
        "Add data to this chart's datasets first, then build the chart from it."
    )
    expect(editor.locator(DIALOG)).to_have_count(0)

    dataset = editor.locator('[data-contentpath="data"]').last.locator(".wagtail-vega-dataset")
    fill_editor(dataset.locator('[data-contentpath="paste"]'), "fruit,count\napple,3\npear,5")
    dialog = open_builder(editor, 4)
    expect(note).to_be_hidden()
    wait_for_preview(dialog)
    expect(control(dialog, "field", "x")).to_have_value("fruit")
    press(editor, dialog.get_by_role("button", name="Use this chart"))
    expect(dialog.locator("[data-errors]")).to_be_empty()
    expect(dialog).to_have_count(0)
    expect(new.locator("button")).to_be_focused()
    spec = json.loads(spec_textarea(editor, 4).input_value())
    assert spec["encoding"]["x"]["field"] == "fruit"


def test_button_sits_above_the_code_editor(editor):
    for index in range(4):
        field = spec_field(editor, index)
        toolbar = field.locator(LAUNCHER)
        code = field.locator(".wagtail-vega-code--spec")
        expect(code).to_be_visible()
        expect(field.locator("textarea")).to_be_hidden()
        assert field.locator(".cm-editor").count() == 1
        top = toolbar.bounding_box()
        box = code.bounding_box()
        assert top["y"] + top["height"] <= box["y"] + 1
    fill_editor(spec_field(editor), '{"a": 1}')
    expect(spec_textarea(editor)).to_have_value('{"a": 1}')


def test_vega_libraries_load_only_when_the_builder_opens(editor):
    assert editor.evaluate("typeof window.vegaEmbed") == "undefined"
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    assert editor.evaluate("typeof window.vegaEmbed") == "function"
    press(editor, dialog.get_by_role("button", name="Cancel"))
    # Opening again doesn't load them twice
    open_builder(editor)
    assert editor.locator('script[src*="vega.min.js"]').count() == 1


def test_narrow_screens(editor):
    editor.set_viewport_size({"width": 390, "height": 844})
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    # No horizontal scrolling; the preview follows the controls
    assert dialog.evaluate("(d) => d.scrollWidth <= d.clientWidth + 1")
    controls = dialog.locator("[data-controls]").bounding_box()
    preview = dialog.locator("[data-preview]").bounding_box()
    assert preview["y"] >= controls["y"] + controls["height"] - 1


def test_preview_needs_no_unsafe_eval(admin_page, live_server, chart_page, console_errors):
    """The builder's preview runs under an admin CSP without 'unsafe-eval'."""
    url = live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,))

    def add_csp(route):
        response = route.fetch()
        csp = "script-src 'self'; object-src 'none'"
        route.fulfill(
            response=response, headers={**response.headers, "content-security-policy": csp}
        )

    admin_page.route(url, add_csp)
    admin_page.add_init_script(
        """document.addEventListener("securitypolicyviolation", (e) =>
            console.error(`CSP violation: ${e.violatedDirective} ${e.blockedURI}`))"""
    )
    admin_page.goto(url)
    expect(admin_page.locator(LAUNCHER)).to_have_count(4)
    dialog = open_builder(admin_page)
    wait_for_preview(dialog)
    choose(admin_page, control(dialog, "mark"), "Line")
    expect(dialog.locator("[data-chart] svg .mark-line").first).to_be_visible()
    assert [e for e in console_errors if "eval" in e] == []
    expect(dialog.locator("[data-warnings]")).to_be_empty()
