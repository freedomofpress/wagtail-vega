"""The "Build chart with Voyager" lightbox, end to end: real Wagtail admin,
real Voyager in its sandboxed iframe."""

import json
import re

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from playwright.sync_api import expect
from wagtail.documents import get_document_model
from wagtail.models import Collection

from tests.testapp.models import ChartPage

from .editor import fill_editor

pytestmark = pytest.mark.e2e

VL = "https://vega.github.io/schema/vega-lite/v6.json"
LAUNCHER = "wagtail-vega-voyager"
DIALOG = "dialog.wagtail-vega-voyager"
# Voyager's start-up and data loading can be slow in CI
VOYAGER_TIMEOUT = 20_000


@pytest.fixture
def editor(admin_page, live_server, chart_page):
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
    expect(admin_page.locator(LAUNCHER)).to_have_count(4)
    return admin_page


def spec_field(page, index=0):
    return page.locator('[data-contentpath="spec"]').nth(index)


def spec_textarea(page, index=0):
    # Hidden behind the code editor, but still the field's value
    return spec_field(page, index).locator("textarea")


def editor_text(page, index=0):
    return spec_textarea(page, index).evaluate(
        "(t) => t.wagtailVegaEditor.view.state.doc.toString()"
    )


def open_voyager(page, index=0):
    page.locator(LAUNCHER).nth(index).locator("button").click()
    dialog = page.locator(DIALOG)
    expect(dialog).to_be_visible()
    return dialog, page.frame_locator(f"{DIALOG} iframe")


def wait_for_fields(frame, *names):
    for name in names:
        expect(frame.get_by_text(name, exact=True).first).to_be_visible(timeout=VOYAGER_TIMEOUT)


def count_input_events(page, index=0):
    page.evaluate(
        """(i) => {
            const t = document.querySelectorAll('[data-contentpath="spec"] textarea')[i];
            window.__inputEvents = 0;
            t.addEventListener("input", (e) => { if (e.bubbles) window.__inputEvents++; });
        }""",
        index,
    )


def save_draft(page):
    page.locator("button.action-save").first.click()
    page.wait_for_load_state("networkidle")


def test_opens_lightbox_with_the_dataset(editor, console_errors):
    dialog, frame = open_voyager(editor)
    expect(dialog).to_have_attribute("aria-labelledby", re.compile("-title$"))
    expect(dialog.get_by_role("heading")).to_have_text("Build a chart with Voyager")
    iframe = dialog.locator("iframe")
    expect(iframe).to_have_attribute("sandbox", "allow-scripts")
    expect(iframe).to_have_attribute("title", "Voyager chart builder")

    # The pasted TSV's columns, as Voyager fields
    wait_for_fields(frame, "quarter", "agency", "requests")
    # The field's Vega-Lite spec was opened, so "Use" is ready
    expect(dialog.locator("[role=status]")).to_contain_text("Opened the field's current chart")
    expect(dialog.get_by_role("button", name="Use this chart")).to_be_enabled()
    # One dataset: no picker
    expect(dialog.locator("[data-dataset-picker]")).to_be_hidden()
    # Voyager's own data loader is hidden: data comes from the chart
    expect(frame.get_by_role("button", name="Change")).to_have_count(0)

    # Focus moved into the lightbox
    assert editor.evaluate("document.activeElement.closest('dialog') !== null")
    # Voyager (React 15, vega 4) stays inside the iframe
    assert editor.evaluate("typeof window.voyager") == "undefined"
    assert editor.locator('script[src*="vendor/voyager"]').count() == 0
    assert console_errors == []


