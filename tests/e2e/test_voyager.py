"""The chart editor's Voyager mode, end to end: the real Wagtail admin, and
real Voyager in its sandboxed iframe.

Voyager is slow to start and reports its chart asynchronously (its own
state changes, then 100 ms in our frame). So these tests never sleep and
hope: they wait for fields to land on Voyager's shelves, for the reports
the admin page receives (recorded by `record_reports`), and for the field
to have the value they expect. Fields are added one at a time, because
Voyager drops a double-click that arrives while it's handling the last.
"""

import json
import re

import pytest
from django.urls import reverse
from playwright.sync_api import expect

from tests.testapp.demo import BAR, create_demo_page, custom_source_chart
from tests.testapp.middleware import DATABASE_LOCK
from tests.testapp.models import ChartPage

from .editor import fill_editor, set_externally

pytestmark = pytest.mark.e2e

VL = "https://vega.github.io/schema/vega-lite/v6.json"
LAUNCHER = "wagtail-vega-chart-builder"
DIALOG = "dialog.wagtail-vega-builder"
REQUESTS, VEGA, DONATIONS, WEATHER = range(4)
# Voyager's start-up and data loading can be slow in CI
VOYAGER_TIMEOUT = 20_000
GROUPED_WARNING = "grouped bars: Voyager shows them stacked"


@pytest.fixture(autouse=True)
def _visual_editor():
    """Voyager is the default here (conftest.py's fixture picks Simple)."""


@pytest.fixture
def editor(admin_page, live_server, chart_page):
    record_reports(admin_page)
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
    expect(admin_page.locator(LAUNCHER)).to_have_count(4)
    return admin_page


def record_reports(page):
    """Record CSP violations (in every frame, Voyager's included) as console
    errors, and the charts Voyager reports to the admin page."""
    page.add_init_script(
        """
        document.addEventListener("securitypolicyviolation", (e) =>
            console.error(`CSP violation: ${e.violatedDirective} ${e.blockedURI}`));
        if (window.top === window) {
            window.__voyager = [];
            window.addEventListener("message", (e) => {
                if (e.data?.channel === "wagtail-vega-voyager") window.__voyager.push(e.data);
            });
        }
        """
    )


def spec_field(page, index=0):
    return page.locator('[data-contentpath="spec"]').nth(index)


def spec_textarea(page, index=0):
    return spec_field(page, index).locator("textarea")


def field_spec(page, index=0):
    return json.loads(spec_textarea(page, index).input_value())


def open_editor(page, index=0):
    page.locator(LAUNCHER).nth(index).locator("[data-builder-open]").click()
    dialog = page.locator(DIALOG)
    expect(dialog).to_be_visible()
    return dialog, page.frame_locator(f"{DIALOG} iframe")


def wait_for_voyager(frame, *fields):
    """Voyager has started, with these fields in its data panel."""
    items = frame.locator(".field-list__field-list-item")
    for name in fields or (None,):
        target = items.get_by_text(name, exact=True) if name else items
        expect(target.first).to_be_visible(timeout=VOYAGER_TIMEOUT)


def wait_for_report(page, condition="true"):
    """Wait for a chart Voyager reported after the editor did something in
    it, matching `condition` (JS, with `spec`)."""
    page.wait_for_function(
        f"""() => (window.__voyager || []).some((m) => {{
            if (m.type !== "spec" || !m.user) return false;
            const spec = m.spec;
            return Boolean({condition});
        }})""",
        timeout=VOYAGER_TIMEOUT,
    )


def wait_for_baseline(page):
    """Voyager has reported the chart it opened (the admin's baseline)."""
    page.wait_for_function(
        "() => (window.__voyager || []).some((m) => m.type === 'spec' && !m.user)",
        timeout=VOYAGER_TIMEOUT,
    )


def mark_menu(frame):
    return frame.locator(".encoding-pane__encoding-pane select").first


