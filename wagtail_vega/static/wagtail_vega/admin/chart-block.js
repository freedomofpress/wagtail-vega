/* wagtail-vega admin: chart blocks (BaseChartBlock and its subclasses).
 *
 * - A collapsed chart is labelled with the spec's title, or else its
 *   caption or description, rather than the first field Wagtail finds
 *   (usually the dataset name, "source").
 * - The spec editor marks, as you type, every dataset the spec loads by name
 *   ("data": {"name": "sales"}) that isn't one of the chart's datasets. The
 *   server makes the same check when the page is saved (ChartBlock.clean),
 *   with the same message.
 *
 * Needs json-source.js; uses the code editor (code-editor.js) when present.
 */
(() => {
  "use strict";

  // -- Pure helpers (see tests/js/chart-block.test.mjs) -----------------------

  // A data entry with only these keys gets its data from outside the spec
  const EXTERNAL_DATA_KEYS = new Set(["name", "format"]);

  function isExternal(entry) {
    return (
      Boolean(entry) &&
      typeof entry === "object" &&
      !Array.isArray(entry) &&
      typeof entry.name === "string" &&
      Object.keys(entry).every((key) => EXTERNAL_DATA_KEYS.has(key))
    );
  }

  function specKind(spec) {
    const schema = typeof spec?.$schema === "string" ? spec.$schema : "";
    let path = schema;
    try {
      path = new URL(schema).pathname;
    } catch {
      // not a URL: match the string itself
    }
    if (path.includes("/vega-lite/")) return "vega-lite";
    if (path.includes("/vega/")) return "vega";
    return null;
  }

  /** [{path, name}] for each dataset the spec expects to be given by name.
   * Must match wagtail_vega.spec.dataset_references (tests/test_spec.py). */
  function datasetReferences(spec) {
    if (!spec || typeof spec !== "object" || Array.isArray(spec)) return [];
    const kind = specKind(spec);
    if (kind === "vega") {
      if (!Array.isArray(spec.data)) return [];
      return spec.data.flatMap((entry, i) =>
        isExternal(entry) ? [{ path: ["data", i, "name"], name: entry.name }] : [],
      );
    }
    if (kind !== "vega-lite") return [];
    const own = spec.datasets && typeof spec.datasets === "object" ? spec.datasets : {};
    const found = [];
    const walk = (node, path) => {
      if (Array.isArray(node)) {
        node.forEach((value, i) => walk(value, [...path, i]));
      } else if (node && typeof node === "object") {
        for (const [key, value] of Object.entries(node)) {
          if (key === "datasets" || key === "values") continue; // inline data
          if (key === "data" && isExternal(value)) {
            if (!Object.hasOwn(own, value.name)) {
              found.push({ path: [...path, key, "name"], name: value.name });
            }
          } else {
            walk(value, [...path, key]);
          }
        }
      }
    };
    walk(spec, []);
    return found;
  }

  function format(template, values) {
    return template.replace(/%\((\w+)\)s/g, (match, key) => (key in values ? values[key] : match));
  }

  /** [{path, message}] for datasets the spec loads that aren't in `names`. */
  function missingDatasets(spec, names, messages) {
    return datasetReferences(spec)
      .filter(({ name }) => !names.includes(name))
      .map(({ path, name }) => ({
        path,
        message: format(names.length ? messages.some : messages.none, {
          name,
          names: names.join(", "),
        }),
      }));
  }

  function titleText(title) {
    if (typeof title === "string") return title;
    if (Array.isArray(title)) return title.filter((t) => typeof t === "string").join(" ");
    if (title && typeof title === "object") return titleText(title.text);
    return "";
  }

  /** The collapsed block's label: the spec's title, the caption, or the
   * description, whichever is found first. */
  function chartLabel({ spec, caption, description }, maxLength) {
    let title = "";
    try {
      title = titleText(JSON.parse(spec || "null")?.title);
    } catch {
      // not valid JSON (yet)
    }
    const label = [title, caption, description]
      .map((text) => (typeof text === "string" ? text.replace(/\s+/g, " ").trim() : ""))
      .find(Boolean);
    if (!label) return null;
    return maxLength && label.length > maxLength ? `${label.slice(0, maxLength - 1)}…` : label;
  }

  // -- Wagtail integration ----------------------------------------------------

  function state(child) {
    try {
      const value = child?.getState?.();
      return typeof value === "string" ? value : "";
    } catch {
      return "";
    }
  }

  /** The names in the chart's Data list, as currently entered. */
  function datasetNames(dataBlock) {
    return (dataBlock?.children || [])
      .map((child) => child?.block?.childBlocks?.name)
      .filter(Boolean)
      .map((name) => state(name).trim());
  }

  const StructBlockDefinition = window.wagtailStreamField?.blocks?.StructBlockDefinition;

  if (StructBlockDefinition && window.telepath) {
    class ChartBlockDefinition extends StructBlockDefinition {
      render(placeholder, prefix, initialState, initialError, ...rest) {
        const block = super.render(placeholder, prefix, initialState, initialError, ...rest);
        const children = block.childBlocks || {};

        block.getTextLabel = (opts) =>
          chartLabel(
            {
              spec: state(children.spec),
              caption: state(children.caption),
              description: state(children.description),
            },
            opts?.maxLength,
          );

        const editor = children.spec?.widget?.codeEditor;
        const messages = this.meta?.wagtailVega?.missingDataset;
        if (editor && children.data && messages) {
          editor.addCheck((spec) => missingDatasets(spec, datasetNames(children.data), messages));
          watchDatasets(block, editor);
        }
        return block;
      }
    }
    window.telepath.register("wagtail_vega.blocks.ChartBlock", ChartBlockDefinition);
  }

  /** Check the spec again when a dataset is renamed, added or removed. */
  function watchDatasets(block, editor) {
    const root = block.container?.[0] ?? block.container;
    const data = root?.querySelector?.('[data-contentpath="data"]');
    if (!data) return;
    let timer;
    const relint = () => {
      clearTimeout(timer);
      timer = setTimeout(() => editor.relint(), 300);
    };
    data.addEventListener("input", (event) => {
      if (event.target.closest?.('[data-contentpath="name"]')) relint();
    });
    // Items added, removed or deleted (but not typing in a code editor)
    new MutationObserver((records) => {
      const outside = (r) => !r.target.closest?.(".wagtail-vega-code, .wagtail-vega-summary");
      if (records.some(outside)) relint();
    }).observe(data, { childList: true, subtree: true });
  }

  window.wagtailVegaAdmin = window.wagtailVegaAdmin || {};
  window.wagtailVegaAdmin.chartBlock = {
    _internal: { datasetReferences, missingDatasets, chartLabel, format },
  };
})();