def test_build_chart_and_use_it(editor, chart_page, console_errors):
    # Report CSP violations from every frame, including Voyager's sandbox
    editor.add_init_script(
        """document.addEventListener("securitypolicyviolation", (e) =>
            console.error(`CSP violation: ${e.violatedDirective} ${e.blockedURI}`))"""
    )
    editor.reload()
    textarea = spec_textarea(editor)
    fill_editor(spec_field(editor), "")
    expect(textarea).to_have_value("")
    count_input_events(editor)
    # Record the specs Voyager reports, as the launcher receives them
    editor.evaluate(
        """() => window.addEventListener("message", (e) => {
            if (e.data?.channel === "wagtail-vega-voyager" && e.data.type === "spec") {
                window.__voyagerSpec = e.data.spec;
            }
        })"""
    )
    dialog, frame = open_voyager(editor)
    wait_for_fields(frame, "quarter", "requests")
    use = dialog.get_by_role("button", name="Use this chart")
    expect(use).to_be_disabled()
    expect(dialog.locator("[role=status]")).to_contain_text("Drag fields")

    # Double-clicking a field adds it to the encoding shelves
    # Add one field at a time, waiting for each to land on a shelf: Voyager
    # drops a double-click that arrives while it's still handling the last,
    # and "Use" is enabled as soon as the first field is placed.
    shelves = frame.locator(".encoding-shelf__field-wrapper")
    for name in ("quarter", "requests"):
        frame.locator(".field-list__field-list-item").get_by_text(name, exact=True).dblclick()
        expect(shelves.get_by_text(name, exact=True)).to_be_visible(timeout=VOYAGER_TIMEOUT)
    # Voyager reports its spec to the launcher shortly after each change
    # (debounced), so wait until the launcher has the two-field chart.
    editor.wait_for_function(
        """() => {
            const fields = Object.values(window.__voyagerSpec?.encoding || {}).map((d) => d.field);
            return fields.includes("quarter") && fields.includes("requests");
        }""",
        timeout=VOYAGER_TIMEOUT,
    )
    expect(use).to_be_enabled(timeout=VOYAGER_TIMEOUT)
    use.click()

    # The field was empty, so no confirmation is needed
    expect(dialog).to_have_count(0)
    spec = json.loads(textarea.input_value())
    assert spec["$schema"] == VL
    assert spec["data"] == {"name": "source"}
    assert isinstance(spec["mark"], str)
    fields = {d.get("field") for d in spec["encoding"].values()}
    assert {"quarter", "requests"} <= fields
    assert "values" not in json.dumps(spec)
    # The code editor picked it up (the textarea + "input" contract)
    assert editor_text(editor) == textarea.input_value()
    # Written through the textarea, with one bubbling input event
    assert editor.evaluate("window.__inputEvents") == 1
    # Focus is back on the button that opened the lightbox
    expect(editor.locator(LAUNCHER).first.locator("button")).to_be_focused()
    expect(editor.locator(LAUNCHER).first.locator("[data-voyager-note]")).to_have_text(
        "The chart from Voyager is now in the spec field."
    )

    # Saving validates the spec on the server
    save_draft(editor)
    expect(editor.locator(".messages")).to_contain_text("has been updated")
    expect(editor.locator(".messages")).not_to_contain_text("could not be saved")
    revision = ChartPage.objects.get(pk=chart_page.pk).get_latest_revision_as_object()
    assert revision.body[0].value["spec"] == spec
    # Nothing was blocked by the Voyager page's CSP (or anything else)
    assert [e for e in console_errors if "CSP violation" in e] == []


def test_confirms_before_replacing_a_spec(editor):
    textarea = spec_textarea(editor)
    original = textarea.input_value()
    count_input_events(editor)
    dialog, frame = open_voyager(editor)
    wait_for_fields(frame, "quarter")
    use = dialog.get_by_role("button", name="Use this chart")
    expect(use).to_be_enabled(timeout=VOYAGER_TIMEOUT)
    frame.locator("select").first.select_option("point")  # Voyager's mark menu
    # Voyager recomputes its chart asynchronously; a spec that changes after
    # "Use" is clicked (correctly) cancels the confirmation, so let it settle
    editor.wait_for_timeout(1000)

    use.click()
    replace = dialog.get_by_role("button", name="Replace spec")
    expect(replace).to_be_focused()
    expect(dialog).to_contain_text("This replaces the spec that's in the field now.")
    assert textarea.input_value() == original

    dialog.get_by_role("button", name="Keep editing").click()
    expect(replace).to_be_hidden()
    expect(use).to_be_focused()
    assert textarea.input_value() == original

    use.click()
    replace.click()
    expect(dialog).to_have_count(0)
    spec = json.loads(textarea.input_value())
    assert spec["mark"] == "point"
    assert spec["data"] == {"name": "source"}
    # Presentation settings are kept from the spec it replaced
    assert spec["title"] == "Requests by quarter"
    assert spec["width"] == "container"
    assert editor.evaluate("window.__inputEvents") == 1
    assert editor_text(editor) == textarea.input_value()

    # ...and one Ctrl/Cmd+Z in the code editor brings the old spec back
    spec_field(editor).locator(".cm-content").click()
    editor.keyboard.press("ControlOrMeta+z")
    expect(textarea).to_have_value(original)


def test_cancel_and_escape_leave_the_field_unchanged(editor):
    textarea = spec_textarea(editor)
    original = textarea.input_value()
    count_input_events(editor)
    trigger = editor.locator(LAUNCHER).first.locator("button")

    # Cancel button
    dialog, frame = open_voyager(editor)
    wait_for_fields(frame, "quarter")
    frame.locator("select").first.select_option("point")
    dialog.get_by_role("button", name="Cancel").click()
    expect(dialog).to_have_count(0)
    expect(trigger).to_be_focused()

    # Escape, with focus in the lightbox's own controls
    dialog, frame = open_voyager(editor)
    wait_for_fields(frame, "quarter")
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(trigger).to_be_focused()

    # Escape, with focus inside Voyager's iframe
    dialog, frame = open_voyager(editor)
    wait_for_fields(frame, "quarter")
    frame.locator("select").first.focus()
    frame.locator("select").first.press("Escape")
    expect(dialog).to_have_count(0)
    expect(trigger).to_be_focused()

    # The close button
    dialog, frame = open_voyager(editor)
    dialog.get_by_role("button", name="Close without using the chart").click()
    expect(dialog).to_have_count(0)

    assert textarea.input_value() == original
    assert editor.evaluate("window.__inputEvents") == 0


