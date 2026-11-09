/* wagtail-vega admin: the chart spec field and the chart editor.
 *
 * THE FIELD. A spec field with the builder (CodeEditor(builder=True), see
 * widgets.py) shows a preview of the chart, the spec's problems (from the
 * code editor's checks: JSON syntax, the schema, data hosts, missing
 * datasets, and errors from a failed save), and an "Edit chart" button.
 * While the spec is empty, a prompt replaces the preview and the button is
 * the main action. The <textarea> stays in the form, hidden, as the value
 * that's saved.
 *
 * THE EDITOR. "Edit chart" opens one <dialog> with:
 *
 * - Visual settings (a "Visual" tab): dataset, chart type, encodings…,
 *   read from and written to the spec with chart-spec.js's round-trip
 *   rules: what the settings don't show is kept as it is.
 * - The code (a "Code" tab): the field's own CodeMirror editor
 *   (code-editor.js), moved into the dialog while it's open, so its checks,
 *   undo history and server errors carry on.
 * - A live preview, in the chart's theme.
 *
 * All three work on one spec, the code editor's text:
 *
 * - A change in the settings writes the new spec into the code editor as
 *   one undoable change (formatted, with the cursor where it changed).
 * - An edit in the code is read back into the settings and preview. While
 *   the JSON is invalid, they stay at the last valid spec and say why. A
 *   spec the settings can't show (a Vega spec, layers…) disables them, with
 *   a note; the code and preview keep working.
 * - Opening the editor, or switching tabs, never changes the spec: only an
 *   edit does. An empty spec shows a suggested chart, which is only written
 *   once the editor changes a setting or picks a suggestion.
 *
 * Every change goes to the textarea as it's made (code-editor.js debounces
 * typing, and flushes on blur, close and submit), with a bubbling "input"
 * event, so Wagtail's unsaved-changes and autosave controllers see it.
 * There's no "use" or "cancel" step: Close and Esc just close, and "Undo
 * changes since opening" puts back the spec the editor opened with.
 *
 * Data comes from the form as it is now: pasted text is parsed with
 * data-format.js (as the server will), documents through the document-rows
 * endpoint, and URL datasets are fetched by the browser, from allowed hosts
 * only. The Vega libraries load once, the first time a chart is drawn, and
 * draw with vega-interpreter, so the admin needs no 'unsafe-eval'.
 *
 * All text comes from the server (builder_strings.py), looked up by key.
 * Needs data-format.js, code-editor.js and chart-spec.js.
 */
