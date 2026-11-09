"""Helpers for driving the admin's code editors in browser tests."""


def fill_editor(wrapper, text):
    """Replace the text in the code editor inside ``wrapper`` (a field's
    ``[data-contentpath]`` element) by typing, as an editor would."""
    content = wrapper.locator(".cm-content")
    content.click()
    page = content.page
    page.keyboard.press("ControlOrMeta+a")
    if text:
        page.keyboard.insert_text(text)
    else:
        page.keyboard.press("Backspace")


def select_text(wrapper, text, nth=0):
    """Focus the code editor in ``wrapper`` and select the ``nth`` occurrence
    of ``text``, ready to type over it."""
    found = wrapper.locator("textarea").evaluate(
        """(textarea, [text, nth]) => {
            const { view } = textarea.wagtailVegaEditor;
            const doc = view.state.doc.toString();
            let at = -1;
            for (let i = 0; i <= nth; i++) at = doc.indexOf(text, at + 1);
            if (at === -1) return false;
            view.focus();
            const selection = { anchor: at, head: at + text.length };
            view.dispatch({ selection, scrollIntoView: true });
            return true;
        }""",
        [text, nth],
    )
    assert found, f"{text!r} not found in the editor"


def set_externally(wrapper, text):
    """Set the field the way other admin code would (see code-editor.js):
    change the textarea and fire "input"."""
    wrapper.locator("textarea").evaluate(
        """(textarea, text) => {
            textarea.value = text;
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
        }""",
        text,
    )


def open_code_editor(field):
    """Open the chart editor from the spec field ``field`` (its
    ``[data-contentpath="spec"]`` element) and show its Code tab. Returns
    the element that holds the field's code editor while it's open."""
    page = field.page
    field.locator("[data-builder-open]").click()
    dialog = page.locator("dialog.wagtail-vega-builder")
    dialog.get_by_role("tab", name="Code").click()
    code = dialog.locator("[data-code]")
    code.locator(".cm-editor").wait_for(state="visible")
    return code


def close_editor(page):
    """Close the chart editor with its Close button."""
    dialog = page.locator("dialog.wagtail-vega-builder")
    dialog.get_by_role("button", name="Close", exact=True).click()
    dialog.wait_for(state="detached")
