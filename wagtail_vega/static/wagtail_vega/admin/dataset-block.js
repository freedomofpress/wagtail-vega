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

  class DatasetBlockDefinition extends window.wagtailStreamField.blocks.StructBlockDefinition {
    render(placeholder, prefix, initialState, initialError) {
      const block = super.render(placeholder, prefix, initialState, initialError);
      const root = block.container?.[0] ?? block.container;
      if (!root) return block;

      // Toggle which inputs are visible
      const toggle = fieldWrapper(root, "source_type");
      toggle?.classList.add("wagtail-vega-source-toggle");
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
        paste.append(summary);
        let timer;
        const update = () => {
          const result = summarise(textarea.value);
          summary.replaceChildren();
          summary.hidden = !result;
          if (!result) return;
          summary.classList.toggle("is-error", !result.ok);
          const line = document.createElement("p");
          line.textContent = `${result.ok ? "✓" : "⚠"} ${result.message}`;
          summary.append(line);
          if (result.warning) {
            const warn = document.createElement("p");
            warn.className = "wagtail-vega-summary__warning";
            warn.textContent = `⚠ ${result.warning}`;
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
