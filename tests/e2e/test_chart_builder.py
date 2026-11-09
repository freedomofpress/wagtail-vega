"""The chart field and its editor ("Edit chart"), end to end: the real
Wagtail admin, driven with the keyboard (Tab, arrows, typing, Space, Enter
and Esc), then the saved page's spec and its chart on the site."""

import json
import re

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from playwright.sync_api import expect
from wagtail.documents import get_document_model
from wagtail.models import Collection

from tests.testapp.demo import BAR
from tests.testapp.middleware import DATABASE_LOCK
from tests.testapp.models import ChartPage

from .editor import fill_editor, select_text, set_externally

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
            # The suggested chart is already a bar chart of these fields, so
            # nothing would change: pick the suggestion to put it in the page
            ("press", '[data-suggestion="0"]'),
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
    # A suggestion is shown, but isn't in the field until a setting changes
    expect(dialog.locator("[data-controls-notice]")).to_contain_text("isn't in the page yet")
    assert spec_textarea(editor, block).input_value() == ""
    run_steps(editor, dialog, steps)
    wait_for_preview(dialog)
    # Each setting goes straight into the code, and from there the field
    assert json.loads(editor_text(editor, block)) == expected
    expect(spec_textarea(editor, block)).to_have_value(editor_text(editor, block))
    assert editor.evaluate("window.__inputEvents") >= 1

    # Esc just closes; focus goes back to the button
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(trigger(editor, block)).to_be_focused()
    assert json.loads(spec_textarea(editor, block).input_value()) == expected
    # The field shows the new chart
    expect(field_chart(editor, block).locator("svg")).to_have_count(1)

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


# -- The field ---------------------------------------------------------------------------


def show_field(page, index=0):
    """Scroll the spec field into view: its chart is drawn once it's seen."""
    launcher = page.locator(LAUNCHER).nth(index)
    launcher.scroll_into_view_if_needed()
    return launcher


def field_chart(page, index=0):
    return show_field(page, index).locator("[data-field-chart]")


def field_problems(page, index=0):
    return show_field(page, index).locator("[data-field-problems]")


def expect_settings_disabled(dialog, disabled=True):
    # A disabled <fieldset> disables its controls; Playwright's
    # to_be_disabled() only applies to the controls themselves
    fieldset = dialog.locator("[data-controls-fieldset]")
    if disabled:
        expect(fieldset).to_have_attribute("disabled", "")
    else:
        expect(fieldset).not_to_have_attribute("disabled", re.compile(".*"))


def test_the_field_shows_the_chart_not_json(editor, console_errors):
    field = spec_field(editor)
    # The textarea is still the field's value, hidden; no code editor inline
    expect(field.locator("textarea")).to_be_hidden()
    expect(field.locator(".cm-editor")).to_be_hidden()
    assert field.locator("textarea").evaluate(
        "(t) => t === t.parentElement.querySelector('textarea, wagtail-vega-chart-builder')"
    )
    # The chart, in the chart's theme (the site default, "house")
    expect(field_chart(editor).locator("svg")).to_have_count(1)
    expect(field_chart(editor).locator("svg text").first).to_have_attribute(
        "font-family", re.compile("Georgia")
    )
    expect(field_problems(editor)).to_be_hidden()
    expect(trigger(editor)).to_have_text("Edit chart")
    # Every chart on the page is drawn, including the Vega one
    for index in (REQUESTS, VEGA, WEATHER):
        expect(field_chart(editor, index).locator("svg")).to_have_count(1)
    assert console_errors == []


def test_the_field_lists_the_specs_problems(editor):
    bad = {**BAR, "encoding": {**BAR["encoding"], "x": {"field": "quarter", "type": "nominl"}}}
    set_externally(spec_field(editor), json.dumps(bad, indent=2))
    problems = field_problems(editor)
    expect(problems).to_be_visible()
    expect(problems).to_contain_text("Use “Edit chart” to fix them")
    expect(problems.locator("li")).to_contain_text([re.compile(r"Line \d+: .*nominl")])
    # Invalid JSON: no chart, and the syntax error
    set_externally(spec_field(editor), '{"mark": "bar",}')
    expect(problems.locator("li")).to_have_count(1)
    expect(show_field(editor).locator("[data-field-status]")).to_contain_text("isn't valid JSON")
    expect(field_chart(editor)).to_be_empty()