def add_field(frame, name):
    """Double-click a field in Voyager's data panel, and wait for it to land
    on a shelf."""
    shelves = frame.locator(".encoding-shelf__field-wrapper")
    frame.locator(".field-list__field-list-item").get_by_text(name, exact=True).dblclick()
    expect(shelves.get_by_text(name, exact=True)).to_be_visible(timeout=VOYAGER_TIMEOUT)


def count_input_events(page, index=0):
    page.evaluate(
        """(i) => {
            const t = document.querySelectorAll('[data-contentpath="spec"] textarea')[i];
            window.__inputEvents = 0;
            t.addEventListener("input", (e) => { if (e.bubbles) window.__inputEvents++; });
        }""",
        index,
    )


def close(dialog):
    dialog.get_by_role("button", name="Close", exact=True).click()
    expect(dialog).to_have_count(0)


# -- Opening ---------------------------------------------------------------------------


def test_opens_in_voyager_with_the_charts_data(editor, console_errors):
    dialog, frame = open_editor(editor, WEATHER)  # /static/testapp/weather.csv
    expect(dialog.get_by_role("radio", name="Voyager")).to_be_checked()
    expect(dialog.get_by_role("group", name="Visual editor")).to_be_visible()
    # It says it needs a mouse, and offers Simple
    expect(dialog.locator(".wagtail-vega-builder__voyager-mouse")).to_contain_text(
        "Voyager is used with a mouse or touchpad"
    )
    expect(dialog.get_by_role("button", name="Switch to Simple")).to_be_visible()
    iframe = dialog.locator("iframe")
    expect(iframe).to_have_attribute("sandbox", "allow-scripts")
    expect(iframe).to_have_attribute("title", "Voyager chart editor")

    # The URL dataset's columns, as Voyager fields
    wait_for_voyager(frame, "date", "weather", "precipitation")
    # Its chart opened: x is the month, colour the weather
    shelves = frame.locator(".encoding-shelf__field-wrapper")
    expect(shelves.get_by_text("weather", exact=True)).to_be_visible()
    expect(mark_menu(frame)).to_have_value("bar")
    # Once it's open, what Voyager changed is listed too: it reads the
    # month on x as a date, not an ordered category
    notice = dialog.locator("[data-voyager-notice]")
    expect(notice).to_contain_text("encoding.x.type")
    # Voyager's own data loader and footer are hidden: data comes from the chart
    expect(frame.locator(".data-selector__data-selector")).to_be_hidden()
    expect(frame.get_by_role("button", name="Change")).to_have_count(0)
    # Voyager gets the dialog's width: the preview is hidden meanwhile
    expect(dialog.locator("[data-preview]")).to_be_hidden()

    # Voyager (React 15, vega 4) stays inside the iframe
    assert editor.evaluate("typeof window.voyager") == "undefined"
    assert editor.locator('script[src*="vendor/voyager"]').count() == 0
    close(dialog)
    assert [e for e in console_errors if "CSP violation" in e] == []
    assert console_errors == []


def test_a_chart_voyager_can_show_has_no_warning(editor):
    set_externally(
        spec_field(editor),
        json.dumps(
            {
                "$schema": VL,
                "title": "Requests",
                "data": {"name": "source"},
                "mark": "bar",
                "encoding": {
                    "x": {"field": "quarter", "type": "nominal"},
                    "y": {"field": "requests", "type": "quantitative", "aggregate": "sum"},
                },
            }
        ),
    )
    dialog, frame = open_editor(editor)
    wait_for_voyager(frame, "quarter")
    wait_for_baseline(editor)
    expect(dialog.locator("[data-voyager-notice]")).to_be_hidden()


def test_voyager_loads_only_when_shown(admin_page, live_server, chart_page, vega_settings):
    vega_settings["VISUAL_EDITOR"] = "simple"
    requests = []
    admin_page.on("request", lambda r: requests.append(r.url))
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
    dialog, frame = open_editor(admin_page)
    expect(dialog.get_by_role("radio", name="Simple")).to_be_checked()
    expect(dialog.get_by_label("Chart type")).to_be_visible()
    expect(dialog.locator("iframe")).to_have_count(0)
    assert not [u for u in requests if "voyager" in u and "voyager-" not in u.rsplit("/", 1)[-1]]
    dialog.get_by_text("Voyager", exact=True).click()
    wait_for_voyager(frame, "quarter")
    assert any(u.endswith("/vendor/voyager/voyager.js") for u in requests)


