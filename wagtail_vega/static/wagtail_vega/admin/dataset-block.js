/* wagtail-vega admin: DatasetBlock form behaviour.
 *
 * - The source toggle (Paste / Document / URL, and any source a subclass
 *   adds) shows only the selected source's inputs. Which fields belong to
 *   which source comes from the block's source_fields, in the adapter's
 *   meta (meta.wagtailVega.sourceFields), so new sources need no script.
 * - Pasted data gets a live summary (format, rows, columns and their
 *   inferred types) so editors can check it was read as intended. The
 *   reading is done by data-format.js, which the paste field's code editor
 *   also uses to mark problems in place.
 * - A source with a rows URL (meta.wagtailVega.rowsUrls, from the block's
 *   source_rows_urls) gets the same summary of the rows the URL returns for
 *   its fields, fetched again when they change.
 * - The settings are put on the dataset's element, as JSON in
 *   data-wagtail-vega-sources, for the chart editor (see sources.js).
 *
 * The paste field's <textarea> is hidden behind the code editor but stays
 * the source of truth: the editor fires "input" on it for every change.
 *
 * The definition is window.wagtailVegaAdmin.DatasetBlockDefinition, so a
 * subclass's script can extend it and register it under its adapter's
 * js_constructor.
 */
(() => {
  "use strict";

  const admin = window.wagtailVegaAdmin;
  const { summarise, summariseRows, renderSummary } = admin.dataFormat;
  const sources = admin.sources;
  const ROWS_DELAY = 300; // ms after a field changes

  const fieldWrapper = (root, name) => sources.fieldWrapper(root, name);

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

  function summaryElement(id) {
    const summary = document.createElement("div");
    summary.className = "wagtail-vega-summary";
    summary.setAttribute("aria-live", "polite");
    summary.hidden = true;
    if (id) summary.id = id;
    return summary;
  }

  /** The live summary of pasted data, under the paste field. */
  function pasteSummary(root) {
    const paste = fieldWrapper(root, "paste");
    const textarea = paste?.querySelector("textarea");
    if (!textarea) return;
    const summary = summaryElement(textarea.id ? `${textarea.id}-summary` : "");
    if (summary.id) describe(textarea.wagtailVegaEditor?.view?.contentDOM, summary.id);
    paste.append(summary);
    let timer;
    const update = () => renderSummary(summary, summarise(textarea.value));
    textarea.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(update, 150);
    });
    update();
  }

  /** The summary of a source's rows from its rows URL, after its last field.
   * Returns {setActive(on)}: rows are only fetched while the source is
   * selected, and again (debounced) when its fields change; a newer request
   * cancels the one before. */
  function rowsSummary(root, source, names, rowsUrl) {
    const wrappers = names.map((name) => fieldWrapper(root, name)).filter(Boolean);
    const anchor = wrappers.at(-1) || fieldWrapper(root, "source_type");
    const prefix = root.id || anchor?.querySelector("[id]")?.id || `wagtail-vega-${source}`;
    const summary = summaryElement(`${prefix}-${source}-summary`);
    summary.dataset.wagtailVegaRowsSummary = source;
    if (anchor) anchor.after(summary);
    else root.append(summary);
    for (const wrapper of wrappers) {
      for (const control of wrapper.querySelectorAll("input, select, textarea")) describe(control, summary.id);
    }

    let active = false;
    let timer;
    let controller = null;
    const cancel = () => {
      clearTimeout(timer);
      controller?.abort();
      controller = null;
    };
    const refresh = async () => {
      cancel();
      if (!active) return;
      const current = (controller = new AbortController());
      summary.setAttribute("aria-busy", "true");
      let result;
      try {
        const url = sources.rowsRequestUrl(rowsUrl, sources.readFields(root, names));
        result = summariseRows(await sources.fetchRows(url, { signal: current.signal }));
      } catch (e) {
        result = { ok: false, message: e.message };
      }
      if (current.signal.aborted || controller !== current) return; // a newer request replaced it
      controller = null;
      summary.removeAttribute("aria-busy");
      renderSummary(summary, result);
    };
    const schedule = () => {
      clearTimeout(timer);
      if (active) timer = setTimeout(refresh, ROWS_DELAY);
    };
    for (const wrapper of wrappers) {
      wrapper.addEventListener("input", schedule);
      wrapper.addEventListener("change", schedule);
    }
    return {
      element: summary,
      refresh,
      setActive(on) {
        if (on === active) return;
        active = on;
        if (on) {
          summary.hidden = !summary.childElementCount;
          refresh();
        } else {
          cancel();
          summary.removeAttribute("aria-busy");
          summary.hidden = true;
        }
      },
    };
  }

  class DatasetBlockDefinition extends window.wagtailStreamField.blocks.StructBlockDefinition {
    /** {sourceFields, rowsUrls}: from the block's source_fields and
     * source_rows_urls (DatasetBlockAdapter), or the built-in sources. */
    get sourceSettings() {
      const settings = this.meta?.wagtailVega || {};
      return {
        sourceFields: settings.sourceFields || { ...sources.BUILT_IN },
        rowsUrls: settings.rowsUrls || {},
      };
    }

    render(placeholder, prefix, initialState, initialError) {
      const block = super.render(placeholder, prefix, initialState, initialError);
      const root = block.container?.[0] ?? block.container;
      if (!root) return block;
      const settings = this.sourceSettings;
      // For the chart editor (and for subclasses that change form_classname)
      root.classList.add("wagtail-vega-dataset");
      root.dataset.wagtailVegaSources = JSON.stringify(settings);

      const summaries = {};
      for (const [source, url] of Object.entries(settings.rowsUrls)) {
        if (url) summaries[source] = rowsSummary(root, source, settings.sourceFields[source] || [], url);
      }

      // Toggle which inputs are visible
      const toggle = fieldWrapper(root, "source_type");
      toggle?.classList.add("wagtail-vega-source-toggle");
      labelRadioGroup(toggle);
      const sourceFieldNames = new Set(Object.values(settings.sourceFields).flat());
      const sync = () => {
        // Read the radio directly: Wagtail's RadioSelect widget shares its
        // getState() with CheckboxSelectMultiple and may return an array.
        const current = sources.selectedSource(root);
        const shown = new Set(settings.sourceFields[current] || []);
        for (const name of sourceFieldNames) {
          const wrapper = fieldWrapper(root, name);
          if (wrapper) wrapper.hidden = !shown.has(name);
        }
        for (const [source, summary] of Object.entries(summaries)) summary.setActive(source === current);
      };
      toggle?.addEventListener("change", sync);
      sync();

      pasteSummary(root);
      return block;
    }
  }

  admin.DatasetBlockDefinition = DatasetBlockDefinition;
  window.telepath.register("wagtail_vega.blocks.DatasetBlock", DatasetBlockDefinition);
})();
