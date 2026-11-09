"""The admin's code editors (CodeMirror) for specs and pasted data.

TODO-23: spec fields now hide their editor until "Edit chart" opens the
dialog, so the spec tests here still drive an inline editor and need
updating (see the draft PR for #23)."""

import json
import re

import pytest
from django.urls import reverse
from playwright.sync_api import expect

from tests.testapp.demo import BAR
from tests.testapp.models import ChartPage

from .editor import fill_editor, select_text, set_externally

pytestmark = pytest.mark.e2e

SPEC = '[data-contentpath="spec"]'
PASTE = '[data-contentpath="paste"]'
VALIDATE_URL = "/admin/wagtail-vega/validate-spec/"


@pytest.fixture
def editor(admin_page, live_server, chart_page):
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
    expect(admin_page.locator(f"{SPEC} .cm-editor").first).to_be_visible()
    return admin_page


def spec_field(page):
    return page.locator(SPEC).first


def underlined(field, severity="error"):
    return field.locator(f".cm-lintRange-{severity}")


def save_draft(page):
    page.locator("button.action-save").first.click()
    page.wait_for_load_state("networkidle")


def latest_body(chart_page):
    return ChartPage.objects.get(pk=chart_page.pk).get_latest_revision_as_object().body


def test_editors_replace_the_code_textareas(editor, console_errors):
    spec = spec_field(editor)
    expect(spec.locator(".cm-editor")).to_be_visible()
    expect(spec.locator("textarea")).to_be_hidden()
    expect(spec.locator(".cm-content")).to_contain_text('"$schema"')
    # JSON highlighting
    expect(spec.locator(".tok-propertyName").first).to_have_text('"$schema"')
    # Every spec, including the developer-defined chart block's
    expect(editor.locator(f"{SPEC} .cm-editor")).to_have_count(4)

    paste = editor.locator(PASTE).first
    expect(paste.locator(".cm-editor")).to_be_visible()
    expect(paste.locator("textarea")).to_be_hidden()
    # Tabs are shown, and the TSV isn't highlighted as JSON
    expect(paste.locator(".cm-highlightTab").first).to_be_visible()
    expect(paste.locator(".tok-propertyName")).to_have_count(0)
    # The pasted JSON dataset is highlighted
    expect(editor.locator(f"{PASTE} .tok-propertyName").first).to_be_visible()

    # Labelled by the field's label, and clicking the label focuses it
    content = spec.locator(".cm-content")
    label_id = content.get_attribute("aria-labelledby")
    label = editor.locator(f"#{label_id}")
    expect(label).to_contain_text("Spec")
    label.click()
    expect(content).to_be_focused()
    assert console_errors == []


def test_tab_moves_focus_out_of_the_editor(editor):
    content = spec_field(editor).locator(".cm-content")
    content.click()
    before = spec_field(editor).locator("textarea").input_value()
    editor.keyboard.press("Tab")
    expect(content).not_to_be_focused()
    assert spec_field(editor).locator("textarea").input_value() == before


def test_invalid_json_is_underlined(editor):
    spec = spec_field(editor)
    fill_editor(spec, '{\n  "mark": "bar",\n  "encoding": {"x": 1,}\n}')
    expect(underlined(spec)).to_have_text(",")
    status = spec.locator(".wagtail-vega-code__status")
    expect(status).to_have_text("Line 3: Trailing commas aren't allowed in JSON")
    expect(spec.locator(".cm-content")).to_have_attribute(
        "aria-describedby", re.compile("helptext")
    )

    underlined(spec).hover()
    expect(editor.locator(".cm-tooltip-lint")).to_contain_text("Trailing commas")

    fill_editor(spec, '{"mark": "bar"}')
    expect(underlined(spec)).to_have_count(0)


def test_schema_error_is_underlined_at_its_node(editor):
    spec = spec_field(editor)
    requests = []
    editor.on("request", lambda r: VALIDATE_URL in r.url and requests.append(r))

    # Edit "nominal" -> "nominl" in the x encoding, by typing
    select_text(spec, "nominal")
    editor.keyboard.type("nominl")
    expect(underlined(spec)).to_have_text('"nominl"')
    expect(spec.locator(".wagtail-vega-code__status")).to_contain_text(
        "Line 15: 'nominl' is not valid under any of the given schemas"
    )
    assert requests and requests[-1].method == "POST"
    assert "nominl" in requests[-1].post_data

    # A host that isn't allowed
    select_text(spec, "nominl")
    editor.keyboard.type("nominal")
    set_externally(
        spec,
        json.dumps({**BAR, "data": {"url": "https://evil.example/x.csv"}}, indent=2),
    )
    expect(underlined(spec)).to_have_text('"https://evil.example/x.csv"')
    expect(spec.locator(".wagtail-vega-code__status")).to_contain_text(
        "Loading data from https://evil.example/x.csv is not allowed."
    )