def test_custom_source(admin_page, live_server, transactional_db, vega_settings, console_errors):
    """A dataset from the test project's custom "donations" source (a rows URL)."""
    record_reports(admin_page)
    page = create_demo_page(body=[custom_source_chart()])
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(page.pk,)))
    dialog, frame = open_editor(admin_page)
    wait_for_voyager(frame, "quarter", "total")
    shelves = frame.locator(".encoding-shelf__field-wrapper")
    expect(shelves.get_by_text("total", exact=True)).to_be_visible()
    # Voyager draws the two quarters' bars
    expect(frame.locator(".chart canvas").first).to_be_visible(timeout=VOYAGER_TIMEOUT)
    close(dialog)
    assert console_errors == []


def test_registered_source(admin_page, live_server, transactional_db, vega_settings):
    """A dataset from a source registered in the browser (registerSource)."""
    page = create_demo_page(body=[custom_source_chart()])
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(page.pk,)))
    dataset = admin_page.locator(".wagtail-vega-dataset").first
    dataset.locator('[data-contentpath="source_type"]').get_by_text("Sample", exact=True).click()
    dataset.locator('[data-contentpath="points"] input').fill("4")
    dialog, frame = open_editor(admin_page)
    wait_for_voyager(frame, "x", "y")


def test_several_datasets_offer_a_picker(editor):
    data_list = editor.locator('[data-contentpath="data"]').first
    data_list.locator("button[data-streamfield-list-add]").last.click()
    new = data_list.locator(".wagtail-vega-dataset").last
    new.locator('[data-contentpath="name"] input').fill("budget")
    fill_editor(new.locator('[data-contentpath="paste"]'), "year,amount\n2025,100\n2026,120")

    dialog, frame = open_editor(editor)
    picker = dialog.get_by_label("Dataset")
    expect(picker).to_have_value("source")  # the one the spec uses
    wait_for_voyager(frame, "quarter")
    picker.select_option("budget")
    wait_for_voyager(frame, "year", "amount")
    add_field(frame, "amount")
    expect(spec_textarea(editor)).to_have_value(
        re.compile('"name": "budget"'), timeout=VOYAGER_TIMEOUT
    )
    assert "amount" in json.dumps(field_spec(editor)["encoding"])


# -- Writing ---------------------------------------------------------------------------


def test_open_and_close_change_nothing(editor):
    for index in (REQUESTS, WEATHER):
        original = spec_textarea(editor, index).input_value()
        count_input_events(editor, index)
        editor.evaluate("window.__voyager = []")
        dialog, frame = open_editor(editor, index)
        wait_for_voyager(frame)
        wait_for_baseline(editor)
        # Looking around: hovering, scrolling
        frame.locator(".field-list__field-list-item").first.hover()
        editor.mouse.wheel(0, 200)
        close(dialog)
        assert spec_textarea(editor, index).input_value() == original
        assert editor.evaluate("window.__inputEvents") == 0
    # Escape too, with focus in the dialog
    original = spec_textarea(editor).input_value()
    dialog, frame = open_editor(editor)
    wait_for_voyager(frame)
    wait_for_baseline(editor)
    editor.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    assert spec_textarea(editor).input_value() == original


def test_an_edit_in_voyager_reaches_the_field(editor, console_errors):
    textarea = spec_textarea(editor, WEATHER)
    count_input_events(editor, WEATHER)
    dialog, frame = open_editor(editor, WEATHER)
    wait_for_voyager(frame, "date")
    wait_for_baseline(editor)
    mark_menu(frame).select_option("point")
    wait_for_report(editor, 'spec?.mark === "point"')
    # Written with the dialog still open, as Vega-Lite 6 with data by name
    expect(textarea).to_have_value(re.compile('"mark": "point"'), timeout=VOYAGER_TIMEOUT)
    spec = field_spec(editor, WEATHER)
    assert spec["$schema"] == VL
    assert spec["data"] == {"name": "weather"}
    assert "values" not in json.dumps(spec)
    # Kept from the field's spec
    assert spec["title"] == "Weather (CSV from a URL)"
    assert spec["width"] == "container"
    # Count, as Vega-Lite 6 writes it
    assert {"aggregate": "count", "type": "quantitative"} in spec["encoding"].values()
    assert editor.evaluate("window.__inputEvents") >= 1
    # The code editor has it (the textarea + "input" contract)
    dialog.get_by_role("tab", name="Code").click()
    expect(dialog.locator("[data-code] .cm-content")).to_contain_text('"mark": "point"')
    close(dialog)
    assert console_errors == []