def test_the_field_lists_errors_from_a_failed_save(editor):
    missing = {**BAR, "data": {"name": "nope"}}
    set_externally(spec_field(editor), json.dumps(missing, indent=2))
    editor.keyboard.press("ControlOrMeta+s")
    expect(editor.locator(".messages")).to_contain_text("could not be saved")
    expect(field_problems(editor).locator("li")).to_contain_text(
        [re.compile('This chart has no dataset called "nope"')]
    )


def test_empty_spec_makes_edit_chart_the_main_action(editor):
    launcher = editor.locator(LAUNCHER).first
    button = launcher.locator("button")
    prompt = launcher.locator("[data-field-empty]")
    expect(button).to_have_class(re.compile("button-secondary"))
    expect(prompt).to_be_hidden()
    set_externally(spec_field(editor), "")
    expect(button).not_to_have_class(re.compile("button-secondary"))
    expect(prompt).to_be_visible()
    expect(prompt).to_contain_text("without writing JSON")
    expect(launcher.locator("[data-field-preview]")).to_be_hidden()
    assert prompt.get_attribute("id") in button.get_attribute("aria-describedby")
    # New blocks start empty
    editor.locator("button.c-sf-add-button").last.click()
    editor.get_by_role("option", name=re.compile(r"^Chart$")).click()
    new = editor.locator(LAUNCHER).last
    expect(new.locator("button")).not_to_have_class(re.compile("button-secondary"))
    expect(new.locator("[data-field-empty]")).to_be_visible()
    # No Voyager, and no "use" or "replace" step, anywhere
    for text in ("Voyager", "Use this chart", "Replace spec"):
        expect(editor.locator("body")).not_to_contain_text(text)


# -- The editor ----------------------------------------------------------------------------


def test_opens_the_fields_chart(editor, console_errors):
    textarea = spec_textarea(editor)
    original = textarea.input_value()
    count_input_events(editor)
    dialog = open_builder(editor)
    expect(dialog).to_have_attribute("aria-labelledby", re.compile("-title$"))
    expect(dialog.get_by_role("heading", name="Edit chart")).to_be_visible()
    # Focus moves to the first setting
    expect(control(dialog, "mark")).to_be_focused()
    # Visual is the default tab; the code is one tab away
    expect(dialog.get_by_role("tab", name="Visual")).to_have_attribute("aria-selected", "true")
    expect(dialog.get_by_role("tab", name="Code")).to_have_attribute("aria-selected", "false")
    expect(dialog.locator("[data-panel=code]")).to_be_hidden()
    # Grouped bars open as grouped bars
    expect(control(dialog, "mark")).to_have_value("bar")
    expect(control(dialog, "arrangement")).to_have_value("grouped")
    expect(control(dialog, "field", "color")).to_have_value("agency")
    expect(control(dialog, "chartTitle")).to_have_value("Requests by quarter")
    expect(dialog.locator("[data-kept]")).to_contain_text("encoding.x.title")
    wait_for_preview(dialog)
    expect(dialog.locator("[data-chart] svg text").first).to_have_attribute(
        "font-family", re.compile("Georgia")
    )
    expect(dialog.locator("[role=status]")).to_contain_text("Changes go into the page")
    # No "use", "replace" or "cancel" steps
    for name in ("Use this chart", "Replace spec", "Cancel", "Keep editing"):
        expect(dialog.get_by_role("button", name=name)).to_have_count(0)
    # Opening changes nothing
    expect(dialog.get_by_role("button", name="Undo changes since opening")).to_be_disabled()
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    assert textarea.input_value() == original
    assert editor.evaluate("window.__inputEvents") == 0
    assert console_errors == []