def test_failed_save_highlights_server_errors_in_place(editor, chart_page):
    revisions = chart_page.revisions.count()
    spec = spec_field(editor)
    bad = {**BAR, "data": {"url": "https://evil.example/x.csv"}}
    bad["encoding"] = {**BAR["encoding"], "x": {**BAR["encoding"]["x"], "type": "nominl"}}
    set_externally(spec, json.dumps(bad, indent=2))
    save_draft(editor)
    expect(editor.locator(".messages")).to_contain_text("could not be saved")
    assert chart_page.revisions.count() == revisions

    # After the reload, the errors come from the save, not live validation
    requests = []
    editor.on("request", lambda r: VALIDATE_URL in r.url and requests.append(r))
    spec = spec_field(editor)
    expect(spec).to_contain_text("encoding.x.type: 'nominl' is not valid")
    expect(underlined(spec)).to_have_text(['"https://evil.example/x.csv"', '"nominl"'])
    underlined(spec).last.hover()
    expect(editor.locator(".cm-tooltip-lint")).to_contain_text(
        "'nominl' is not valid under any of the given schemas"
    )
    expect(spec.locator(".wagtail-vega-code")).to_have_class(re.compile("is-invalid"))
    assert requests == []

    # Fixing it clears the highlight
    select_text(spec, "nominl")
    editor.keyboard.type("nominal")
    expect(underlined(spec)).to_have_text(['"https://evil.example/x.csv"'])


def test_external_input_event_updates_the_editor(editor):
    spec = spec_field(editor)
    textarea = spec.locator("textarea")
    textarea.evaluate(
        """(t) => {
            window.inputEvents = 0;
            t.addEventListener("input", () => window.inputEvents++);
        }"""
    )
    new = json.dumps({**BAR, "title": "From the chart builder"}, indent=2)
    set_externally(spec, new)
    expect(spec.locator(".cm-content")).to_contain_text('"title": "From the chart builder"')
    # No feedback loop: only the external event fired, and the value stuck
    assert editor.evaluate("window.inputEvents") == 1
    assert textarea.input_value() == new

    # The external change is one undoable edit
    spec.locator(".cm-content").click()
    editor.keyboard.press("ControlOrMeta+z")
    expect(spec.locator(".cm-content")).to_contain_text('"title": "Requests by quarter"')
    expect(textarea).to_have_value(re.compile('"title": "Requests by quarter"'))


def test_typing_updates_the_textarea(editor):
    spec = spec_field(editor)
    select_text(spec, "Requests")
    editor.keyboard.type("Typed")
    expect(spec.locator("textarea")).to_have_value(re.compile('"title": "Typed by quarter"'))


def test_paste_problems_are_marked_in_place(editor):
    paste = editor.locator(PASTE).first
    fill_editor(paste, "year\tcount\n2024\t10\n2025\n2026\t12\t9")
    expect(underlined(paste, "warning")).to_have_text(["2025", "2026\t12\t9"])
    underlined(paste, "warning").first.hover()
    expect(editor.locator(".cm-tooltip-lint")).to_contain_text(
        "Line 3 has 1 value but there are 2 columns."
    )

    fill_editor(paste, '[{"a": 1}, {"a": 2,}]')
    expect(underlined(paste)).to_have_text(",")
    expect(paste.locator(".tok-propertyName").first).to_have_text('"a"')
    expect(paste.locator(".wagtail-vega-summary")).to_contain_text("Trailing commas")


def test_saving_round_trips_editor_content(editor, chart_page):
    spec = spec_field(editor)
    select_text(spec, "Requests")
    editor.keyboard.type("Typed")
    paste = editor.locator(PASTE).first
    data = "quarter\trequests\nQ1\t5\nQ2\t7"
    fill_editor(paste, data)
    save_draft(editor)
    expect(editor.locator(".messages")).to_contain_text("has been updated")

    chart = latest_body(chart_page)[0].value
    assert chart["spec"] == {**BAR, "title": "Typed by quarter"}
    # Browsers submit textarea line breaks as CRLF, as they always have
    assert chart["data"][0]["paste"].replace("\r\n", "\n") == data

    # And it's shown again after the reload
    expect(spec_field(editor).locator(".cm-content")).to_contain_text('"Typed by quarter"')
    expect(editor.locator(PASTE).first.locator("textarea")).to_have_value(data)
