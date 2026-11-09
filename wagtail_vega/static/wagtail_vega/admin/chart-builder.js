/* wagtail-vega admin: the "Build chart" button and the chart builder.
 *
 * A button on each spec field opens a lightbox (a modal <dialog>) with one
 * of the chart's datasets, read from the unsaved form. Editors pick a chart
 * type and fields with ordinary form controls, see a live preview drawn
 * with the Vega libraries the site already ships, and "Use this chart"
 * writes a Vega-Lite 6 spec that loads the dataset by name.
 *
 * - The model and its specs (including how an existing spec is opened and
 *   what's kept from it) are in chart-spec.js.
 * - Data comes from the form as it is now: pasted text is parsed with
 *   data-format.js (as the server will), documents through the
 *   document-rows endpoint, and URL datasets are fetched by the browser,
 *   from allowed hosts only.
 * - The spec is checked with the validate-spec endpoint (the checks saving
 *   runs) before it's written.
 * - Writing follows code-editor.js's contract: textarea.value is set and a
 *   bubbling "input" event dispatched, which the code editor takes as one
 *   undoable change.
 * - The Vega libraries are loaded the first time a builder opens, not with
 *   the edit page. The preview uses vega-interpreter, so it needs no
 *   'unsafe-eval' in the admin's Content Security Policy.
 *
 * The button is rendered by the spec field's CodeEditor widget (widgets.py),
 * with its settings in data-config. Needs data-format.js and chart-spec.js.
 */
