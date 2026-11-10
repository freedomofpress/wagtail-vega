/* wagtail-vega admin: dataset sources, for the dataset form (dataset-block.js)
 * and the chart editor (chart-builder.js).
 *
 * A dataset's source is Paste, Document, URL, or one a DatasetBlock subclass
 * adds. dataset-block.js puts the block's settings on each dataset's element,
 * as JSON in data-wagtail-vega-sources:
 *
 *   {"sourceFields": {source: [field name, ...]}, "rowsUrls": {source: url}}
 *
 * The admin gets a custom source's rows from, in order:
 *
 * 1. its rows URL (DatasetBlock.source_rows_urls): a GET request with the
 *    source's field values as query parameters, answered with
 *    {"rows": [...]} or {"error": "..."};
 * 2. a script that registered it:
 *
 *      wagtailVegaAdmin.registerSource("incidents", {
 *        hasData(datasetEl) { return true; },        // optional
 *        loadRows(datasetEl, config) { return fetch(...).then(...); },
 *        key(datasetEl) { return "..."; },          // optional
 *      });
 *
 *    loadRows() returns (a promise of) the rows, or throws an Error whose
 *    message is shown to the editor;
 * 3. otherwise its rows can't be loaded in the admin. They're never read
 *    from another source's inputs.
 *
 * Exposed as window.wagtailVegaAdmin.sources, and registerSource() as
 * window.wagtailVegaAdmin.registerSource.
 */
(() => {
  "use strict";

  const admin = (window.wagtailVegaAdmin = window.wagtailVegaAdmin || {});
  if (admin.sources) return; // loaded already: keep its registry

  // Translations come from Django's JavaScript catalogue (see data-format.js)
  const gettext = (s) => (window.gettext ? window.gettext(s) : s);
  const fill = (s, params) => s.replace(/%\((\w+)\)s/g, (m, k) => (k in params ? String(params[k]) : m));

  const BUILT_IN = Object.freeze({ paste: ["paste"], document: ["document"], url: ["url", "format"] });
  const SKIPPED_TYPES = new Set(["button", "submit", "reset", "image", "file"]);

  const registry = new Map();

  /** Let the admin load a custom source's rows in the browser. `source` is
   * {loadRows(datasetEl, config), hasData(datasetEl)?, key(datasetEl)?}:
   * see the comment at the top of this file. A source with a rows URL uses
   * that instead. */
  function registerSource(name, source) {
    if (typeof name !== "string" || !name) {
      throw new TypeError("wagtailVegaAdmin.registerSource() needs a source name.");
    }
    if (!source || typeof source.loadRows !== "function") {
      throw new TypeError(`wagtailVegaAdmin.registerSource("${name}") needs a loadRows() function.`);
    }
    registry.set(name, source);
  }

  function registeredSource(name) {
    return registry.get(name) || null;
  }

  /** The wrapper of the dataset's field `name`. */
  function fieldWrapper(datasetEl, name) {
    return datasetEl?.querySelector(`[data-contentpath="${name}"]`) || null;
  }

  /** The values of the form controls in a field's wrapper, as strings: the
   * checked checkboxes and radio buttons, the selected options of a select,
   * and the value of any other named input or textarea. */
  function fieldValues(wrapper) {
    if (!wrapper) return [];
    const values = [];
    for (const control of wrapper.querySelectorAll("input, select, textarea")) {
      if (!control.name || control.disabled) continue;
      const type = String(control.type || "").toLowerCase();
      if (SKIPPED_TYPES.has(type)) continue;
      if (type === "checkbox" || type === "radio") {
        if (control.checked) values.push(control.value);
      } else if (String(control.tagName).toUpperCase() === "SELECT") {
        for (const option of control.options) if (option.selected) values.push(option.value);
      } else {
        values.push(control.value);
      }
    }
    return values;
  }

  /** {name: [value, ...]} for the dataset's fields `names`. */
  function readFields(datasetEl, names) {
    return Object.fromEntries(names.map((name) => [name, fieldValues(fieldWrapper(datasetEl, name))]));
  }

  /** Whether any of the fields has a value that isn't blank. */
  function hasValues(fields) {
    return Object.values(fields).some((values) => values.some((v) => String(v).trim()));
  }

  /** The dataset's settings ({sourceFields, rowsUrls}), from the element
   * dataset-block.js rendered. Only the built-in sources if there are none. */
  function sourceSettings(datasetEl) {
    let settings = null;
    try {
      settings = JSON.parse(datasetEl?.dataset?.wagtailVegaSources || "null");
    } catch {
      // fall through to the built-in sources
    }
    return {
      sourceFields: settings?.sourceFields || { ...BUILT_IN },
      rowsUrls: settings?.rowsUrls || {},
    };
  }

  /** The dataset's selected source: its source_type radio button (or select). */
  function selectedSource(datasetEl) {
    const wrapper = fieldWrapper(datasetEl, "source_type");
    const radio = wrapper?.querySelector("input[type=radio]:checked");
    if (radio) return radio.value;
    return wrapper?.querySelector("select")?.value || "paste";
  }

  /** The label of the dataset's source, as the toggle shows it. */
  function sourceLabel(datasetEl, source) {
    const radio = [...(fieldWrapper(datasetEl, "source_type")?.querySelectorAll("input[type=radio]") || [])].find(
      (input) => input.value === source,
    );
    return radio?.closest("label")?.textContent.trim() || source;
  }

  /** How the admin gets `source`'s rows: {kind: "builtIn"}, {kind:
   * "rowsUrl", url}, {kind: "registry", entry}, or {kind: null} when it
   * can't. */
  function loaderFor(source, settings) {
    if (Object.hasOwn(BUILT_IN, source)) return { kind: "builtIn" };
    const url = settings?.rowsUrls?.[source];
    if (url) return { kind: "rowsUrl", url };
    const entry = registeredSource(source);
    if (entry) return { kind: "registry", entry };
    return { kind: null };
  }

  /** The rows URL with the fields as query parameters (repeated for
   * several values). It must be on this site. */
  function rowsRequestUrl(rowsUrl, fields, base = window.document.baseURI) {
    const url = new URL(rowsUrl, base);
    if (url.origin !== new URL(base).origin) {
      throw new Error(fill(gettext("Data for the admin can't be loaded from %(url)s."), { url: url.href }));
    }
    for (const [name, values] of Object.entries(fields)) {
      for (const value of values) url.searchParams.append(name, value);
    }
    return url;
  }

  /** GET a rows URL: resolves to the rows, or rejects with the server's
   * error message. */
  async function fetchRows(url, { signal } = {}) {
    const response = await window.fetch(url, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      signal,
    });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body || !Array.isArray(body.rows)) {
      throw new Error(
        (body && typeof body.error === "string" && body.error) ||
          fill(gettext("Couldn't load the data (%(status)s)."), { status: response.status }),
      );
    }
    return body.rows;
  }

  admin.sources = {
    BUILT_IN,
    registerSource,
    registeredSource,
    fieldWrapper,
    fieldValues,
    readFields,
    hasValues,
    sourceSettings,
    selectedSource,
    sourceLabel,
    loaderFor,
    rowsRequestUrl,
    fetchRows,
  };
  admin.registerSource = registerSource;
})();