@pytest.fixture
def autosave_editor(admin_page, live_server, chart_page, settings):
    """The edit page with Wagtail's autosave on, once it's watching for edits."""
    settings.WAGTAIL_AUTOSAVE_INTERVAL = 500
    record_reports(admin_page)
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


def test_an_edit_in_voyager_is_autosaved(autosave_editor, chart_page):
    page = autosave_editor
    dialog, frame = open_editor(page, WEATHER)
    wait_for_voyager(frame, "date")
    wait_for_baseline(page)
    with page.expect_response(lambda r: is_autosave(r, chart_page), timeout=15_000) as info:
        mark_menu(frame).select_option("tick")
    assert info.value.status == 200
    assert info.value.json()["success"] is True
    for _ in range(60):
        with DATABASE_LOCK:
            revision = ChartPage.objects.get(pk=chart_page.pk).get_latest_revision_as_object()
        if revision.body[WEATHER].value["spec"].get("mark") == "tick":
            break
        page.wait_for_timeout(250)
    assert revision.body[WEATHER].value["spec"]["mark"] == "tick"
    assert revision.body[WEATHER].value["spec"]["data"] == {"name": "weather"}
    expect(dialog).to_be_visible()


def test_escape_and_close_write_the_last_edit(editor):
    """Voyager's last change may not be reported yet when the editor closes:
    it's asked for, and written, first."""
    textarea = spec_textarea(editor, WEATHER)

    # Escape, with focus inside Voyager's iframe, straight after the change
    dialog, frame = open_editor(editor, WEATHER)
    wait_for_voyager(frame, "date")
    wait_for_baseline(editor)
    mark_menu(frame).select_option("point")
    mark_menu(frame).press("Escape")
    expect(dialog).to_have_count(0)
    expect(textarea).to_have_value(re.compile('"mark": "point"'))
    expect(editor.locator(LAUNCHER).nth(WEATHER).locator("[data-builder-open]")).to_be_focused()

    # The Close button, straight after the change
    editor.evaluate("window.__voyager = []")
    dialog, frame = open_editor(editor, WEATHER)
    wait_for_voyager(frame, "date")
    wait_for_baseline(editor)
    expect(mark_menu(frame)).to_have_value("point")
    mark_menu(frame).select_option("line")
    dialog.get_by_role("button", name="Close", exact=True).click()
    expect(dialog).to_have_count(0)
    expect(textarea).to_have_value(re.compile('"mark": "line"'))


def test_undo_changes_since_opening(editor):
    textarea = spec_textarea(editor, WEATHER)
    original = textarea.input_value()
    dialog, frame = open_editor(editor, WEATHER)
    wait_for_voyager(frame, "date")
    wait_for_baseline(editor)
    undo = dialog.get_by_role("button", name="Undo changes since opening")
    expect(undo).to_be_disabled()
    mark_menu(frame).select_option("area")
    expect(textarea).to_have_value(re.compile('"mark": "area"'), timeout=VOYAGER_TIMEOUT)
    expect(undo).to_be_enabled()
    undo.click()
    expect(textarea).to_have_value(original)
    # Voyager opens the original again
    expect(mark_menu(frame)).to_have_value("bar", timeout=VOYAGER_TIMEOUT)
    expect(undo).to_be_disabled()
    close(dialog)
    assert textarea.input_value() == original