def test_close_and_escape_just_close(editor):
    textarea = spec_textarea(editor)

    # Escape from a select, after a change: the change stays
    dialog = open_builder(editor)
    choose(editor, control(dialog, "mark"), "Point")
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(trigger(editor)).to_be_focused()
    assert json.loads(textarea.input_value())["mark"] == {"type": "point", "tooltip": True}
    # ...and the field's chart shows it
    expect(field_chart(editor).locator("svg .mark-symbol.role-mark")).to_have_count(1)

    # Escape from a text field
    dialog = open_builder(editor)
    type_into(editor, control(dialog, "chartTitle"), "Changed")
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(trigger(editor)).to_be_focused()
    assert json.loads(textarea.input_value())["title"] == "Changed"
    expect(field_chart(editor)).to_contain_text("Changed")

    # The Close button, and the close icon
    for name in ("Close", "Close the chart editor"):
        dialog = open_builder(editor)
        press(editor, dialog.get_by_role("button", name=name, exact=True))
        expect(dialog).to_have_count(0)
        expect(trigger(editor)).to_be_focused()
    assert editor.locator(DIALOG).count() == 0


def test_settings_update_the_code_and_the_code_updates_the_settings(editor):
    dialog = open_builder(editor)
    choose(editor, control(dialog, "mark"), "Line")
    # Settings -> code, formatted
    code = editor_text(editor)
    assert '"type": "line"' in code
    assert code == json.dumps(json.loads(code), indent=2)
    expect(dialog.locator("[data-chart] svg .mark-line").first).to_be_visible()

    # Code -> settings and preview, by keyboard: to the tabs, then the Code tab
    tab_to(editor, dialog.get_by_role("tab", name="Visual"))
    editor.keyboard.press("ArrowRight")
    code_tab = dialog.get_by_role("tab", name="Code")
    expect(code_tab).to_be_focused()
    expect(code_tab).to_have_attribute("aria-selected", "true")
    expect(dialog.locator("[data-panel=visual]")).to_be_hidden()
    editor.keyboard.press("Tab")
    content = dialog.locator("[data-code] .cm-content")
    expect(content).to_be_focused()
    select_text(spec_field(editor), '"line"')
    editor.keyboard.type('"area"')
    expect(dialog.locator("[data-chart] svg .mark-area").first).to_be_visible()
    editor.keyboard.press("Home")  # (stay in the editor)
    dialog.get_by_role("tab", name="Visual").focus()
    editor.keyboard.press("Enter")
    expect(control(dialog, "mark")).to_have_value("area")
    # The edit reaches the field (debounced while typing)
    expect(spec_textarea(editor)).to_have_value(re.compile('"type": "area"'))


def test_invalid_json_freezes_the_settings_and_keeps_the_text(editor, console_errors):
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    svg = dialog.locator("[data-chart] svg")
    before = svg.inner_html()
    dialog.get_by_role("tab", name="Code").click()
    select_text(spec_field(editor), '"bar"')
    editor.keyboard.type('"bar",,')
    notice = dialog.locator("[data-controls-notice]")
    expect(notice).to_contain_text("The code isn't valid JSON (line")
    expect_settings_disabled(dialog)
    # The error is shown in place, and the Code tab says there's a problem
    expect(dialog.locator(".wagtail-vega-code__status")).to_contain_text("Line")
    expect(dialog.locator("[data-code-badge]")).to_be_visible()
    # The invalid text is the field's value: nothing is lost
    expect(spec_textarea(editor)).to_have_value(re.compile(r'"bar",,'))
    assert svg.inner_html() == before
    # Fixing it brings the settings back
    editor.keyboard.press("Backspace")
    editor.keyboard.press("Backspace")
    expect(notice).to_be_hidden()
    expect_settings_disabled(dialog, False)
    # Closing with invalid JSON keeps it too
    editor.keyboard.type(",")
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(spec_textarea(editor)).to_have_value(re.compile(r'"bar",'))
    assert [e for e in console_errors if "autosave" not in e.lower()] == []