def test_lightbox_is_modal(editor):
    dialog, frame = open_voyager(editor)
    wait_for_fields(frame, "quarter")
    # showModal() makes everything outside the dialog inert
    assert editor.evaluate("document.querySelector('dialog').matches(':modal')")
    # Pointer events outside the lightbox hit its backdrop, not the page
    assert editor.evaluate("document.elementFromPoint(5, 5) === document.querySelector('dialog')")
    # Tabbing from the last control stays in the dialog rather than reaching the page
    dialog.get_by_role("button", name="Use this chart").focus()
    editor.keyboard.press("Tab")
    assert editor.evaluate(
        "!document.activeElement || document.activeElement === document.body"
        " || document.activeElement.closest('dialog') !== null"
    )


def test_disabled_when_data_comes_from_code(editor):
    launcher = editor.locator(LAUNCHER).nth(2)  # DonationsChartBlock
    button = launcher.locator("button")
    expect(button).to_be_disabled()
    note = launcher.locator("[data-voyager-note]")
    expect(note).to_have_text(
        "Voyager works with datasets added in this form. This chart's data comes from code."
    )
    expect(button).to_have_attribute("aria-describedby", note.get_attribute("id"))


def test_url_dataset(editor, console_errors):
    dialog, frame = open_voyager(editor, 3)  # /static/testapp/weather.csv
    wait_for_fields(frame, "date", "weather", "precipitation")
    assert console_errors == []


def test_url_dataset_on_a_disallowed_host(editor):
    data = editor.locator('[data-contentpath="data"]').nth(2)
    url = data.locator('[data-contentpath="url"] input')
    url.fill("https://evil.example/data.csv")
    dialog, frame = open_voyager(editor, 3)
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
    dialog, frame = open_voyager(editor)
    wait_for_fields(frame, "region", "sales")


def test_several_datasets_offer_a_picker(editor):
    data_list = editor.locator('[data-contentpath="data"]').first
    data_list.locator("button[data-streamfield-list-add]").last.click()
    new = data_list.locator(".wagtail-vega-dataset").last
    new.locator('[data-contentpath="name"] input').fill("budget")
    fill_editor(new.locator('[data-contentpath="paste"]'), "year,amount\n2025,100\n2026,120")

    dialog, frame = open_voyager(editor)
    picker = dialog.get_by_label("Dataset")
    expect(picker).to_be_visible()
    expect(picker).to_have_value("source")  # the one the spec refers to
    wait_for_fields(frame, "quarter")

    picker.select_option("budget")
    wait_for_fields(frame, "year", "amount")
    frame.get_by_text("year", exact=True).first.dblclick()
    frame.get_by_text("amount", exact=True).first.dblclick()
    use = dialog.get_by_role("button", name="Use this chart")
    expect(use).to_be_enabled(timeout=VOYAGER_TIMEOUT)
    use.click()
    dialog.get_by_role("button", name="Replace spec").click()
    assert json.loads(spec_textarea(editor).input_value())["data"] == {"name": "budget"}


def test_new_chart_blocks_get_the_button(editor):
    """Blocks added after page load (telepath-rendered) get a working button."""
    editor.locator("button.c-sf-add-button").last.click()
    editor.get_by_role("option", name=re.compile(r"^Chart$")).click()
    launchers = editor.locator(LAUNCHER)
    expect(launchers).to_have_count(5)
    new = launchers.last
    new.locator("button").click()
    # A new chart starts with one empty dataset
    note = new.locator("[data-voyager-note]")
    expect(note).to_have_text(
        "Add data to this chart's datasets first, then build the chart from it."
    )
    expect(editor.locator(DIALOG)).to_have_count(0)

    dataset = editor.locator('[data-contentpath="data"]').last.locator(".wagtail-vega-dataset")
    fill_editor(dataset.locator('[data-contentpath="paste"]'), "fruit,count\napple,3\npear,5")
    dialog, frame = open_voyager(editor, 4)
    expect(note).to_be_hidden()
    wait_for_fields(frame, "fruit", "count")
    dialog.get_by_role("button", name="Cancel").click()
    expect(new.locator("button")).to_be_focused()


def test_button_sits_above_the_code_editor(editor):
    """The button is part of the spec field's code editor widget: above the
    editor, without hiding it or taking its place."""
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
    # Typing in the editor still works with the button there
    fill_editor(spec_field(editor), '{"a": 1}')
    expect(spec_textarea(editor)).to_have_value('{"a": 1}')


def test_new_blocks_get_both_editor_and_button(editor):
    editor.locator("button.c-sf-add-button").last.click()
    editor.get_by_role("option", name=re.compile(r"^Chart$")).click()
    field = spec_field(editor, 4)
    expect(field.locator(LAUNCHER)).to_be_visible()
    expect(field.locator(".wagtail-vega-code--spec")).to_be_visible()