def test_an_empty_chart_gets_the_chart_made_in_voyager(editor):
    textarea = spec_textarea(editor)
    set_externally(spec_field(editor), "")
    expect(textarea).to_have_value("")
    dialog, frame = open_editor(editor)
    wait_for_voyager(frame, "quarter", "requests")
    wait_for_baseline(editor)
    # Nothing is written until the editor makes a chart (in Simple, a
    # suggestion would be)
    assert textarea.input_value() == ""
    add_field(frame, "quarter")
    add_field(frame, "requests")
    wait_for_report(
        editor,
        """["quarter", "requests"].every((f) =>
            Object.values(spec?.encoding || {}).some((d) => d.field === f))""",
    )
    expect(textarea).to_have_value(re.compile('"requests"'), timeout=VOYAGER_TIMEOUT)
    spec = field_spec(editor)
    assert spec["data"] == {"name": "source"}
    assert {"quarter", "requests"} <= {d.get("field") for d in spec["encoding"].values()}


# -- Charts Voyager can't show as they are ----------------------------------------------------


def test_grouped_bars_warn_and_open_unchanged(editor):
    """Voyager (Vega-Lite 2) has no grouped bars: it shows them stacked. The
    editor is told, and the field only changes if they change something."""
    textarea = spec_textarea(editor)
    original = textarea.input_value()
    assert "xOffset" in original
    count_input_events(editor)
    dialog, frame = open_editor(editor)
    notice = dialog.locator("[data-voyager-notice]")
    expect(notice).to_be_visible()
    expect(notice).to_contain_text("Voyager can't show all of this chart")
    items = notice.locator("li")
    expect(items.first).to_have_text(GROUPED_WARNING)
    expect(notice).to_contain_text("mark.tooltip")
    expect(notice).to_contain_text("encoding.x.title")
    expect(notice).to_contain_text("edit the chart in Simple or Code instead")
    wait_for_voyager(frame, "quarter")
    wait_for_baseline(editor)
    close(dialog)
    assert textarea.input_value() == original
    assert editor.evaluate("window.__inputEvents") == 0

    # Going ahead and changing it in Voyager writes Voyager's version
    dialog, frame = open_editor(editor)
    wait_for_voyager(frame, "quarter")
    wait_for_baseline(editor)
    mark_menu(frame).select_option("point")
    expect(textarea).to_have_value(re.compile('"mark": "point"'), timeout=VOYAGER_TIMEOUT)
    spec = field_spec(editor)
    assert "xOffset" not in spec["encoding"]
    assert spec["title"] == BAR["title"]
    close(dialog)


def test_problems_with_the_spec_are_shown_but_its_written(editor):
    """Voyager's chart is checked by the server (the code editor's live
    validation), and written regardless, like every other change."""
    spec = json.loads(spec_textarea(editor, WEATHER).input_value())
    set_externally(spec_field(editor, WEATHER), json.dumps({**spec, "padding": "lots"}, indent=2))
    dialog, frame = open_editor(editor, WEATHER)
    wait_for_voyager(frame, "date")
    wait_for_baseline(editor)
    problems = dialog.locator("[data-voyager-problems]")
    expect(problems).to_be_hidden()  # not Voyager's: it hasn't written anything
    mark_menu(frame).select_option("point")
    expect(spec_textarea(editor, WEATHER)).to_have_value(
        re.compile('"mark": "point"'), timeout=VOYAGER_TIMEOUT
    )
    # The padding is kept from the field's spec, and isn't valid
    expect(problems).to_be_visible(timeout=10_000)
    expect(problems).to_contain_text(
        "The chart from Voyager is in the page, but its spec has problems."
    )
    expect(problems.locator("li")).to_contain_text(re.compile(r"Line \d+: .*lots"))
    expect(dialog.get_by_role("tab", name=re.compile("Code"))).to_contain_text("has problems")


