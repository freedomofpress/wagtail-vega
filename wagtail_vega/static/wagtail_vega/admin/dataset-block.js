/* wagtail-vega admin: DatasetBlock form behaviour.
 *
 * - The Paste / Document / URL toggle shows only the matching inputs.
 * - Pasted data gets a live summary (format, rows, columns and their
 *   inferred types) so editors can check it was read as intended. The
 *   reading is done by data-format.js, which the paste field's code editor
 *   also uses to mark problems in place.
 *
 * The paste field's <textarea> is hidden behind the code editor but stays
 * the source of truth: the editor fires "input" on it for every change.
 */
(() => {
  "use strict";

  const SOURCE_FIELDS = { paste: ["paste"], document: ["document"], url: ["url", "format"] };
  const { summarise } = window.wagtailVegaAdmin.dataFormat;

  function fieldWrapper(root, name) {
    return root.querySelector(`[data-contentpath="${name}"]`);
  }

  /** Name the radio buttons' container after the field's label ("Source"),
   * which Wagtail renders as a <label> that isn't linked to any input, so
   * screen readers announce the group as well as each option. */
  function labelRadioGroup(wrapper) {
    const label = wrapper?.querySelector(".w-field__label");
    const group = wrapper
      ?.querySelector("input[type=radio]")
      ?.closest("[data-field-input] > *");
    if (!label || !group) return;
    if (!label.id) label.id = `${group.id || wrapper.dataset.contentpath}-label`;
    group.setAttribute("role", "radiogroup");
    group.setAttribute("aria-labelledby", label.id);
  }

  /** Add an id to an element's aria-describedby. */
  function describe(element, id) {
    if (!element) return;
    const ids = (element.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
    if (!ids.includes(id)) element.setAttribute("aria-describedby", [...ids, id].join(" "));
  }

  /** A summary line: the symbol is decoration, so screen readers skip it. */
  function summaryLine(symbol, text) {
    const line = document.createElement("p");
    const icon = document.createElement("span");
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = `${symbol} `;
    line.append(icon, text);
    return line;
  }

  class DatasetBlockDefinition extends window.wagtailStreamField.blocks.StructBlockDefinition {
    render(placeholder, prefix, initialState, initialError) {
      const block = super.render(placeholder, prefix, initialState, initialError);
      const root = block.container?.[0] ?? block.container;
      if (!root) return block;

      // Toggle which inputs are visible
      const toggle = fieldWrapper(root, "source_type");
      toggle?.classList.add("wagtail-vega-source-toggle");
      labelRadioGroup(toggle);
      const sync = () => {
        // Read the radio directly: Wagtail's RadioSelect widget shares its
        // getState() with CheckboxSelectMultiple and may return an array.
        const current = toggle?.querySelector("input[type=radio]:checked")?.value || "paste";
        for (const [source, names] of Object.entries(SOURCE_FIELDS)) {
          for (const name of names) {
            const wrapper = fieldWrapper(root, name);
            if (wrapper) wrapper.hidden = source !== current;
          }
        }
      };
      toggle?.addEventListener("change", sync);
      sync();

      // Live summary of pasted data
      const paste = fieldWrapper(root, "paste");
      const textarea = paste?.querySelector("textarea");
      if (textarea) {
        const summary = document.createElement("div");
        summary.className = "wagtail-vega-summary";
        summary.setAttribute("aria-live", "polite");
        if (textarea.id) {
          summary.id = `${textarea.id}-summary`;
          describe(textarea.wagtailVegaEditor?.view?.contentDOM, summary.id);
        }
        paste.append(summary);
        let timer;
        const update = () => {
          const result = summarise(textarea.value);
          summary.replaceChildren();
          summary.hidden = !result;
          if (!result) return;
          summary.classList.toggle("is-error", !result.ok);
          summary.append(summaryLine(result.ok ? "✓" : "⚠", result.message));
          if (result.warning) {
            const warn = summaryLine("⚠", result.warning);
            warn.className = "wagtail-vega-summary__warning";
            summary.append(warn);
          }
        };
        textarea.addEventListener("input", () => {
          clearTimeout(timer);
          timer = setTimeout(update, 150);
        });
        update();
      }
      return block;
    }
  }

  window.telepath.register("wagtail_vega.blocks.DatasetBlock", DatasetBlockDefinition);
})();