(() => {
  "use strict";

  const admin = (window.wagtailVegaAdmin = window.wagtailVegaAdmin || {});
  // Element boundaries in Wagtail's StreamField / StructBlock markup
  const BOUNDARY = "[data-streamfield-child], [data-contentpath], [data-contentpath-disabled]";
  const CUSTOM = "__custom__";
  const PREVIEW_DELAY = 200; // ms

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
   * will actually fetch: same-origin URLs are allowed, absolute ones must be
   * http(s) on an allowed host. Protocol-relative URLs are refused, as on the
   * server. */
  function urlAllowed(raw, allowedHosts, base) {
    if (typeof raw !== "string" || !raw.trim() || raw.startsWith("//")) return false;
    let url;
    try {
      url = new URL(raw, base);
    } catch {
      return false;
    }
    if (url.origin === new URL(base).origin) return true;
    if (url.protocol !== "http:" && url.protocol !== "https:") return false;
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

  /** The spec field's chart: its datasets field and theme field, if any. */
  function chartContext(launcher) {
    const boundary = launcher.closest(BOUNDARY)?.parentElement?.closest(BOUNDARY);
    return {
      textarea: launcher.textarea,
      dataField: boundary ? ownField(boundary, "data") : null,
      themeField: boundary ? ownField(boundary, "theme") : null,
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

  function readDatasets(dataField) {
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
    if (!parseRows) throw new Error("The data editor's scripts aren't loaded.");
    if (dataset.source === "document") {
      const url = `${config.rowsUrl}?id=${encodeURIComponent(dataset.document)}`;
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || `Couldn't load the document (${response.status}).`);
      return body.rows;
    }
    if (dataset.source === "url") {
      if (!urlAllowed(dataset.url, config.allowedHosts, document.baseURI)) {
        throw new Error(`Data can't be loaded from ${dataset.url}.`);
      }
      const url = new URL(dataset.url, document.baseURI);
      const response = await fetch(url);
      if (!response.ok) throw new Error(`Couldn't load ${url.href} (${response.status}).`);
      return parseRows(await response.text(), dataset.format || formatFromUrl(url));
    }
    return parseRows(dataset.paste);
  }

  function csrfHeaders() {
    const config = window.wagtailConfig || {};
    const token =
      config.CSRF_TOKEN ||
      document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
      document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1];
    return token ? { [config.CSRF_HEADER_NAME || "X-CSRFToken"]: token } : {};
  }

  /** Problems as messages, e.g. "encoding.x.type: ...", like a failed save. */
  function problemMessages(errors) {
    return errors.map(({ path, message }) =>
      path && path.length ? `${path.join(".")}: ${message}` : message,
    );
  }

  /** Check a spec with the validation endpoint the code editor uses (the
   * same checks as saving). Returns error messages, empty if it's valid. */
  async function checkSpec(spec, config) {
    const response = await fetch(config.validateUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        ...csrfHeaders(),
      },
      body: JSON.stringify(spec),
    });
    if (!response.ok) throw new Error(`Couldn't check the spec (${response.status}).`);
    const { errors } = await response.json();
    return Array.isArray(errors) ? problemMessages(errors) : [];
  }

  // -- Preview ------------------------------------------------------------------

  let libraries = null;

  /** Load vega, vega-lite, vega-embed, vega-interpreter and wagtail-vega.js
   * (for var() resolution) once, in order. */
  function loadLibraries(config) {
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
              script.addEventListener("error", () => reject(new Error(`Couldn't load ${src}.`)));
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

  /** The spec as the page will draw it: data filled in, theme applied
   * (as BaseChartBlock.get_spec does: theme, dark, then the spec's config). */
  function previewSpec(spec, rows, theme, dark) {
    const out = clone(spec);
    out.datasets = { [spec.data.name]: rows };
    if (theme) {
      const config = deepMerge(theme.config, dark ? theme.dark : null, spec.config);
      if (Object.keys(config).length) out.config = config;
    }
    return out;
  }

  // -- The lightbox -----------------------------------------------------------

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

  const TYPE_NAMES = { quantitative: "number", nominal: "category", ordinal: "ordered", temporal: "date" };

  /** A value kept from the spec, briefly, e.g. for a placeholder. */
  function keptText(value) {
    if (value === null) return "None (kept from the spec)";
    let text = JSON.stringify(value);
    if (text.length > 40) text = `${text.slice(0, 39)}…`;
    return `${text} (kept from the spec)`;
  }

  /** One opening of the lightbox for one spec field. */
  class Session {
    constructor(launcher, textarea, datasets, themeField) {
      this.launcher = launcher;
      this.trigger = launcher.button;
      this.textarea = textarea;
      this.datasets = datasets;
      this.themeField = themeField;
      this.config = launcher.config;
      this.spec = admin.chartSpec;
      this.id = `wagtail-vega-builder-${++uid}`;
      this.previewToken = 0;
      this.scheme = adminScheme();
      this.text = textarea.value.trim();
      this.previous = null;
      this.opened = { state: null };
      if (this.text) {
        try {
          this.previous = JSON.parse(this.text);
          this.opened = this.spec.fromSpec(this.previous);
        } catch {
          this.opened = { problem: "it isn't valid JSON" };
        }
      }
      const wanted = this.opened.dataset;
      this.datasetName = datasets.some((d) => d.name === wanted) ? wanted : datasets[0].name;
      this.missingDataset = wanted && wanted !== this.datasetName ? wanted : null;
    }

    $(selector) {
      return this.dialog.querySelector(selector);
    }

    // -- Building the dialog ---------------------------------------------------

    buildDialog() {
      const id = this.id;
      const dialog = h("dialog", {
        className: "wagtail-vega-builder",
        "aria-labelledby": `${id}-title`,
        "aria-describedby": `${id}-status`,
      });
      dialog.innerHTML = `
        <header class="wagtail-vega-builder__header">
          <h2 class="wagtail-vega-builder__title" id="${id}-title">Build a chart</h2>
          <div class="wagtail-vega-builder__dataset" data-dataset-picker hidden>
            <label for="${id}-dataset">Dataset</label>
            <select id="${id}-dataset" data-dataset></select>
          </div>
          <button type="button" class="wagtail-vega-builder__close" data-cancel aria-label="Close without using the chart">${icon("cross")}</button>
        </header>
        <div class="wagtail-vega-builder__body">
          <div class="wagtail-vega-builder__problem" data-problem hidden>
            <p id="${id}-problem" data-problem-text></p>
            <p>You can start a new chart from the data instead. The spec in the field is only replaced if you choose “Use this chart” and confirm.</p>
            <div class="wagtail-vega-builder__actions">
              <button type="button" class="button" data-start-fresh aria-describedby="${id}-problem">Start a new chart</button>
            </div>
          </div>
          <div class="wagtail-vega-builder__controls" data-controls hidden></div>
          <section class="wagtail-vega-builder__preview" data-preview aria-labelledby="${id}-preview-title" hidden>
            <div class="wagtail-vega-builder__preview-header">
              <h3 id="${id}-preview-title">Preview</h3>
              <div class="wagtail-vega-builder__scheme" data-scheme-picker hidden>
                <label for="${id}-scheme">Colours</label>
                <select id="${id}-scheme" data-scheme>
                  <option value="light">Light mode</option>
                  <option value="dark">Dark mode</option>
                </select>
              </div>
            </div>
            <div class="wagtail-vega-builder__chart" data-color-scheme="light" data-chart></div>
            <ul class="wagtail-vega-builder__warnings" data-warnings aria-live="polite"></ul>
            <details class="wagtail-vega-builder__json">
              <summary>Spec (JSON)</summary>
              <pre data-json></pre>
            </details>
          </section>
        </div>
        <footer class="wagtail-vega-builder__footer">
          <div class="wagtail-vega-builder__messages" data-messages>
            <p class="wagtail-vega-builder__status" id="${id}-status" role="status"><span data-notice></span> <span data-status></span></p>
            <ul class="wagtail-vega-builder__errors" role="alert" data-errors></ul>
          </div>
          <div class="wagtail-vega-builder__actions" data-actions>
            <button type="button" class="button button-secondary" data-cancel>Cancel</button>
            <button type="button" class="button" data-use disabled>Use this chart</button>
          </div>
          <div class="wagtail-vega-builder__actions wagtail-vega-builder__confirm" data-confirm hidden>
            <p id="${id}-confirm">This replaces the spec that's in the field now.</p>
            <button type="button" class="button button-secondary" data-confirm-back>Keep editing</button>
            <button type="button" class="button" data-confirm-replace aria-describedby="${id}-confirm">Replace spec</button>
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
        h("summary", { text: "Suggested charts" }),
        h("p", { className: "wagtail-vega-builder__hint", text: "Start from a chart that suits the data's columns. It replaces the chart type and fields below." }),
        h("ul", { "data-suggestion-list": true }),
      );

      const chart = h(
        "fieldset",
        { className: "wagtail-vega-builder__section" },
        h("legend", { text: "Chart" }),
        h(
          "div",
          { className: "wagtail-vega-builder__grid" },
          this.control("mark", "Chart type", select("mark", S.MARKS)),
          this.control("arrangement", "Bars or areas that share a position", select("arrangement")),
        ),
        h("p", { className: "wagtail-vega-builder__hint", "data-arrangement-hint": true, hidden: true }),
        this.checkbox("point", "Show a point for each value", "point"),
        this.checkbox("donut", "Donut (leave a hole in the middle)", "donut"),
        this.checkbox("tooltip", "Show values in a tooltip on hover or focus", "tooltip"),
      );

      const channels = Object.entries(S.CHANNELS).map(([name, info]) => {
        const fieldset = h(
          "fieldset",
          { className: "wagtail-vega-builder__section wagtail-vega-builder__channel", "data-channel": name },
          h("legend", { text: info.label }),
          h(
            "div",
            { className: "wagtail-vega-builder__grid" },
            this.control(`${name}-field`, "Field", select("field")),
            this.control(`${name}-type`, "Type", select("type")),
            this.control(`${name}-aggregate`, "Combine rows", select("aggregate")),
            this.control(`${name}-bin`, "Bins", select("bin")),
            this.control(`${name}-timeUnit`, "Time unit", select("timeUnit")),
            this.control(`${name}-sort`, "Sort", select("sort")),
            this.control(`${name}-title`, info.titleLabel, h("input", { type: "text", "data-prop": "title" })),
          ),
        );
        if (name === "y") {
          return [
            h(
              "div",
              { className: "wagtail-vega-builder__swap", "data-control": "swap" },
              h("button", { type: "button", className: "button button-small button-secondary", "data-swap": true, text: "Swap X and Y" }),
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
        h("legend", { text: "Title and size" }),
        this.control("chart-title", "Chart title", h("input", { type: "text", "data-prop": "chartTitle" })),
        h(
          "div",
          { className: "wagtail-vega-builder__grid" },
          this.control("width", "Width", select("width")),
          this.control("width-value", "Width in pixels", width),
          this.control("height", "Height in pixels", height, "Leave blank for the default."),
        ),
      );

      const kept = h(
        "section",
        { className: "wagtail-vega-builder__section wagtail-vega-builder__kept", "data-kept-section": true, "aria-labelledby": `${this.id}-kept-title`, hidden: true },
        h("h3", { id: `${this.id}-kept-title`, text: "From the current spec" }),
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

    // -- Opening ------------------------------------------------------------------

    open() {
      this.dialog = this.buildDialog();
      const select = this.$("[data-dataset]");
      for (const dataset of this.datasets) select.add(new Option(dataset.name, dataset.name));
      select.value = this.datasetName;
      this.$("[data-dataset-picker]").hidden = this.datasets.length < 2;
      select.addEventListener("change", () => this.switchDataset(select.value));

      const scheme = this.$("[data-scheme]");
      scheme.value = this.scheme;
      scheme.addEventListener("change", () => {
        this.scheme = scheme.value;
        this.renderPreview();
      });

      for (const button of this.dialog.querySelectorAll("[data-cancel]")) {
        button.addEventListener("click", () => this.close());
      }
      this.$("[data-use]").addEventListener("click", () => this.use());
      this.$("[data-confirm-back]").addEventListener("click", () => this.showConfirm(false));
      this.$("[data-confirm-replace]").addEventListener("click", () => this.write());
      this.$("[data-start-fresh]").addEventListener("click", () => this.startFresh());
      // Escape (native "cancel") and dialog.close() both end up here
      this.dialog.addEventListener("close", () => this.cleanUp());
      this.buildControls();

      document.documentElement.classList.add("wagtail-vega-builder-open");
      this.dialog.showModal();
      // Start loading the preview's libraries alongside the data
      loadLibraries(this.config).catch(() => {});
      this.load(true);
    }

    async load(first) {
      const dataset = this.datasets.find((d) => d.name === this.datasetName);
      this.setErrors([]);
      this.setStatus(`Loading “${dataset.name}”…`);
      this.$("[data-use]").disabled = true;
      let rows;
      try {
        rows = await loadRows(dataset, this.config);
        if (!Array.isArray(rows)) throw new Error(`Couldn't read “${dataset.name}”.`);
      } catch (e) {
        if (!this.dialog) return;
        this.setStatus("");
        this.setErrors([e.message]);
        return;
      }
      if (!this.dialog || dataset.name !== this.datasetName) return; // closed or switched meanwhile
      if (!rows.length) {
        this.setStatus("");
        this.setErrors([`“${dataset.name}” has no rows yet.`]);
        return;
      }
      this.rows = rows;
      this.columns = this.spec.describeColumns(rows);
      this.setStatus("");
      if (first) this.start();
      else this.afterDatasetChange();
    }

    start() {
      const { problem, state } = this.opened;
      if (problem) {
        this.$("[data-problem-text]").textContent = `The builder can't open the spec that's in the field: ${problem}.`;
        this.$("[data-problem]").hidden = false;
        this.setStatus("");
        this.setNotice("The builder can't open this spec.");
        this.$("[data-start-fresh]").focus();
        return;
      }
      if (state) {
        this.state = state;
        this.original = this.spec.toSpec(state, this.datasetName);
        this.setNotice(
          this.missingDataset
            ? `Opened the field's chart. It used the dataset “${this.missingDataset}”, which this chart doesn't have, so it now uses “${this.datasetName}”.`
            : "Opened the field's chart.",
        );
      } else {
        this.state = this.spec.initialState(this.columns);
        this.original = null;
        this.$("[data-suggestions]").open = true;
        this.setNotice("Started from a suggested chart. Change anything below.");
      }
      this.showBuilder();
    }

    startFresh() {
      this.state = this.spec.initialState(this.columns);
      this.original = null;
      this.$("[data-problem]").hidden = true;
      this.$("[data-suggestions]").open = true;
      this.setNotice("Started a new chart from a suggestion.");
      this.showBuilder();
    }

    showBuilder() {
      this.$("[data-controls]").hidden = false;
      this.$("[data-preview]").hidden = false;
      this.update();
      // Focus the first control, unless the editor has already moved on
      const active = document.activeElement;
      if (!active || active === document.body || active.matches("[data-cancel], [data-start-fresh], dialog")) {
        this.$("[data-prop=mark]").focus();
      }
    }

    async switchDataset(name) {
      this.datasetName = name;
      this.missingDataset = null;
      if (!this.state && !this.opened.problem) {
        this.load(true);
        return;
      }
      this.load(false);
    }

    afterDatasetChange() {
      if (!this.state) {
        // Still showing "can't open": nothing to adapt
        this.setStatus("");
        return;
      }
      const names = new Set(this.columns.map((c) => c.name));
      const missing = this.spec.specFields(this.state).filter((f) => !names.has(f));
      if (missing.length) {
        const fresh = this.spec.initialState(this.columns);
        this.state.mark = fresh.mark;
        this.state.arrangement = fresh.arrangement;
        this.state.channels = fresh.channels;
        this.setNotice(`“${this.datasetName}” doesn't have the fields the chart used, so it starts from a suggestion.`);
      } else {
        this.setNotice(`The chart now uses “${this.datasetName}”.`);
      }
      this.update();
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

    // -- Editing ----------------------------------------------------------------

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
            this.announce("Width set to automatic: charts split into rows or columns can't fill the page width.");
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
        const allowed = S.ARRANGEMENTS.find(([a]) => a === state.arrangement)[2];
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
      this.update();
    }

    swap() {
      const { channels } = this.state;
      [channels.x, channels.y] = [channels.y, channels.x];
      this.update();
      this.announce("Swapped the X and Y axes.");
    }

    useSuggestion(index) {
      const suggestion = this.suggestions[index];
      if (!suggestion) return;
      this.spec.applySuggestion(this.state, suggestion, this.columns);
      this.update();
      this.announce(`Chart set to “${suggestion.label}”.`);
    }

    announce(text) {
      this.setStatus(text);
    }

    // -- Showing the state --------------------------------------------------------

    update() {
      this.showConfirm(false);
      this.setErrors([]);
      this.sync();
      // The spec as it is now; the preview follows shortly
      this.$("[data-json]").textContent = JSON.stringify(this.spec.toSpec(this.state, this.datasetName).spec, null, 2);
      this.$("[data-use]").disabled = !this.spec.channelsFor(this.state.mark).some((c) => this.spec.hasField(this.state.channels[c]));
      clearTimeout(this.previewTimer);
      this.previewTimer = setTimeout(() => this.renderPreview(), PREVIEW_DELAY);
    }

    fieldOptions() {
      const S = this.spec;
      const options = [["", "None"], [S.COUNT, "Count of rows"]];
      for (const column of this.columns) {
        options.push([column.name, `${column.name} (${TYPE_NAMES[column.type]})`]);
      }
      const names = new Set(this.columns.map((c) => c.name));
      for (const field of S.specFields(this.state)) {
        if (!names.has(field)) options.push([field, `${field} (from the spec)`]);
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
        isCustom ? [...options, [CUSTOM, `Custom: ${keptText(value)}`.replace("Custom: None", "Custom: none")]] : options;

      // Suggestions
      this.suggestions = S.suggest(this.columns);
      const list = $c("[data-suggestion-list]");
      const labels = JSON.stringify(this.suggestions.map((s) => s.label));
      if (list.dataset.labels !== labels) {
        list.dataset.labels = labels;
        list.replaceChildren(
          ...this.suggestions.map((s, i) =>
            h("li", {}, h("button", { type: "button", className: "button button-small button-secondary", "data-suggestion": String(i), text: s.label })),
          ),
        );
      }
      $c("[data-suggestions]").hidden = !this.suggestions.length;

      // The chart
      const mark = $c("[data-prop=mark]");
      setValue(mark, state.mark);
      const stackable = state.mark === "bar" || state.mark === "area";
      show("arrangement", stackable);
      const arrangement = $c("[data-prop=arrangement]");
      const customStack = stackable && S.customArrangement(state);
      const measure = state.channels[S.measureChannel(state)];
      setOptions(
        arrangement,
        custom(
          S.ARRANGEMENTS.filter(([, , marks]) => marks.includes(state.mark)).map(([v, l]) => [v, l]),
          customStack,
          measure.extras.stack,
        ),
      );
      setValue(arrangement, customStack ? CUSTOM : state.arrangement);
      const hint = $c("[data-arrangement-hint]");
      const needsColor = stackable && state.arrangement !== "none" && !S.hasField(state.channels.color);
      hint.hidden = !needsColor;
      hint.textContent = needsColor ? `Choose a colour field to split the ${state.mark === "bar" ? "bars" : "areas"} into parts.` : "";
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

        setOptions(prop("type"), custom(S.TYPES, isCustom("type"), extras.type));
        setValue(prop("type"), isCustom("type") ? CUSTOM : ch.type || S.impliedType(ch));
        showIn("type", has && !ch.count);

        setOptions(prop("aggregate"), custom([["", "No (one mark per row)"], ...S.AGGREGATES], isCustom("aggregate"), extras.aggregate));
        setValue(prop("aggregate"), isCustom("aggregate") ? CUSTOM : ch.aggregate);
        showIn("aggregate", has && !ch.count);

        setOptions(prop("bin"), custom([["", "No"], ["bin", "Group into ranges (bins)"]], isCustom("bin"), extras.bin));
        setValue(prop("bin"), isCustom("bin") ? CUSTOM : ch.bin ? "bin" : "");
        showIn("bin", has && !ch.count && ((ch.type === "quantitative" && name !== "theta") || ch.bin || isCustom("bin")));

        setOptions(prop("timeUnit"), custom([["", "None (exact values)"], ...S.TIME_UNITS], isCustom("timeUnit"), extras.timeUnit));
        setValue(prop("timeUnit"), isCustom("timeUnit") ? CUSTOM : ch.timeUnit);
        const temporalish = ch.type === "temporal" || (ch.type === "ordinal" && column?.type === "temporal");
        showIn("timeUnit", has && !ch.count && (temporalish || Boolean(ch.timeUnit) || isCustom("timeUnit")));

        const sortOptions = [
          ["", "Default"],
          ["ascending", "Ascending (A to Z, low to high)"],
          ["descending", "Descending (Z to A, high to low)"],
          ["none", "Order in the data"],
        ];
        for (const other of S.SORT_CHANNELS) {
          if (other === name || !shown.has(other) || !S.hasField(state.channels[other])) continue;
          const label = S.CHANNELS[other].label.replace(/ \(.*\)$/, "");
          sortOptions.push([other, `By ${label}, ascending`], [`-${other}`, `By ${label}, descending`]);
        }
        if (ch.sort && !sortOptions.some(([v]) => v === ch.sort)) sortOptions.push([ch.sort, ch.sort]);
        setOptions(prop("sort"), custom(sortOptions, isCustom("sort"), extras.sort));
        setValue(prop("sort"), isCustom("sort") ? CUSTOM : ch.sort);
        showIn("sort", has && name !== "size" && name !== "theta");

        setValue(prop("title"), ch.title);
        prop("title").placeholder = isCustom("title") ? keptText(extras.title) : "Default: the field name";
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
            ["container", "Fill the page width", facets && state.width !== "container"],
            ["", "Automatic"],
            ["fixed", "Fixed"],
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
          ? [
              h("p", { text: heading }),
              h("ul", {}, paths.map((path) => h("li", {}, h("code", { text: path })))),
            ]
          : [];
      this.$("[data-kept]").replaceChildren(
        ...list("The builder doesn't edit these parts of the spec. They're kept as they are:", kept),
      );
      this.$("[data-dropped]").replaceChildren(
        ...list("Your changes remove these parts of the spec:", dropped),
      );
      this.$("[data-kept-section]").hidden = !kept.length && !dropped.length;
    }

    // -- Preview ------------------------------------------------------------------

    theme() {
      const { themes = {}, defaultTheme } = this.config;
      const chosen = this.themeField?.querySelector("select")?.value;
      return themes[chosen] || themes[defaultTheme] || null;
    }

    async renderPreview() {
      if (!this.dialog || !this.state) return;
      const token = ++this.previewToken;
      const { spec } = this.spec.toSpec(this.state, this.datasetName);
      const theme = this.theme();
      this.$("[data-scheme-picker]").hidden = !theme?.dark;
      const host = this.$("[data-chart]");
      const warnings = this.$("[data-warnings]");
      const show = (messages) => {
        const text = JSON.stringify(messages);
        if (warnings.dataset.text === text) return;
        warnings.dataset.text = text;
        warnings.replaceChildren(...messages.map((m) => h("li", { text: m })));
      };
      try {
        await loadLibraries(this.config);
      } catch (e) {
        show([`The preview isn't available: ${e.message}`]);
        return;
      }
      if (token !== this.previewToken || !this.dialog) return;

      const dark = Boolean(theme?.dark) && this.scheme === "dark";
      host.dataset.colorScheme = dark ? "dark" : "light";
      const internal = window.wagtailVega?._internal || {};
      let full = previewSpec(spec, this.rows, theme, dark);
      if (internal.resolveVars) full = internal.resolveVars(full, host, theme?.fallbacks || {});
      const messages = [];
      const logger = window.vega.logger(window.vega.Warn);
      logger.warn = (...args) => {
        messages.push(args.join(" "));
        return logger;
      };
      logger.error = (...args) => {
        messages.push(args.map(String).join(" "));
        return logger;
      };
      const options = {
        ...(this.config.embedOptions || {}),
        actions: false,
        renderer: "svg",
        defaultStyle: false,
        tooltip: { disableDefaultStyle: true },
        ast: true,
        expr: window.vegaInterpreter.expressionInterpreter,
        logger,
        loader: internal.makeLoader ? internal.makeLoader(this.config.allowedHosts) : undefined,
      };
      if (theme?.vega_theme) options.theme = theme.vega_theme;
      const target = h("div", { className: "wagtail-vega__target" });
      host.append(target);
      try {
        const result = await window.vegaEmbed(target, full, options);
        await result.view.runAsync();
        if (token !== this.previewToken || !this.dialog) {
          result.view.finalize();
          target.remove();
          return;
        }
        this.view?.finalize();
        this.view = result.view;
        for (const child of [...host.children]) if (child !== target) child.remove();
        show(messages.map((m) => `Note: ${m}`));
      } catch (e) {
        target.remove();
        if (token !== this.previewToken) return;
        show([`The preview can't be drawn yet: ${e.message}`, ...messages]);
      }
    }

    // -- Using the chart ------------------------------------------------------------

    async use() {
      if (!this.state) return;
      const { spec } = this.spec.toSpec(this.state, this.datasetName);
      if (this.previous && this.spec.sameSpec(spec, this.previous)) {
        this.result = null;
        this.unchanged = true;
        this.close();
        return;
      }
      const button = this.$("[data-use]");
      button.disabled = true;
      this.setErrors([]);
      this.setStatus("Checking the chart…");
      try {
        const errors = await checkSpec(spec, this.config);
        if (errors.length) {
          this.setStatus("");
          this.setErrors(["This chart can't be used as it is:", ...errors]);
          return;
        }
      } catch (e) {
        this.setStatus("");
        this.setErrors([e.message]);
        return;
      } finally {
        if (this.dialog) button.disabled = false;
      }
      if (!this.dialog) return; // closed while the spec was being checked
      this.setStatus("");
      this.result = spec;
      // An empty field (a new block's holds "null") needs no confirmation
      const current = this.textarea.value.trim();
      if (current && current !== "null") this.showConfirm(true);
      else this.write();
    }

    showConfirm(show) {
      if (!this.dialog) return;
      const confirm = this.$("[data-confirm]");
      if (confirm.hidden === !show) return;
      confirm.hidden = !show;
      this.$("[data-actions]").hidden = show;
      this.$("[data-messages]").hidden = show;
      this.$(show ? "[data-confirm-replace]" : "[data-use]").focus();
    }

    write() {
      if (!this.result) return;
      this.textarea.value = JSON.stringify(this.result, null, 2);
      // The contract with editors that enhance the textarea
      this.textarea.dispatchEvent(new Event("input", { bubbles: true }));
      this.written = true;
      this.close();
    }

    close() {
      if (this.dialog?.open) this.dialog.close();
      else this.cleanUp();
    }

    cleanUp() {
      if (!this.dialog) return;
      clearTimeout(this.previewTimer);
      this.view?.finalize();
      this.view = null;
      this.dialog.remove();
      this.dialog = null;
      document.documentElement.classList.remove("wagtail-vega-builder-open");
      this.trigger.focus();
      let note = "";
      if (this.written) note = "The chart is now in the spec field.";
      else if (this.unchanged) note = "The chart wasn't changed.";
      this.launcher.note(note);
    }
  }

  // -- The button on each spec field -----------------------------------------

  class ChartBuilderLauncher extends HTMLElement {
    /** The spec textarea this button belongs to: a sibling, named by data-for. */
    get textarea() {
      const name = this.dataset.for;
      if (!name || !this.parentElement) return null;
      return this.parentElement.querySelector(`:scope > textarea[name="${CSS.escape(name)}"]`);
    }

    connectedCallback() {
      // The widget renders the textarea first (Wagtail gives a widget's first
      // element the field's aria-describedby and required, which the code
      // editor copies), then this. Move above the textarea, and so above the
      // code editor, which inserts itself right after the textarea. Moving
      // reconnects the element, so this runs again; the check below stops it.
      const textarea = this.textarea;
      if (textarea && textarea.compareDocumentPosition(this) & Node.DOCUMENT_POSITION_FOLLOWING) {
        textarea.before(this);
        return;
      }
      if (this.button) return;
      this.button = this.querySelector("[data-builder-open]");
      this.noteEl = this.querySelector("[data-builder-note]");
      this.noteEl.id = `wagtail-vega-builder-note-${++uid}`;
      this.button.addEventListener("click", () => this.open());
      // StructBlock renders its fields one after another; look for the
      // datasets field once they're all there.
      setTimeout(() => this.refresh());
    }

    get config() {
      try {
        return JSON.parse(this.dataset.config || "{}");
      } catch {
        return {};
      }
    }

    refresh() {
      const { dataField } = chartContext(this);
      if (!dataField) {
        // e.g. a BaseChartBlock subclass whose data comes from code
        this.button.disabled = true;
        this.note("The chart builder works with datasets added in this form. This chart's data comes from code.");
      }
    }

    note(text) {
      this.noteEl.textContent = text;
      this.noteEl.hidden = !text;
      if (text) this.button.setAttribute("aria-describedby", this.noteEl.id);
      else this.button.removeAttribute("aria-describedby");
    }

    open() {
      const { textarea, dataField, themeField } = chartContext(this);
      if (!textarea || !dataField) return this.refresh();
      if (!admin.chartSpec) return this.note("The chart builder's scripts aren't loaded.");
      const datasets = readDatasets(dataField);
      if (!datasets.length) {
        this.note("Add data to this chart's datasets first, then build the chart from it.");
        return;
      }
      this.note("");
      new Session(this, textarea, datasets, themeField).open();
    }
  }

  if (!window.customElements.get("wagtail-vega-chart-builder")) {
    window.customElements.define("wagtail-vega-chart-builder", ChartBuilderLauncher);
  }

  // Internal helpers, exposed for tests. Not a public API.
  admin.chartBuilder = {
    _internal: { urlAllowed, formatFromUrl, deepMerge, problemMessages, previewSpec, adminScheme },
  };
})();