def test_a_vega_spec_isnt_opened(editor):
    textarea = spec_textarea(editor, VEGA)
    original = textarea.input_value()
    dialog, _ = open_editor(editor, VEGA)
    notice = dialog.locator("[data-voyager-notice]")
    expect(notice).to_contain_text(
        "Voyager can't open this chart: it's a Vega spec, and Voyager makes Vega-Lite charts."
    )
    expect(dialog.locator("[data-voyager-host]")).to_be_hidden()
    expect(dialog.get_by_role("button", name="Start a new chart in Voyager")).to_be_visible()
    expect(dialog.get_by_role("button", name="Switch to Simple")).to_be_visible()
    close(dialog)
    assert textarea.input_value() == original


def test_charts_with_data_from_code(editor):
    dialog, _ = open_editor(editor, DONATIONS)
    expect(dialog.locator("[data-voyager-notice]")).to_contain_text(
        "This chart's data comes from code, so Voyager isn't available."
    )
    expect(dialog.locator("iframe")).to_have_count(0)


# -- Modes and sync -----------------------------------------------------------------------


def test_voyager_simple_and_code_stay_in_sync(editor):
    textarea = spec_textarea(editor, WEATHER)
    dialog, frame = open_editor(editor, WEATHER)
    wait_for_voyager(frame, "date")
    wait_for_baseline(editor)

    # Voyager -> Simple
    mark_menu(frame).select_option("point")
    dialog.get_by_text("Simple", exact=True).click()
    expect(textarea).to_have_value(re.compile('"mark": "point"'))
    expect(dialog.get_by_label("Chart type")).to_have_value("point")
    expect(dialog.locator("[data-preview]")).to_be_visible()

    # Simple -> Voyager: opened again, with a new baseline
    dialog.get_by_label("Chart type").select_option("line")
    expect(textarea).to_have_value(re.compile('"mark": "line"'))
    before = textarea.input_value()
    dialog.get_by_text("Voyager", exact=True).click()
    expect(mark_menu(frame)).to_have_value("line", timeout=VOYAGER_TIMEOUT)
    editor.wait_for_timeout(500)  # Voyager's reports of the reload: not changes
    assert textarea.input_value() == before

    # Code -> Voyager
    dialog.get_by_role("tab", name="Code").click()
    fill_editor(dialog.locator("[data-code]"), before.replace('"mark": "line"', '"mark": "area"'))
    dialog.get_by_role("tab", name="Visual").click()
    expect(mark_menu(frame)).to_have_value("area", timeout=VOYAGER_TIMEOUT)

    # Voyager -> Code
    mark_menu(frame).select_option("tick")
    dialog.get_by_role("tab", name="Code").click()
    expect(dialog.locator("[data-code] .cm-content")).to_contain_text('"mark": "tick"')
    expect(textarea).to_have_value(re.compile('"mark": "tick"'))


def test_switch_to_simple_is_remembered(editor):
    dialog, frame = open_editor(editor)
    switch = dialog.get_by_role("button", name="Switch to Simple")
    switch.click()
    simple = dialog.get_by_role("radio", name="Simple")
    expect(simple).to_be_checked()
    expect(simple).to_be_focused()
    expect(dialog.get_by_label("Chart type")).to_be_visible()
    close(dialog)
    # The next time, the editor opens in Simple
    dialog, _ = open_editor(editor)
    expect(dialog.get_by_role("radio", name="Simple")).to_be_checked()
    # The arrow keys switch modes (they're radio buttons)
    simple.focus()
    editor.keyboard.press("ArrowLeft")
    expect(dialog.get_by_role("radio", name="Voyager")).to_be_checked()
    expect(dialog.locator("iframe")).to_be_visible()


def test_narrow_screens_open_in_simple(admin_page, live_server, chart_page):
    admin_page.set_viewport_size({"width": 390, "height": 844})
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
    dialog, frame = open_editor(admin_page)
    expect(dialog.get_by_role("radio", name="Simple")).to_be_checked()
    expect(
        dialog.get_by_text("Voyager needs a wider screen, so the Simple settings are shown.")
    ).to_be_visible()
    expect(dialog.get_by_label("Chart type")).to_be_visible()
    expect(dialog.locator("iframe")).to_have_count(0)
    # It can still be chosen
    dialog.get_by_text("Voyager", exact=True).click()
    wait_for_voyager(frame, "quarter")