(() => {
  "use strict";

  const admin = (window.wagtailVegaAdmin = window.wagtailVegaAdmin || {});
  // Element boundaries in Wagtail's StreamField / StructBlock markup
  const BOUNDARY = "[data-streamfield-child], [data-contentpath], [data-contentpath-disabled]";
  const CUSTOM = "__custom__";
  const PREVIEW_DELAY = 200; // ms, in the editor
  const FIELD_DELAY = 400; // ms, for the field's preview

  // The builder's text, translated on the server (builder_strings.py) and
  // passed in the field's settings. Values use %(name)s placeholders.
  let STRINGS = {};

  function t(key, vars = {}) {
    const template = Object.hasOwn(STRINGS, key) ? STRINGS[key] : key;
    return template.replace(/%\((\w+)\)s/g, (match, name) => (name in vars ? String(vars[name]) : match));
  }

  /** A message from chart-spec.js ({key, vars}), translated. */
  const message = ({ key, vars }) => t(key, vars);

  const escapeHTML = (text) => String(text).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const clone = (v) => JSON.parse(JSON.stringify(v));

  /** Recursively merge objects; later arguments win (as spec.deep_merge). */
  function deepMerge(...objects) {
    const out = {};
    for (const object of objects) {
      if (!isObject(object)) continue;
      for (const [k, v] of Object.entries(object)) {
        out[k] = isObject(v) && isObject(out[k]) ? deepMerge(out[k], v) : clone(v);
      }
    }
    return out;
  }

  // -- Data -------------------------------------------------------------------

  /** Mirrors wagtail_vega.spec.host_allowed, applied to the URL the browser
   * will actually fetch. `new URL(raw, base)` parses it as the browser does
   * (stripping control characters and spaces, reading backslashes as
   * slashes, resolving scheme-relative URLs), which is what the server's
   * normalize_url() copies. The result must be http(s), and on this origin
   * or an allowed host. `allowedHosts` is conf.get_allowed_hosts(). */
  function urlAllowed(raw, allowedHosts, base) {
    if (typeof raw !== "string" || !raw.trim()) return false;
    let url;
    try {
      url = new URL(raw, base);
    } catch {
      return false;
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") return false;
    if (url.origin === new URL(base).origin) return true;
    const host = url.hostname.toLowerCase();
    return allowedHosts.some((pattern) => {
      pattern = String(pattern).toLowerCase();
      if (pattern === "*" || pattern === host) return true;
      return pattern.startsWith("*.") && (host === pattern.slice(2) || host.endsWith(pattern.slice(1)));
    });
  }

  function formatFromUrl(url) {
    const match = url.pathname.toLowerCase().match(/\.(csv|tsv|json)$/);
    return match ? match[1] : "json";
  }

  /** The child field `name` of the block that holds `boundary`'s fields. */
  function ownField(boundary, name) {
    return (
      [...boundary.querySelectorAll(`[data-contentpath="${name}"]`)].find(
        (el) => el.parentElement.closest(BOUNDARY) === boundary,
      ) || null
    );
  }

  /** Datasets a ChartBlock subclass adds in code (extra_dataset_names),
   * which chart-block.js puts on the block. They have no rows here. */
  function extraDatasetNames(el) {
    try {
      const names = JSON.parse(el.closest("[data-wagtail-vega-extra-datasets]")?.dataset.wagtailVegaExtraDatasets || "[]");
      return Array.isArray(names) ? names.filter((n) => typeof n === "string") : [];
    } catch {
      return [];
    }
  }

  /** The spec field's chart: its datasets field and theme field, if any. */
  function chartContext(launcher) {
    const boundary = launcher.closest(BOUNDARY)?.parentElement?.closest(BOUNDARY);
    return {
      textarea: launcher.textarea,
      dataField: boundary ? ownField(boundary, "data") : null,
      themeField: boundary ? ownField(boundary, "theme") : null,
      extraNames: extraDatasetNames(launcher),
    };
  }

  function isDeleted(el) {
    const child = el.closest("[data-streamfield-child]");
    return child?.querySelector(':scope > input[name$="-deleted"]')?.value === "1";
  }

  function hasData(dataset) {
    if (dataset.source === "document") return Boolean(dataset.document);
    if (dataset.source === "url") return Boolean(dataset.url);
    return Boolean(dataset.paste.trim());
  }

  /** The chart's datasets that have data, as entered in the form now. */
  function readDatasets(dataField) {
    if (!dataField) return [];
    return [...dataField.querySelectorAll(".wagtail-vega-dataset")]
      .filter((el) => !isDeleted(el))
      .map((el) => {
        const field = (name) => el.querySelector(`[data-contentpath="${name}"]`);
        return {
          name: field("name")?.querySelector("input")?.value.trim() || "",
          source: field("source_type")?.querySelector("input[type=radio]:checked")?.value || "paste",
          paste: field("paste")?.querySelector("textarea")?.value || "",
          document: field("document")?.querySelector('input[type="hidden"]')?.value || "",
          url: field("url")?.querySelector("input")?.value.trim() || "",
          format: field("format")?.querySelector("select")?.value || "",
        };
      })
      .filter((dataset) => dataset.name && hasData(dataset));
  }

  async function loadRows(dataset, config) {
    const parseRows = admin.dataFormat?.parseRows;
    if (!parseRows) throw new Error(t("error.scripts"));
    if (dataset.source === "document") {
      const url = `${config.rowsUrl}?id=${encodeURIComponent(dataset.document)}`;
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || t("error.document", { status: response.status }));
      return body.rows;
    }
    if (dataset.source === "url") {
      if (!urlAllowed(dataset.url, config.allowedHosts, document.baseURI)) {
        throw new Error(t("error.host", { url: dataset.url }));
      }
      const url = new URL(dataset.url, document.baseURI);
      const response = await fetch(url);
      if (!response.ok) throw new Error(t("error.url", { url: url.href, status: response.status }));
      return parseRows(await response.text(), dataset.format || formatFromUrl(url));
    }
    return parseRows(dataset.paste);
  }

  // Rows for each dataset as entered, so redrawing doesn't fetch them again
  const rowsCache = new Map();

  function cachedRows(dataset, config) {
    const key = JSON.stringify(dataset);
    if (!rowsCache.has(key)) {
      const promise = loadRows(dataset, config).then((rows) => {
        if (!Array.isArray(rows)) throw new Error(t("unreadable", { name: dataset.name }));
        return rows;
      });
      promise.catch(() => rowsCache.delete(key)); // try again next time
      rowsCache.set(key, promise);
    }
    return rowsCache.get(key);
  }

  /** {rows: {name: rows}, errors: [message]} for the datasets. */
  async function loadAllRows(datasets, config) {
    const rows = {};
    const errors = [];
    await Promise.all(
      datasets.map(async (dataset) => {
        try {
          rows[dataset.name] = await cachedRows(dataset, config);
        } catch (e) {
          errors.push(e.message);
        }
      }),
    );
    return { rows, errors };
  }

  // -- Drawing charts -----------------------------------------------------------

  let libraries = null;

  /** Load vega, vega-lite, vega-embed, vega-interpreter and wagtail-vega.js
   * (for var() resolution) once, in order. */
  function loadLibraries(config) {
    // TODO-23: vegaInterpreter. main (#25) drops vega-interpreter.js: stop waiting for it
    if (window.vegaEmbed && window.vegaInterpreter && window.wagtailVega?._internal) {
      return Promise.resolve();
    }
    if (!libraries) {
      if (config.stylesheet && !document.querySelector(`link[href="${CSS.escape(config.stylesheet)}"]`)) {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = config.stylesheet;
        document.head.append(link);
      }
      libraries = Promise.all(
        config.scripts.map(
          (src) =>
            new Promise((resolve, reject) => {
              const script = document.createElement("script");
              script.src = src;
              script.async = false; // run in order
              script.addEventListener("load", resolve);
              script.addEventListener("error", () => reject(new Error(t("error.library", { src }))));
              document.head.append(script);
            }),
        ),
      ).catch((error) => {
        libraries = null; // try again next time
        throw error;
      });
    }
    return libraries;
  }

  /** The admin's colour scheme: Wagtail's theme setting, or the system's. */
  function adminScheme() {
    const html = document.documentElement.classList;
    if (html.contains("w-theme-dark")) return "dark";
    if (html.contains("w-theme-light")) return "light";
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  const isVega = (spec) => typeof spec?.$schema === "string" && spec.$schema.includes("/vega/");

  /** At most `limit` rows of each dataset: {rows, sampled: [{name, shown, total}]}. */
  function sampleRows(rowsByName, limit) {
    const rows = {};
    const sampled = [];
    for (const [name, all] of Object.entries(rowsByName)) {
      if (limit && all.length > limit) {
        rows[name] = all.slice(0, limit);
        sampled.push({ name, shown: limit, total: all.length });
      } else {
        rows[name] = all;
      }
    }
    return { rows, sampled };
  }

  /** The spec as the page will draw it: data filled in by name, and the
   * theme applied (as BaseChartBlock.get_spec does: theme, dark, then the
   * spec's own config). */
  function previewSpec(spec, rowsByName, theme, dark) {
    const out = clone(spec);
    if (isVega(out)) {
      for (const entry of Array.isArray(out.data) ? out.data : []) {
        const external = isObject(entry) && Object.keys(entry).every((k) => k === "name" || k === "format");
        if (external && entry.name in rowsByName) entry.values = rowsByName[entry.name];
      }
    } else {
      out.datasets = { ...rowsByName, ...(isObject(spec.datasets) ? spec.datasets : {}) };
    }
    if (theme) {
      const config = deepMerge(theme.config, dark ? theme.dark : null, spec.config);
      if (Object.keys(config).length) out.config = config;
    }
    return out;
  }

  function themeFor(config, themeField) {
    const { themes = {}, defaultTheme } = config;
    const chosen = themeField?.querySelector("select")?.value;
    return themes[chosen] || themes[defaultTheme] || null;
  }

  /** Draw `spec` into `host`, replacing what's there once it's drawn.
   * Returns {messages, error}; `isCurrent()` false means a newer drawing
   * has started, so this one is dropped. */
  async function drawChart(host, spec, { rowsByName, theme, dark, config, isCurrent = () => true }) {
    await loadLibraries(config);
    if (!isCurrent()) return { messages: [] };
    host.dataset.colorScheme = dark ? "dark" : "light";
    const internal = window.wagtailVega?._internal || {};
    const { rows, sampled } = sampleRows(rowsByName, config.previewRows || 5000);
    let full = previewSpec(spec, rows, theme, dark);
    if (internal.resolveVars) full = internal.resolveVars(full, host, theme?.fallbacks || {});
    const messages = sampled.map((s) => t("sampled", { shown: s.shown.toLocaleString(), total: s.total.toLocaleString() }));
    const logged = [];
    const logger = window.vega.logger(window.vega.Warn);
    logger.warn = (...args) => {
      logged.push(args.join(" "));
      return logger;
    };
    logger.error = (...args) => {
      logged.push(args.map(String).join(" "));
      return logger;
    };
    const options = {
      ...(config.embedOptions || {}),
      actions: false,
      renderer: "svg",
      defaultStyle: false,
      tooltip: { disableDefaultStyle: true },
      ast: true,
      // TODO-23: vegaInterpreter. main (#25) drops this: keep ast: true, remove expr
      expr: window.vegaInterpreter.expressionInterpreter,
      logger,
      loader: internal.makeLoader ? internal.makeLoader(config.allowedHosts) : undefined,
    };
    if (theme?.vega_theme) options.theme = theme.vega_theme;
    const target = document.createElement("div");
    target.className = "wagtail-vega__target";
    host.append(target);
    try {
      const result = await window.vegaEmbed(target, full, options);
      await result.view.runAsync();
      if (!isCurrent()) {
        result.view.finalize();
        target.remove();
        return { messages: [] };
      }
      host.wagtailVegaView?.finalize();
      host.wagtailVegaView = result.view;
      for (const child of [...host.children]) if (child !== target) child.remove();
      return { messages: [...messages, ...logged.map((m) => t("previewNote", { message: m }))] };
    } catch (e) {
      target.remove();
      return { messages: logged, error: e.message };
    }
  }

  // -- The editor's dialog ------------------------------------------------------

  let uid = 0;

  function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === false || value === null || value === undefined) continue;
      if (key === "text") el.textContent = value;
      else if (key === "className") el.className = value;
      else el.setAttribute(key, value === true ? "" : value);
    }
    el.append(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
    return el;
  }

  function icon(name) {
    return `<svg class="icon icon-${name}" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
  }

  const optionSets = new WeakMap();

  function setOptions(select, options) {
    // Only rebuild when the options change, so a focused select isn't disturbed
    const signature = JSON.stringify(options);
    if (optionSets.get(select) === signature) return;
    optionSets.set(select, signature);
    select.replaceChildren(
      ...options.map(([value, label, disabled]) => {
        const option = new Option(label, value);
        option.disabled = Boolean(disabled);
        return option;
      }),
    );
  }

  /** A value kept from the spec, briefly, e.g. for a placeholder. */
  function keptText(value) {
    if (value === null) return t("keptNone");
    let text = JSON.stringify(value);
    if (text.length > 40) text = `${text.slice(0, 39)}…`;
    return t("kept", { value: text });
  }

  /** One opening of the editor for one spec field. */
  class Session {
    constructor(launcher, { textarea, dataField, themeField, extraNames }) {
      this.launcher = launcher;
      this.trigger = launcher.button;
      this.textarea = textarea;
      this.editor = textarea.wagtailVegaEditor;
      this.hasDataField = Boolean(dataField);
      this.datasets = readDatasets(dataField);
      // Datasets from code: listed, but there are no rows to build from
      this.extraNames = extraNames.filter((name) => !this.datasets.some((d) => d.name === name));
      this.themeField = themeField;
      this.config = launcher.config;
      this.spec = admin.chartSpec;
      this.id = `wagtail-vega-builder-${++uid}`;
      this.previewToken = 0;
      this.scheme = adminScheme();
      this.rowsByName = {};
      this.columns = [];
      this.state = null;
      this.mode = "loading"; // then visual, pending, unrepresentable or noData
      this.frozen = null; // {line, error} while the code isn't valid JSON
      this.current = null; // the spec being previewed
      this.datasetName = this.datasets[0]?.name || null;
    }

    $(selector) {
      return this.dialog.querySelector(selector);
    }

    get text() {
      return this.editor.view.state.doc.toString();
    }

    // -- Building the dialog ---------------------------------------------------

    buildDialog() {
      const id = this.id;
      const dialog = h("dialog", {
        className: "wagtail-vega-builder",
        "aria-labelledby": `${id}-title`,
        "aria-describedby": `${id}-status`,
      });
      const e = (key) => escapeHTML(t(key));
      dialog.innerHTML = `
        <header class="wagtail-vega-builder__header">
          <h2 class="wagtail-vega-builder__title" id="${id}-title">${e("title")}</h2>
          <button type="button" class="wagtail-vega-builder__close" data-close aria-label="${e("closeLabel")}">${icon("cross")}</button>
        </header>
        <div class="wagtail-vega-builder__body">
          <div class="wagtail-vega-builder__panes">
            <div class="wagtail-vega-builder__tabs" role="tablist" aria-label="${e("tabs")}">
              <button type="button" role="tab" id="${id}-tab-visual" aria-controls="${id}-panel-visual" aria-selected="true" data-tab="visual">${e("tab.visual")}</button>
              <button type="button" role="tab" id="${id}-tab-code" aria-controls="${id}-panel-code" aria-selected="false" tabindex="-1" data-tab="code">${e("tab.code")}<span class="wagtail-vega-builder__badge" data-code-badge hidden> <span aria-hidden="true">⚠</span><span class="visually-hidden">${e("tab.codeProblems")}</span></span></button>
            </div>
            <div class="wagtail-vega-builder__panel" role="tabpanel" id="${id}-panel-visual" aria-labelledby="${id}-tab-visual" data-panel="visual">
              <div class="wagtail-vega-builder__notice" data-controls-notice hidden>
                <p id="${id}-notice" data-controls-note></p>
                <button type="button" class="button button-small" data-start-fresh aria-describedby="${id}-notice" hidden>${e("startFresh")}</button>
              </div>
              <fieldset class="wagtail-vega-builder__settings" data-controls-fieldset>
                <legend class="visually-hidden">${e("controls")}</legend>
                <div class="wagtail-vega-builder__dataset" data-dataset-picker hidden>
                  <label for="${id}-dataset">${e("dataset")}</label>
                  <select id="${id}-dataset" data-dataset></select>
                </div>
                <div class="wagtail-vega-builder__controls" data-controls></div>
              </fieldset>
            </div>
            <div class="wagtail-vega-builder__panel wagtail-vega-builder__panel--code" role="tabpanel" id="${id}-panel-code" aria-labelledby="${id}-tab-code" data-panel="code" hidden>
              <p class="wagtail-vega-builder__hint" id="${id}-code-help">${e("codeHelp")}</p>
              <div data-code></div>
            </div>
          </div>
          <section class="wagtail-vega-builder__preview" data-preview aria-labelledby="${id}-preview-title">
            <div class="wagtail-vega-builder__preview-header">
              <h3 id="${id}-preview-title">${e("preview")}</h3>
              <div class="wagtail-vega-builder__scheme" data-scheme-picker hidden>
                <label for="${id}-scheme">${e("colours")}</label>
                <select id="${id}-scheme" data-scheme>
                  <option value="light">${e("light")}</option>
                  <option value="dark">${e("dark")}</option>
                </select>
              </div>
            </div>
            <div class="wagtail-vega-builder__chart" data-color-scheme="light" data-chart></div>
            <ul class="wagtail-vega-builder__warnings" data-warnings aria-live="polite"></ul>
          </section>
        </div>
        <footer class="wagtail-vega-builder__footer">
          <div class="wagtail-vega-builder__messages">
            <p class="wagtail-vega-builder__status" id="${id}-status" role="status"><span data-notice></span> <span data-status></span></p>
            <ul class="wagtail-vega-builder__errors" role="alert" data-errors></ul>
          </div>
          <div class="wagtail-vega-builder__actions">
            <button type="button" class="button button-secondary" data-undo disabled>${e("undo")}</button>
            <button type="button" class="button" data-close>${e("close")}</button>
          </div>
        </footer>`;
      document.body.append(dialog);
      return dialog;
    }

    /** A labelled control: <div><label/>control<p hint/></div> */
    control(name, label, input, hint) {
      const id = `${this.id}-${name}`;
      input.id = id;
      const hintEl = hint ? h("p", { className: "wagtail-vega-builder__hint", id: `${id}-hint`, text: hint }) : null;
      if (hintEl) input.setAttribute("aria-describedby", hintEl.id);
      return h(
        "div",
        { className: "wagtail-vega-builder__control", "data-control": name },
        h("label", { for: id, text: label }),
        input,
        hintEl,
      );
    }

    checkbox(name, label, prop) {
      const id = `${this.id}-${name}`;
      return h(
        "div",
        { className: "wagtail-vega-builder__check", "data-control": name },
        h("input", { type: "checkbox", id, "data-prop": prop }),
        h("label", { for: id, text: label }),
      );
    }

    buildControls() {
      const S = this.spec;
      const select = (prop, options = []) => {
        const el = h("select", { "data-prop": prop });
        setOptions(el, options);
        return el;
      };

      const suggestions = h(
        "details",
        { className: "wagtail-vega-builder__section wagtail-vega-builder__suggestions", "data-suggestions": true },
        h("summary", { text: t("suggestions") }),
        h("p", { className: "wagtail-vega-builder__hint", text: t("suggestionsHelp") }),
        h("ul", { "data-suggestion-list": true }),
      );

      const chart = h(
        "fieldset",
        { className: "wagtail-vega-builder__section" },
        h("legend", { text: t("chart") }),
        h(
          "div",
          { className: "wagtail-vega-builder__grid" },
          this.control("mark", t("chartType"), select("mark", S.MARKS.map((m) => [m, t(`mark.${m}`)]))),
          this.control("arrangement", t("arrangement"), select("arrangement")),
        ),
        h("p", { className: "wagtail-vega-builder__hint", "data-arrangement-hint": true, hidden: true }),
        this.checkbox("point", t("point"), "point"),
        this.checkbox("donut", t("donut"), "donut"),
        this.checkbox("tooltip", t("tooltip"), "tooltip"),
      );

      const channels = S.CHANNELS.map((name) => {
        const fieldset = h(
          "fieldset",
          { className: "wagtail-vega-builder__section wagtail-vega-builder__channel", "data-channel": name },
          h("legend", { text: t(`channel.${name}`) }),
          h(
            "div",
            { className: "wagtail-vega-builder__grid" },
            this.control(`${name}-field`, t("field"), select("field")),
            this.control(`${name}-type`, t("type"), select("type")),
            this.control(`${name}-aggregate`, t("aggregate"), select("aggregate")),
            this.control(`${name}-bin`, t("bin"), select("bin")),
            this.control(`${name}-timeUnit`, t("timeUnit"), select("timeUnit")),
            this.control(`${name}-sort`, t("sort"), select("sort")),
            this.control(`${name}-title`, t(`channelTitle.${name}`), h("input", { type: "text", "data-prop": "title" })),
          ),
        );
        if (name === "y") {
          return [
            h(
              "div",
              { className: "wagtail-vega-builder__swap", "data-control": "swap" },
              h("button", { type: "button", className: "button button-small button-secondary", "data-swap": true, text: t("swap") }),
            ),
            fieldset,
          ];
        }
        return fieldset;
      });

      const width = h("input", { type: "number", min: "50", step: "10", inputmode: "numeric", "data-prop": "widthValue" });
      const height = h("input", { type: "number", min: "50", step: "10", inputmode: "numeric", "data-prop": "height" });
      const layout = h(
        "fieldset",
        { className: "wagtail-vega-builder__section" },
        h("legend", { text: t("layout") }),
        this.control("chart-title", t("chartTitle"), h("input", { type: "text", "data-prop": "chartTitle" })),
        h(
          "div",
          { className: "wagtail-vega-builder__grid" },
          this.control("width", t("width"), select("width")),
          this.control("width-value", t("widthValue"), width),
          this.control("height", t("height"), height, t("heightHint")),
        ),
      );

      const kept = h(
        "section",
        { className: "wagtail-vega-builder__section wagtail-vega-builder__kept", "data-kept-section": true, "aria-labelledby": `${this.id}-kept-title`, hidden: true },
        h("h3", { id: `${this.id}-kept-title`, text: t("keptTitle") }),
        h("div", { "data-kept": true }),
        h("div", { "data-dropped": true }),
      );

      const container = this.$("[data-controls]");
      container.replaceChildren(suggestions, chart, ...channels.flat(), layout, kept);
      container.addEventListener("change", (event) => this.onControl(event.target));
      container.addEventListener("input", (event) => {
        if (event.target.matches("input[type=text], input[type=number]")) this.onControl(event.target);
      });
      container.addEventListener("click", (event) => {
        const button = event.target.closest("button");
        if (!button) return;
        if (button.matches("[data-swap]")) this.swap();
        else if (button.dataset.suggestion !== undefined) this.useSuggestion(Number(button.dataset.suggestion));
      });
    }

    // -- Tabs -----------------------------------------------------------------------

    setupTabs() {
      const tabs = [...this.dialog.querySelectorAll("[role=tab]")];
      for (const tab of tabs) {
        tab.addEventListener("click", () => this.showTab(tab.dataset.tab));
        tab.addEventListener("keydown", (event) => {
          const index = tabs.indexOf(tab);
          let next = null;
          if (event.key === "ArrowRight" || event.key === "ArrowDown") next = tabs[(index + 1) % tabs.length];
          else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = tabs[(index - 1 + tabs.length) % tabs.length];
          else if (event.key === "Home") next = tabs[0];
          else if (event.key === "End") next = tabs[tabs.length - 1];
          if (!next) return;
          event.preventDefault();
          this.showTab(next.dataset.tab);
          next.focus();
        });
      }
    }

    showTab(name) {
      for (const tab of this.dialog.querySelectorAll("[role=tab]")) {
        const selected = tab.dataset.tab === name;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
      }
      for (const panel of this.dialog.querySelectorAll("[role=tabpanel]")) {
        panel.hidden = panel.dataset.panel !== name;
      }
      if (name === "code") this.editor.view.requestMeasure();
    }

    // -- Opening and closing ---------------------------------------------------------

    open() {
      this.dialog = this.buildDialog();
      this.setupTabs();
      const select = this.$("[data-dataset]");
      for (const dataset of this.datasets) select.add(new Option(dataset.name, dataset.name));
      for (const name of this.extraNames) {
        const option = new Option(t("codeDataset", { name }), name);
        option.disabled = true;
        select.add(option);
      }
      if (this.datasetName) select.value = this.datasetName;
      this.$("[data-dataset-picker]").hidden = this.datasets.length + this.extraNames.length < 2;
      select.addEventListener("change", () => this.switchDataset(select.value));

      const scheme = this.$("[data-scheme]");
      scheme.value = this.scheme;
      scheme.addEventListener("change", () => {
        this.scheme = scheme.value;
        this.renderPreview();
      });

      for (const button of this.dialog.querySelectorAll("[data-close]")) {
        button.addEventListener("click", () => this.close());
      }
      this.$("[data-undo]").addEventListener("click", () => this.undo());
      this.$("[data-start-fresh]").addEventListener("click", () => this.startFresh());
      // Escape (native "cancel") and dialog.close() both end up here
      this.dialog.addEventListener("close", () => this.cleanUp());
      this.buildControls();

      // The field's own code editor, in the Code tab while the dialog is open
      const code = this.$("[data-code]");
      code.append(this.editor.host);
      this.editor.host.hidden = false;
      this.openingText = this.text;
      this.unsubscribe = [
        this.editor.onChange((text) => {
          this.updateUndo();
          this.fromCode(text);
        }),
        this.editor.onProblems((problems) => {
          this.$("[data-code-badge]").hidden = !problems.some((p) => p.severity === "error");
        }),
      ];

      document.documentElement.classList.add("wagtail-vega-builder-open");
      this.dialog.showModal();
      this.$("[data-tab=visual]").focus();
      this.setNotice(t("autosaveNote"));
      loadLibraries(this.config).catch(() => {});
      this.load();
    }

    async load() {
      if (this.datasets.length) this.setStatus(t("loading", { name: this.datasets.map((d) => d.name).join(", ") }));
      const { rows, errors } = await loadAllRows(this.datasets, this.config);
      if (!this.dialog) return;
      this.rowsByName = rows;
      this.loaded = true;
      this.setStatus("");
      this.setErrors(errors);
      this.fromCode(this.text);
      this.$("[data-start-fresh]").hidden = this.mode !== "unrepresentable";
      // Focus the first setting, unless the editor has already moved on
      const active = document.activeElement;
      if (this.mode === "visual" || this.mode === "pending") {
        if (!active || active === document.body || active.matches("[data-tab=visual], dialog")) {
          (this.$("[data-dataset-picker]").hidden ? this.$("[data-prop=mark]") : this.$("[data-dataset]")).focus();
        }
      }
    }

    close() {
      if (this.dialog?.open) this.dialog.close();
      else this.cleanUp();
    }

    cleanUp() {
      if (!this.dialog) return;
      clearTimeout(this.previewTimer);
      // Nothing's lost: whatever was typed last goes to the field now
      this.editor.flush();
      for (const unsubscribe of this.unsubscribe || []) unsubscribe();
      this.editor.host.hidden = true;
      this.textarea.after(this.editor.host);
      this.$("[data-chart]").wagtailVegaView?.finalize();
      this.dialog.remove();
      this.dialog = null;
      document.documentElement.classList.remove("wagtail-vega-builder-open");
      this.trigger.focus();
      this.launcher.closed();
    }

    // -- Messages ---------------------------------------------------------------

    setStatus(text) {
      this.$("[data-status]").textContent = text;
    }

    setNotice(text) {
      this.$("[data-notice]").textContent = text;
    }

    setErrors(messages) {
      this.$("[data-errors]").replaceChildren(...messages.map((m) => h("li", { text: m })));
    }

    announce(text) {
      this.setStatus(text);
    }

    // -- One spec, three views ---------------------------------------------------

    columnsFor(name) {
      return this.spec.describeColumns(this.rowsByName[name] || []);
    }

    /** Read the code into the settings and preview. */
    fromCode(text) {
      // Before the data has loaded, load() reads the code once it has
      if (this.writing || !this.dialog || !this.loaded) return;
      const S = this.spec;
      const trimmed = text.trim();
      this.frozen = null;
      this.columns = this.columnsFor(this.datasetName);
      const usable = this.datasets.some((d) => this.rowsByName[d.name]?.length);

      if (!trimmed || trimmed === "null") {
        // Nothing yet: offer a suggestion, written once the editor uses it
        this.current = null;
        if (!usable) {
          this.mode = "noData";
        } else {
          this.mode = "pending";
          this.state = S.initialState(this.columns);
          this.original = null;
          this.current = S.toSpec(this.state, this.datasetName).spec;
        }
        this.showMode();
        this.schedulePreview();
        return;
      }

      let parsed;
      try {
        parsed = JSON.parse(text);
      } catch (error) {
        // Keep the settings and preview at the last valid spec
        const position = Number(/position (\d+)/.exec(error.message)?.[1]);
        const line = Number.isFinite(position) ? text.slice(0, position).split("\n").length : "?";
        this.frozen = { line, error: error.message };
        this.showMode();
        return;
      }

      this.current = parsed;
      const opened = S.fromSpec(parsed);
      if (opened.problem) {
        this.mode = "unrepresentable";
        this.state = null;
        this.problem = opened.problem;
      } else if (!usable) {
        this.mode = "noData";
        this.state = null;
      } else {
        this.mode = "visual";
        this.state = opened.state;
        this.missingDataset = null;
        if (opened.dataset && this.rowsByName[opened.dataset]) {
          this.datasetName = opened.dataset;
        } else if (opened.dataset) {
          this.missingDataset = opened.dataset;
        }
        this.$("[data-dataset]").value = this.datasetName;
        this.columns = this.columnsFor(this.datasetName);
        // What the settings keep from this spec, to show what changes remove
        this.original = S.toSpec(this.state, this.datasetName);
      }
      this.showMode();
      this.schedulePreview();
    }

    /** Show the settings for the current mode: usable, or disabled with why. */
    showMode() {
      const fieldset = this.$("[data-controls-fieldset]");
      const notice = this.$("[data-controls-notice]");
      const note = this.$("[data-controls-note]");
      const controls = this.$("[data-controls]");
      let text = "";
      let disabled = false;
      if (this.frozen) {
        text = t("frozen", this.frozen);
        disabled = true;
      } else if (this.mode === "noData") {
        text = this.hasDataField ? t("noData") : t("codeData");
        disabled = true;
      } else if (this.mode === "unrepresentable") {
        text = t("unrepresentable", { problem: message(this.problem) });
        disabled = true;
      } else if (this.mode === "pending") {
        text = t("pending");
      } else if (this.missingDataset) {
        text = this.extraNames.includes(this.missingDataset)
          ? t("codeDatasetUsed", { missing: this.missingDataset, name: this.datasetName })
          : t("missingDataset", { missing: this.missingDataset, name: this.datasetName });
      }
      note.textContent = text;
      notice.hidden = !text;
      notice.classList.toggle("is-blocking", disabled);
      this.$("[data-start-fresh]").hidden = this.frozen !== null || this.mode !== "unrepresentable";
      fieldset.disabled = disabled;
      controls.hidden = !this.state;
      if (this.state) this.sync();
      if (this.mode === "pending") this.$("[data-suggestions]").open = true;
    }

    /** Write the settings' spec into the code (and so the field). */
    fromControls() {
      if (!this.state) return;
      this.sync();
      const { spec } = this.spec.toSpec(this.state, this.datasetName);
      const text = JSON.stringify(spec, null, 2);
      this.writing = true;
      try {
        this.editor.setText(text, { userEvent: "input.builder" });
      } finally {
        this.writing = false;
      }
      // A setting is a finished change: no need to wait for more typing
      this.editor.flush();
      this.current = spec;
      this.mode = "visual";
      this.missingDataset = null;
      this.showMode();
      this.updateUndo();
      this.schedulePreview();
    }

    updateUndo() {
      if (this.dialog) this.$("[data-undo]").disabled = this.text === this.openingText;
    }

    undo() {
      this.editor.setText(this.openingText, { userEvent: "input.builder.undo" });
      this.editor.flush();
      this.announce(t("undone"));
      this.updateUndo();
    }

    startFresh() {
      this.columns = this.columnsFor(this.datasetName);
      this.state = this.spec.initialState(this.columns);
      this.original = null;
      this.announce(t("startedFresh"));
      this.fromControls();
      this.$("[data-prop=mark]").focus();
    }

    switchDataset(name) {
      this.datasetName = name;
      this.columns = this.columnsFor(name);
      if (!this.state) {
        this.fromCode(this.text);
        return;
      }
      const names = new Set(this.columns.map((c) => c.name));
      const missing = this.spec.specFields(this.state).filter((f) => !names.has(f));
      if (missing.length) {
        const fresh = this.spec.initialState(this.columns);
        this.state.mark = fresh.mark;
        this.state.arrangement = fresh.arrangement;
        this.state.channels = fresh.channels;
        this.announce(t("datasetFields", { name }));
      } else {
        this.announce(t("datasetNow", { name }));
      }
      this.fromControls();
    }

    onControl(el) {
      const S = this.spec;
      const state = this.state;
      const prop = el.dataset.prop;
      if (!state || !prop || el.value === CUSTOM) return;
      const channelEl = el.closest("[data-channel]");
      if (channelEl) {
        const name = channelEl.dataset.channel;
        const ch = state.channels[name];
        // A control changed from "Custom" no longer uses the spec's value
        const extraKey = { field: null, type: "type", aggregate: "aggregate", bin: "bin", timeUnit: "timeUnit", sort: "sort", title: "title" }[prop];
        if (extraKey && S.extrasApply(ch)) delete ch.extras[extraKey];
        if (prop === "field") {
          S.setField(ch, el.value, this.columns);
          if ((name === "row" || name === "column") && el.value && state.width === "container") {
            state.width = "";
            this.announce(t("widthAuto"));
          }
        } else if (prop === "type") {
          ch.type = el.value;
          ch.typeImplied = false;
          if (ch.type !== "temporal" && ch.type !== "ordinal") ch.timeUnit = "";
          if (ch.type !== "quantitative") ch.bin = false;
        } else if (prop === "aggregate") {
          ch.aggregate = el.value;
        } else if (prop === "bin") {
          ch.bin = el.value === "bin";
        } else if (prop === "timeUnit") {
          ch.timeUnit = el.value;
        } else if (prop === "sort") {
          ch.sort = el.value;
        } else if (prop === "title") {
          ch.title = el.value;
        }
      } else if (prop === "mark") {
        state.mark = el.value;
        const allowed = S.ARRANGEMENTS.find(([a]) => a === state.arrangement)[1];
        if (!allowed.includes(state.mark)) state.arrangement = "";
      } else if (prop === "arrangement") {
        const measure = state.channels[S.measureChannel(state)];
        if (S.extrasApply(measure)) delete measure.extras.stack;
        state.arrangement = el.value;
      } else if (prop === "point" || prop === "donut" || prop === "tooltip") {
        state[prop] = el.checked;
        if (S.markExtrasApply(state)) delete state.markExtras[prop === "donut" ? "innerRadius" : prop];
      } else if (prop === "chartTitle") {
        state.title = el.value;
        delete state.extras.title;
      } else if (prop === "width") {
        delete state.extras.width;
        state.width = el.value === "fixed" ? Number(this.$("[data-prop=widthValue]").value) || 400 : el.value;
      } else if (prop === "widthValue") {
        const value = Number(el.value);
        if (value > 0) state.width = value;
      } else if (prop === "height") {
        delete state.extras.height;
        state.height = el.value === "" ? "" : Number(el.value) || "";
      }
      this.fromControls();
    }

    swap() {
      const { channels } = this.state;
      [channels.x, channels.y] = [channels.y, channels.x];
      this.fromControls();
      this.announce(t("swapped"));
    }

    useSuggestion(index) {
      const suggestion = this.suggestions[index];
      if (!suggestion) return;
      this.spec.applySuggestion(this.state, suggestion, this.columns);
      this.fromControls();
      this.announce(t("suggestionApplied", { label: message(suggestion.message) }));
    }

    // -- Showing the state --------------------------------------------------------

    fieldOptions() {
      const S = this.spec;
      const options = [["", t("none")], [S.COUNT, t("count")]];
      for (const column of this.columns) {
        options.push([column.name, t("column", { name: column.name, type: t(`columnType.${column.type}`) })]);
      }
      const names = new Set(this.columns.map((c) => c.name));
      for (const field of S.specFields(this.state)) {
        if (!names.has(field)) options.push([field, t("specField", { name: field })]);
      }
      return options;
    }

    sync() {
      const S = this.spec;
      const state = this.state;
      const $c = (selector) => this.$(`[data-controls] ${selector}`);
      const show = (name, visible) => {
        $c(`[data-control="${name}"]`).hidden = !visible;
      };
      const setValue = (el, value) => {
        if (el.type === "checkbox") el.checked = Boolean(value);
        else if (el.value !== String(value)) el.value = String(value);
      };
      const custom = (options, isCustom, value) =>
        isCustom ? [...options, [CUSTOM, t("custom", { value: keptText(value) })]] : options;

      // Suggestions
      this.suggestions = S.suggest(this.columns);
      const list = $c("[data-suggestion-list]");
      const labels = JSON.stringify(this.suggestions.map((s) => message(s.message)));
      if (list.dataset.labels !== labels) {
        list.dataset.labels = labels;
        list.replaceChildren(
          ...this.suggestions.map((s, i) =>
            h("li", {}, h("button", { type: "button", className: "button button-small button-secondary", "data-suggestion": String(i), text: message(s.message) })),
          ),
        );
      }
      $c("[data-suggestions]").hidden = !this.suggestions.length;

      // The chart
      setValue($c("[data-prop=mark]"), state.mark);
      const stackable = state.mark === "bar" || state.mark === "area";
      show("arrangement", stackable);
      const arrangement = $c("[data-prop=arrangement]");
      const customStack = stackable && S.customArrangement(state);
      const measure = state.channels[S.measureChannel(state)];
      setOptions(
        arrangement,
        custom(
          S.ARRANGEMENTS.filter(([, marks]) => marks.includes(state.mark)).map(([v]) => [v, t(`arrangement.${v || "stacked"}`)]),
          customStack,
          measure.extras.stack,
        ),
      );
      setValue(arrangement, customStack ? CUSTOM : state.arrangement);
      const hint = $c("[data-arrangement-hint]");
      const needsColor = stackable && state.arrangement !== "none" && !S.hasField(state.channels.color);
      hint.hidden = !needsColor;
      hint.textContent = needsColor ? t(`arrangementHint.${state.mark}`) : "";
      show("point", state.mark === "line" || state.mark === "area");
      show("donut", state.mark === "arc");
      setValue($c("[data-prop=point]"), state.point);
      setValue($c("[data-prop=donut]"), state.donut);
      setValue($c("[data-prop=tooltip]"), state.tooltip);

      // Channels
      const fieldOptions = this.fieldOptions();
      const shown = new Set(S.channelsFor(state.mark));
      show("swap", shown.has("x"));
      for (const [name, ch] of Object.entries(state.channels)) {
        const fieldset = $c(`[data-channel="${name}"]`);
        fieldset.hidden = !shown.has(name);
        if (!shown.has(name)) continue;
        const extras = S.extrasApply(ch) ? ch.extras : {};
        const isCustom = (key) => key in extras;
        const prop = (p) => fieldset.querySelector(`[data-prop="${p}"]`);
        const showIn = (p, visible) => {
          prop(p).closest("[data-control]").hidden = !visible;
        };
        const field = prop("field");
        setOptions(field, fieldOptions);
        setValue(field, ch.count ? S.COUNT : ch.field);
        const has = S.hasField(ch);
        const column = this.columns.find((c) => c.name === ch.field);

        setOptions(prop("type"), custom(S.TYPES.map((v) => [v, t(`type.${v}`)]), isCustom("type"), extras.type));
        setValue(prop("type"), isCustom("type") ? CUSTOM : ch.type || S.impliedType(ch));
        showIn("type", has && !ch.count);

        setOptions(prop("aggregate"), custom([["", t("aggregate.none")], ...S.AGGREGATES.map((v) => [v, t(`aggregate.${v}`)])], isCustom("aggregate"), extras.aggregate));
        setValue(prop("aggregate"), isCustom("aggregate") ? CUSTOM : ch.aggregate);
        showIn("aggregate", has && !ch.count);

        setOptions(prop("bin"), custom([["", t("bin.none")], ["bin", t("bin.bin")]], isCustom("bin"), extras.bin));
        setValue(prop("bin"), isCustom("bin") ? CUSTOM : ch.bin ? "bin" : "");
        showIn("bin", has && !ch.count && ((ch.type === "quantitative" && name !== "theta") || ch.bin || isCustom("bin")));

        setOptions(prop("timeUnit"), custom([["", t("timeUnit.none")], ...S.TIME_UNITS.map((v) => [v, t(`timeUnit.${v}`)])], isCustom("timeUnit"), extras.timeUnit));
        setValue(prop("timeUnit"), isCustom("timeUnit") ? CUSTOM : ch.timeUnit);
        const temporalish = ch.type === "temporal" || (ch.type === "ordinal" && column?.type === "temporal");
        showIn("timeUnit", has && !ch.count && (temporalish || Boolean(ch.timeUnit) || isCustom("timeUnit")));

        const sortOptions = [
          ["", t("sort.default")],
          ["ascending", t("sort.ascending")],
          ["descending", t("sort.descending")],
          ["none", t("sort.none")],
        ];
        for (const other of S.SORT_CHANNELS) {
          if (other === name || !shown.has(other) || !S.hasField(state.channels[other])) continue;
          const channel = t(`channelShort.${other}`);
          sortOptions.push([other, t("sort.byAscending", { channel })], [`-${other}`, t("sort.byDescending", { channel })]);
        }
        if (ch.sort && !sortOptions.some(([v]) => v === ch.sort)) sortOptions.push([ch.sort, ch.sort]);
        setOptions(prop("sort"), custom(sortOptions, isCustom("sort"), extras.sort));
        setValue(prop("sort"), isCustom("sort") ? CUSTOM : ch.sort);
        showIn("sort", has && name !== "size" && name !== "theta");

        setValue(prop("title"), ch.title);
        prop("title").placeholder = isCustom("title") ? keptText(extras.title) : t("titleDefault");
        showIn("title", has);
      }

      // Title and size
      const facets = S.hasField(state.channels.row) || S.hasField(state.channels.column);
      setValue($c("[data-prop=chartTitle]"), state.title);
      $c("[data-prop=chartTitle]").placeholder = "title" in state.extras ? keptText(state.extras.title) : "";
      const width = $c("[data-prop=width]");
      setOptions(
        width,
        custom(
          [
            ["container", t("width.container"), facets && state.width !== "container"],
            ["", t("width.auto")],
            ["fixed", t("width.fixed")],
          ],
          "width" in state.extras,
          state.extras.width,
        ),
      );
      setValue(width, "width" in state.extras ? CUSTOM : typeof state.width === "number" ? "fixed" : state.width);
      show("width-value", typeof state.width === "number" && !("width" in state.extras));
      if (typeof state.width === "number") setValue($c("[data-prop=widthValue]"), state.width);
      setValue($c("[data-prop=height]"), state.height);
      $c("[data-prop=height]").placeholder = "height" in state.extras ? keptText(state.extras.height) : "";

      this.syncKept();
    }

    syncKept() {
      const { kept } = this.spec.toSpec(this.state, this.datasetName);
      const original = this.original?.kept || [];
      const dropped = original.filter((path) => !kept.includes(path));
      const list = (heading, paths) =>
        paths.length
          ? [h("p", { text: heading }), h("ul", {}, paths.map((path) => h("li", {}, h("code", { text: path }))))]
          : [];
      this.$("[data-kept]").replaceChildren(...list(t("keptIntro"), kept));
      this.$("[data-dropped]").replaceChildren(...list(t("droppedIntro"), dropped));
      this.$("[data-kept-section]").hidden = !kept.length && !dropped.length;
    }

    // -- Preview ------------------------------------------------------------------

    schedulePreview() {
      clearTimeout(this.previewTimer);
      this.previewTimer = setTimeout(() => this.renderPreview(), PREVIEW_DELAY);
    }

    async renderPreview() {
      if (!this.dialog || !this.current) return;
      const token = ++this.previewToken;
      const theme = themeFor(this.config, this.themeField);
      this.$("[data-scheme-picker]").hidden = !theme?.dark;
      const warnings = this.$("[data-warnings]");
      const show = (messages) => {
        const text = JSON.stringify(messages);
        if (warnings.dataset.text === text) return;
        warnings.dataset.text = text;
        warnings.replaceChildren(...messages.map((m) => h("li", { text: m })));
      };
      let result;
      try {
        result = await drawChart(this.$("[data-chart]"), this.current, {
          rowsByName: this.rowsByName,
          theme,
          dark: Boolean(theme?.dark) && this.scheme === "dark",
          config: this.config,
          isCurrent: () => token === this.previewToken && Boolean(this.dialog),
        });
      } catch (e) {
        if (this.dialog) show([t("previewUnavailable", { error: e.message })]);
        return;
      }
      if (token !== this.previewToken || !this.dialog) return;
      const notes = this.hasDataField ? [] : [t("field.codeData")];
      show(result.error ? [t("previewError", { error: result.error }), ...result.messages] : [...notes, ...result.messages]);
    }
  }

  // -- The spec field -----------------------------------------------------------------

  class ChartBuilderLauncher extends HTMLElement {
    /** The spec textarea this belongs to: a sibling, named by data-for. */
    get textarea() {
      const name = this.dataset.for;
      if (!name || !this.parentElement) return null;
      return this.parentElement.querySelector(`:scope > textarea[name="${CSS.escape(name)}"]`);
    }

    connectedCallback() {
      if (this.button) return;
      // The text is the same for every field on the page
      STRINGS = { ...STRINGS, ...(this.config.strings || {}) };
      this.button = this.querySelector("[data-builder-open]");
      this.noteEl = this.querySelector("[data-builder-note]");
      this.noteEl.id = `wagtail-vega-builder-note-${++uid}`;
      this.promptEl = this.querySelector("[data-field-empty]");
      this.promptEl.id = `wagtail-vega-builder-prompt-${uid}`;
      this.button.addEventListener("click", () => this.open());
      const textarea = this.textarea;
      textarea?.addEventListener("input", () => this.changed());
      textarea?.addEventListener("change", () => this.changed());
      // StructBlock renders its fields one after another, and telepath
      // attaches the code editor after this connects
      setTimeout(() => this.setUp());
    }

    disconnectedCallback() {
      this.observer?.disconnect();
    }

    get config() {
      try {
        return JSON.parse(this.dataset.config || "{}");
      } catch {
        return {};
      }
    }

    setUp() {
      const context = chartContext(this);
      this.context = context;
      const editor = context.textarea?.wagtailVegaEditor;
      if (editor && editor !== this.editor) {
        this.editor = editor;
        // Focusing the field (its label, or Wagtail) focuses the button
        editor.focusTarget = this.button;
        editor.onProblems((problems) => this.showProblems(problems));
      }
      // Redraw when the chart's data or theme changes
      const redraw = () => this.changed({ dataOnly: true });
      context.dataField?.addEventListener("input", redraw);
      context.dataField?.addEventListener("change", redraw);
      context.themeField?.addEventListener("change", redraw);
      // Draw when the field is first shown (e.g. a collapsed block opened)
      if ("IntersectionObserver" in window) {
        this.observer = new IntersectionObserver((entries) => {
          this.visible = entries.some((entry) => entry.isIntersecting);
          if (this.visible && this.stale) this.renderField();
        });
        this.observer.observe(this);
      } else {
        this.visible = true;
      }
      this.stale = true;
      this.showEmpty();
      if (this.visible) this.renderField();
    }

    changed() {
      this.showEmpty();
      this.stale = true;
      if (this.session?.dialog) return; // drawn when the editor closes
      clearTimeout(this.fieldTimer);
      this.fieldTimer = setTimeout(() => {
        if (this.visible) this.renderField();
      }, FIELD_DELAY);
    }

    closed() {
      this.session = null;
      this.stale = true;
      this.showEmpty();
      this.renderField();
    }

    get isEmpty() {
      const value = this.textarea?.value.trim() ?? "";
      return value === "" || value === "null";
    }

    /** While the spec is empty, a prompt instead of the chart, and the
     * button is the main action. */
    showEmpty() {
      const empty = this.isEmpty;
      this.classList.toggle("is-empty", empty);
      this.button.classList.toggle("button-secondary", !empty);
      this.promptEl.hidden = !empty;
      this.querySelector("[data-field-preview]").hidden = empty;
      this.describe();
    }

    describe() {
      const ids = [this.promptEl, this.noteEl].filter((el) => el && !el.hidden).map((el) => el.id);
      if (ids.length) this.button.setAttribute("aria-describedby", ids.join(" "));
      else this.button.removeAttribute("aria-describedby");
    }

    note(text) {
      this.noteEl.textContent = text;
      this.noteEl.hidden = !text;
      this.describe();
    }

    showProblems(problems) {
      const box = this.querySelector("[data-field-problems]");
      const list = this.querySelector("[data-field-problem-list]");
      list.replaceChildren(
        ...problems.map((p) => h("li", { className: `is-${p.severity}`, text: t("field.problem", p) })),
      );
      box.hidden = !problems.length;
    }

    /** Draw the field's chart from the spec as it is now. */
    async renderField() {
      if (!this.context || this.isEmpty) return;
      this.stale = false;
      const token = (this.fieldToken = (this.fieldToken || 0) + 1);
      const isCurrent = () => token === this.fieldToken;
      const chart = this.querySelector("[data-field-chart]");
      const status = this.querySelector("[data-field-status]");
      let spec;
      try {
        spec = JSON.parse(this.textarea.value);
      } catch {
        chart.replaceChildren();
        status.textContent = t("field.invalid");
        return;
      }
      if (!isObject(spec)) {
        chart.replaceChildren();
        status.textContent = t("field.invalid");
        return;
      }
      status.textContent = chart.childElementCount ? "" : t("field.loading");
      const { rows, errors } = await loadAllRows(readDatasets(this.context.dataField), this.config);
      if (!isCurrent()) return;
      const theme = themeFor(this.config, this.context.themeField);
      let result;
      try {
        result = await drawChart(chart, spec, {
          rowsByName: rows,
          theme,
          dark: Boolean(theme?.dark) && adminScheme() === "dark",
          config: this.config,
          isCurrent,
        });
      } catch (e) {
        status.textContent = t("previewUnavailable", { error: e.message });
        return;
      }
      if (!isCurrent()) return;
      if (result.error) {
        chart.replaceChildren();
        status.textContent = t("field.error", { error: result.error });
      } else {
        status.textContent = [...errors, ...(this.context.dataField ? [] : [t("field.codeData")])].join(" ");
      }
    }

    open() {
      const context = chartContext(this);
      this.context = context;
      if (!context.textarea?.wagtailVegaEditor || !admin.chartSpec) {
        this.note(t("note.scripts"));
        return;
      }
      this.note("");
      this.session = new Session(this, context);
      this.session.open();
    }
  }

  if (!window.customElements.get("wagtail-vega-chart-builder")) {
    window.customElements.define("wagtail-vega-chart-builder", ChartBuilderLauncher);
  }

  // Internal helpers, exposed for tests. Not a public API.
  admin.chartBuilder = {
    _internal: { urlAllowed, formatFromUrl, deepMerge, previewSpec, sampleRows, adminScheme, t },
  };
})();