def test_undo_changes_since_opening(editor):
    textarea = spec_textarea(editor)
    original = textarea.input_value()
    dialog = open_builder(editor)
    undo = dialog.get_by_role("button", name="Undo changes since opening")
    expect(undo).to_be_disabled()
    choose(editor, control(dialog, "arrangement"), "Stacked")
    type_into(editor, control(dialog, "chartTitle"), "New title")
    expect(undo).to_be_enabled()
    assert textarea.input_value() != original
    press(editor, undo)
    expect(textarea).to_have_value(original)
    expect(control(dialog, "arrangement")).to_have_value("grouped")
    expect(control(dialog, "chartTitle")).to_have_value("Requests by quarter")
    expect(undo).to_be_disabled()
    expect(dialog.locator("[role=status]")).to_contain_text("Undid the changes")
    # Ctrl/Cmd+Z in the code editor undoes edits one at a time
    choose(editor, control(dialog, "mark"), "Point")
    dialog.get_by_role("tab", name="Code").click()
    dialog.locator("[data-code] .cm-content").focus()
    editor.keyboard.press("ControlOrMeta+z")
    expect(control(dialog, "mark")).to_have_value("bar")
    expect(textarea).to_have_value(original)


def test_settings_keep_what_they_dont_edit(editor):
    dialog = open_builder(editor)
    # Grouped -> stacked: only that changes in the spec
    choose(editor, control(dialog, "arrangement"), "Stacked")
    spec = json.loads(spec_textarea(editor).input_value())
    assert spec == {**BAR, "encoding": {k: v for k, v in BAR["encoding"].items() if k != "xOffset"}}
    # Changing a field removes its kept settings, and lists them
    dropped = dialog.locator("[data-dropped]")
    choose(editor, control(dialog, "field", "x"), "agency")
    expect(dropped).to_contain_text("encoding.x.title")
    editor.wait_for_timeout(1100)  # let the select's type-ahead search end
    choose(editor, control(dialog, "field", "x"), "quarter")
    expect(dropped).to_be_empty()


def test_specs_the_settings_cant_show(editor, console_errors):
    textarea = spec_textarea(editor, VEGA)
    original = textarea.input_value()
    dialog = open_builder(editor, VEGA)
    notice = dialog.locator("[data-controls-notice]")
    expect(notice).to_contain_text("The visual settings can't show this spec: it's a Vega spec")
    expect(dialog.locator("[data-controls]")).to_be_hidden()
    # The code and preview keep working
    wait_for_preview(dialog)
    expect(dialog.locator("[data-chart] svg .mark-rect path")).not_to_have_count(0)
    dialog.get_by_role("tab", name="Code").click()
    select_text(spec_field(editor, VEGA), "steelblue")
    editor.keyboard.type("darkred")
    expect(dialog.locator("[data-chart] svg .mark-rect path").first).to_have_attribute(
        "fill", "darkred"
    )
    expect(textarea).to_have_value(re.compile("darkred"))
    # ...and a new chart can replace it
    dialog.get_by_role("tab", name="Visual").click()
    press(editor, dialog.get_by_role("button", name="Start a new chart"))
    expect(control(dialog, "mark")).to_be_focused()
    expect(textarea).to_have_value(re.compile("vega-lite/v6"))
    # Undo since opening brings back the Vega spec
    press(editor, dialog.get_by_role("button", name="Undo changes since opening"))
    expect(textarea).to_have_value(original)
    expect(notice).to_contain_text("it's a Vega spec")
    assert console_errors == []


def test_layers_open_in_the_code(editor):
    layered = {"$schema": VL, "data": {"name": "source"}, "layer": [{"mark": "bar"}]}
    set_externally(spec_field(editor), json.dumps(layered))
    dialog = open_builder(editor)
    expect(dialog.locator("[data-controls-notice]")).to_contain_text("it combines several views")
    editor.keyboard.press("Escape")
    assert json.loads(spec_textarea(editor).input_value()) == layered


# Wagtail's autosave (7.4 and 8.x behave the same): the edit form's
# w-unsaved controller takes a snapshot of the form's data 2 s after the
# page loads ("w-unsaved:watch-edits"), then compares the form's data with
# it every 500 ms. When it differs, w-autosave POSTs the form to the edit
# URL with "Accept: application/json" (debounced by
# WAGTAIL_AUTOSAVE_INTERVAL, 500 ms by default). A valid form saves a
# revision and returns 200 {"success": true, "revision_id": ...}; a form
# with errors saves nothing and returns 400 {"success": false,
# "error_code": "validation_error"}, and the indicator shows "paused".
# Autosave stays on, so the next valid change is saved.


@pytest.fixture
def autosave_editor(admin_page, live_server, chart_page, settings):
    """The edit page, with autosave on (Wagtail's default interval), once
    Wagtail has started watching it for edits."""
    settings.WAGTAIL_AUTOSAVE_INTERVAL = 500
    admin_page.add_init_script(
        """document.addEventListener("w-unsaved:watch-edits", () => {
            window.__watchingEdits = true;
        });"""
    )
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
    admin_page.wait_for_function("window.__watchingEdits === true")
    return admin_page


def is_autosave(response, chart_page):
    request = response.request
    return (
        request.method == "POST"
        and request.url.endswith(reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
        and "application/json" in (request.headers.get("accept") or "")
    )


def autosave_indicator(page):
    return page.locator("#w-autosave-indicator")


def wait_for_saved_spec(page, chart_page, check, timeout=15_000):
    """Wait until the latest revision's first chart spec passes `check`
    (autosave may save a few revisions while the editor types)."""
    for _ in range(timeout // 250):
        # Not while the live server is using the shared test database
        with DATABASE_LOCK:
            revision = ChartPage.objects.get(pk=chart_page.pk).get_latest_revision_as_object()
        spec = revision.body[0].value["spec"]
        if check(spec):
            return spec
        page.wait_for_timeout(250)
    raise AssertionError(f"Not autosaved: the latest revision has {spec!r}")


def test_autosave_saves_edits_made_in_the_editor(autosave_editor, chart_page):
    """Edits in the editor reach the form as they're made, so Wagtail
    autosaves them, with the editor still open."""
    page = autosave_editor
    with DATABASE_LOCK:
        before = chart_page.revisions.count()
    dialog = open_builder(page)
    with page.expect_response(lambda r: is_autosave(r, chart_page), timeout=15_000) as info:
        type_into(page, control(dialog, "chartTitle"), "Autosaved title")
    response = info.value
    assert response.status == 200
    body = response.json()
    assert body["success"] is True
    assert body["revision_id"]
    expect(autosave_indicator(page)).to_have_attribute("data-w-autosave-state-value", "saved")
    wait_for_saved_spec(page, chart_page, lambda spec: spec.get("title") == "Autosaved title")
    with DATABASE_LOCK:
        assert ChartPage.objects.get(pk=chart_page.pk).revisions.count() > before
    expect(dialog).to_be_visible()


def test_autosave_with_invalid_json_loses_nothing(autosave_editor, chart_page):
    """Invalid JSON is written to the field too. Wagtail refuses to autosave
    it (and says so); nothing is lost, and the fix is autosaved."""
    page = autosave_editor
    dialog = open_builder(page)
    dialog.get_by_role("tab", name="Code").click()
    select_text(spec_field(page), '"Requests by quarter"')
    with page.expect_response(lambda r: is_autosave(r, chart_page), timeout=15_000) as info:
        page.keyboard.type('"Half typed')
        dialog.get_by_role("tab", name="Code").focus()  # blur: written now
    response = info.value
    assert response.status == 400
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "validation_error"
    expect(autosave_indicator(page)).to_have_attribute("data-w-autosave-state-value", "paused")
    # Nothing is lost: the field and the editor keep the text
    expect(spec_textarea(page)).to_have_value(re.compile('"Half typed'))
    assert '"Half typed' in editor_text(page)
    expect(dialog).to_be_visible()
    # The fix is autosaved
    with page.expect_response(
        lambda r: is_autosave(r, chart_page) and r.status == 200, timeout=15_000
    ):
        select_text(spec_field(page), '"Half typed')
        page.keyboard.type('"Fixed title"')
        dialog.get_by_role("tab", name="Code").focus()
    expect(autosave_indicator(page)).to_have_attribute("data-w-autosave-state-value", "saved")
    wait_for_saved_spec(page, chart_page, lambda spec: spec.get("title") == "Fixed title")


def test_lightbox_is_modal(editor):
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    assert editor.evaluate("document.querySelector('dialog').matches(':modal')")
    assert editor.evaluate("document.elementFromPoint(5, 5) === document.querySelector('dialog')")
    dialog.get_by_role("button", name="Close", exact=True).focus()
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
    expect(dialog.get_by_role("tablist", name="Edit the chart")).to_be_visible()
    expect(dialog.get_by_role("tabpanel", name="Visual")).to_be_visible()


def test_suggestions(editor):
    set_externally(spec_field(editor), "")
    dialog = open_builder(editor)
    suggestions = dialog.locator("[data-suggestions]")
    expect(suggestions).to_have_attribute("open", "")
    press(editor, dialog.get_by_role("button", name="Pie: share of requests by agency"))
    expect(control(dialog, "mark")).to_have_value("arc")
    expect(spec_textarea(editor)).to_have_value(re.compile('"theta"'))
    expect(dialog.locator("[role=status]")).to_contain_text("Chart set to")


def test_preview_in_dark_mode(editor):
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    title = dialog.locator("[data-chart] svg .role-title text")
    expect(title).to_have_attribute("fill", "#111")
    choose(editor, dialog.get_by_label("Colours"), "Dark mode")
    expect(title).to_have_attribute("fill", "#fff")


def test_charts_with_data_from_code(editor, console_errors):
    """A BaseChartBlock subclass with no data field: the code and preview
    work, the visual settings say why they can't."""
    textarea = spec_textarea(editor, DONATIONS)
    dialog = open_builder(editor, DONATIONS)
    expect(dialog.locator("[data-controls-notice]")).to_contain_text("data comes from code")
    expect_settings_disabled(dialog)
    expect(dialog.locator("[data-warnings]")).to_contain_text("data comes from code")
    dialog.get_by_role("tab", name="Code").click()
    select_text(spec_field(editor, DONATIONS), "Donations (from the database)")
    editor.keyboard.type("Donations by month")
    editor.keyboard.press("Escape")
    expect(textarea).to_have_value(re.compile("Donations by month"))
    assert console_errors == []


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
    expect(dialog.locator("[data-controls-notice]")).to_contain_text("need a dataset with data")


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


def test_datasets_from_code_are_listed_but_not_previewed(editor):
    spec_field(editor).evaluate(
        """(el) => el.closest("[data-contentpath]").parentElement
            .setAttribute("data-wagtail-vega-extra-datasets", '["totals"]')"""
    )
    set_externally(spec_field(editor), json.dumps({**BAR, "data": {"name": "totals"}}))
    dialog = open_builder(editor)
    picker = dialog.get_by_label("Dataset")
    expect(picker).to_be_visible()
    expect(picker).to_have_value("source")
    option = picker.locator('option[value="totals"]')
    expect(option).to_have_text("totals (from code, can't be previewed here)")
    expect(option).to_be_disabled()
    expect(dialog.locator("[data-controls-notice]")).to_contain_text(
        "The spec uses “totals”, whose data comes from code"
    )


def test_several_datasets_offer_a_picker(editor):
    data_list = editor.locator('[data-contentpath="data"]').first
    data_list.locator("button[data-streamfield-list-add]").last.click()
    new = data_list.locator(".wagtail-vega-dataset").last
    new.locator('[data-contentpath="name"] input').fill("budget")
    fill_editor(new.locator('[data-contentpath="paste"]'), "year,amount\n2025,100\n2026,120")

    dialog = open_builder(editor)
    picker = dialog.get_by_label("Dataset")
    expect(picker).to_be_focused()
    expect(picker).to_have_value("source")
    wait_for_preview(dialog)
    choose(editor, picker, "budget")
    expect(dialog.locator("[role=status]")).to_contain_text("doesn't have the fields")
    expect(control(dialog, "field", "x")).to_contain_text("amount (number)")
    choose(editor, control(dialog, "field", "x"), "year")
    choose(editor, control(dialog, "field", "y"), "amount")
    spec = json.loads(spec_textarea(editor).input_value())
    assert spec["data"] == {"name": "budget"}
    assert spec["title"] == "Requests by quarter"


def test_new_chart_blocks(editor):
    """Blocks added after page load (telepath-rendered) work too."""
    editor.locator("button.c-sf-add-button").last.click()
    editor.get_by_role("option", name=re.compile(r"^Chart$")).click()
    launchers = editor.locator(LAUNCHER)
    expect(launchers).to_have_count(5)
    dataset = editor.locator('[data-contentpath="data"]').last.locator(".wagtail-vega-dataset")
    fill_editor(dataset.locator('[data-contentpath="paste"]'), "fruit,count\napple,3\npear,5")
    dialog = open_builder(editor, 4)
    wait_for_preview(dialog)
    expect(control(dialog, "field", "x")).to_have_value("fruit")
    choose(editor, control(dialog, "mark"), "Point")
    editor.keyboard.press("Escape")
    expect(launchers.last.locator("button")).to_be_focused()
    spec = json.loads(spec_textarea(editor, 4).input_value())
    assert spec["encoding"]["x"]["field"] == "fruit"
    expect(field_chart(editor, 4).locator("svg")).to_have_count(1)


def test_label_focuses_the_button(editor):
    spec_field(editor).locator("label").first.click()
    expect(trigger(editor)).to_be_focused()


def test_narrow_screens(editor):
    editor.set_viewport_size({"width": 390, "height": 844})
    dialog = open_builder(editor)
    wait_for_preview(dialog)
    assert dialog.evaluate("(d) => d.scrollWidth <= d.clientWidth + 1")
    panes = dialog.locator(".wagtail-vega-builder__panes").bounding_box()
    preview = dialog.locator("[data-preview]").bounding_box()
    assert preview["y"] >= panes["y"] + panes["height"] - 1
    dialog.get_by_role("tab", name="Code").click()
    box = dialog.locator("[data-code] .cm-editor").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390


def test_preview_needs_no_unsafe_eval(admin_page, live_server, chart_page, console_errors):
    """The previews run under an admin CSP without 'unsafe-eval'."""
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
    expect(field_chart(admin_page).locator("svg")).to_have_count(1)
    dialog = open_builder(admin_page)
    wait_for_preview(dialog)
    choose(admin_page, control(dialog, "mark"), "Line")
    expect(dialog.locator("[data-chart] svg .mark-line").first).to_be_visible()
    assert [e for e in console_errors if "eval" in e] == []
    expect(dialog.locator("[data-warnings]")).to_be_empty()


def test_large_datasets_are_previewed_from_a_sample(editor):
    editor.locator(LAUNCHER).nth(WEATHER).evaluate(
        "(el) => { el.dataset.config = JSON.stringify({...JSON.parse(el.dataset.config),"
        " previewRows: 10}); }"
    )
    dialog = open_builder(editor, WEATHER)
    wait_for_preview(dialog)
    expect(dialog.locator("[data-warnings]")).to_contain_text(
        "The preview shows the first 10 of 48 rows. The chart on the page uses them all."
    )
    assert "datasets" not in json.loads(editor_text(editor, WEATHER))
