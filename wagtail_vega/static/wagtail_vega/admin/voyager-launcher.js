/* wagtail-vega admin: "Build chart with Voyager".
 *
 * A button on each spec field opens Vega Voyager in a lightbox, loaded with
 * one of the chart's datasets (read from the unsaved form). "Use this chart"
 * converts Voyager's spec to Vega-Lite v6 that refers to the dataset by
 * name, checks it with the server (validate-spec, the endpoint the code
 * editor uses for live validation), and writes it to the spec textarea.
 *
 * Voyager runs in a sandboxed iframe (wagtail_vega/views.py), which talks
 * to this page with postMessage. Every message is an object
 * {channel: "wagtail-vega-voyager", type, ...}:
 *
 *   frame -> admin  ready                  Voyager has started
 *                   loaded {seeded, warning}  data (and spec, if seeded) loaded
 *                   spec {spec}            the current chart, or null
 *                   close                  Escape pressed inside the frame
 *                   error {message}
 *   admin -> frame  load {values, spec}    data rows, plus a spec to open
 *
 * The frame has an opaque origin, so messages from it arrive with origin
 * "null"; they are accepted only from that iframe's window. Messages to it
 * have to use targetOrigin "*", and are only sent once the frame has said
 * it's ready. The frame accepts messages only from its parent at this
 * page's origin, and sends only to that origin.
 *
 * Writing the result follows code-editor.js's contract: textarea.value is
 * set and a bubbling "input" event dispatched, which the code editor takes
 * as one undoable change. The button is rendered by the spec field's
 * CodeEditor widget (widgets.py) above the textarea; the editor inserts
 * itself after the textarea, so the two don't overlap.
 *
 * Needs data-format.js (loaded with the code editor) for pasted data.
 */
(() => {
  "use strict";

  const CHANNEL = "wagtail-vega-voyager";
  const VL_SCHEMA = "https://vega.github.io/schema/vega-lite/v6.json";
  // Element boundaries in Wagtail's StreamField / StructBlock markup
  const BOUNDARY = "[data-streamfield-child], [data-contentpath], [data-contentpath-disabled]";
  // Kept from the field's current spec when Voyager's chart replaces it
  const CARRY_OVER = ["title", "description", "width", "height", "autosize", "padding", "background"];
  // Encoding channels Voyager (Vega-Lite 2) understands
  const VOYAGER_CHANNELS = new Set([
    "x", "y", "x2", "y2", "color", "opacity", "size", "shape", "text", "tooltip", "detail",
    "row", "column",
  ]);
  const FIELD_TYPES = new Set(["quantitative", "nominal", "ordinal", "temporal"]);

  const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const clone = (v) => JSON.parse(JSON.stringify(v));

  function deepMerge(a, b) {
    const out = clone(a);
    for (const [k, v] of Object.entries(b)) {
      out[k] = isObject(v) && isObject(out[k]) ? deepMerge(out[k], v) : clone(v);
    }
    return out;
  }

  function isVegaLite(spec) {
    return isObject(spec) && typeof spec.$schema === "string" && spec.$schema.includes("/vega-lite/");
  }

  // -- Spec conversion ------------------------------------------------------

  /** The parts of a Vega-Lite spec that Voyager can open: a single view's
   * mark and field encodings. Returns null if there's nothing to open. */
  function toVoyagerSpec(spec) {
    if (!isVegaLite(spec) || !isObject(spec.encoding)) return null;
    const composite = ["layer", "concat", "hconcat", "vconcat", "facet", "repeat", "spec"];
    if (composite.some((key) => key in spec)) return null;
    const mark = isObject(spec.mark) ? spec.mark.type : spec.mark;
    if (typeof mark !== "string") return null;
    const encoding = {};
    for (const [channel, def] of Object.entries(spec.encoding)) {
      if (!VOYAGER_CHANNELS.has(channel) || !isObject(def)) continue;
      if (def.aggregate === "count") {
        encoding[channel] = { aggregate: "count", field: "*", type: "quantitative" };
        continue;
      }
      if (typeof def.field !== "string" || !FIELD_TYPES.has(def.type)) continue;
      const out = { field: def.field, type: def.type };
      if (typeof def.aggregate === "string") out.aggregate = def.aggregate;
      if (def.bin === true || isObject(def.bin)) out.bin = true;
      if (typeof def.timeUnit === "string") out.timeUnit = def.timeUnit;
      encoding[channel] = out;
    }
    return Object.keys(encoding).length ? { mark, encoding } : null;
  }

  /** Voyager's (Vega-Lite 2) spec as Vega-Lite v6 that loads ``datasetName``
   * by name. Presentation settings such as the title and width are kept
   * from ``previous``, the field's current spec. */
  function fromVoyagerSpec(voyagerSpec, datasetName, previous) {
    const spec = clone(voyagerSpec);
    for (const key of ["$schema", "data", "datasets"]) delete spec[key];
    if (isObject(spec.encoding)) {
      for (const def of Object.values(spec.encoding)) {
        if (!isObject(def)) continue;
        // Vega-Lite 2 wrote count as {"aggregate": "count", "field": "*"}
        if (def.aggregate === "count" && def.field === "*") delete def.field;
        for (const [key, value] of Object.entries(def)) {
          if (isObject(value) && Object.keys(value).length === 0) delete def[key];
        }
      }
    }
    const out = { $schema: VL_SCHEMA };
    const prev = isVegaLite(previous) ? previous : null;
    for (const key of CARRY_OVER) {
      if (prev && key in prev && !(key in spec)) out[key] = clone(prev[key]);
    }
    out.data = { name: datasetName };
    Object.assign(out, spec);
    if (prev && isObject(prev.config)) out.config = deepMerge(prev.config, spec.config || {});
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

  /** The spec field's chart: its datasets field (if any) and textarea. */
  function chartContext(launcher) {
    const textarea = launcher.textarea;
    const specWrapper = launcher.closest(BOUNDARY);
    const struct = specWrapper?.parentElement;
    const boundary = struct?.closest(BOUNDARY);
    let dataField = null;
    if (boundary) {
      dataField =
        [...boundary.querySelectorAll('[data-contentpath="data"]')].find(
          (el) => el.parentElement.closest(BOUNDARY) === boundary,
        ) || null;
    }
    return { textarea, dataField };
  }

  function isDeleted(el) {
    const child = el.closest("[data-streamfield-child]");
    return child?.querySelector(':scope > input[name$="-deleted"]')?.value === "1";
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

  function hasData(dataset) {
    if (dataset.source === "document") return Boolean(dataset.document);
    if (dataset.source === "url") return Boolean(dataset.url);
    return Boolean(dataset.paste.trim());
  }

  async function loadRows(dataset, config) {
    // data-format.js comes with the code editor (widgets.EDITOR_JS)
    const parseRows = window.wagtailVegaAdmin?.dataFormat?.parseRows;
    if (!parseRows) throw new Error("The data editor's scripts aren't loaded.");
    if (dataset.source === "document") {
      if (!dataset.document) throw new Error(`Choose a document for “${dataset.name}” first.`);
      const url = `${config.rowsUrl}?id=${encodeURIComponent(dataset.document)}`;
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || `Couldn't load the document (${response.status}).`);
      return body.rows;
    }
    if (dataset.source === "url") {
      if (!dataset.url) throw new Error(`Enter a URL for “${dataset.name}” first.`);
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

  // -- The lightbox -----------------------------------------------------------

  let uid = 0;

  function icon(name) {
    return `<svg class="icon icon-${name}" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
  }

  function buildDialog() {
    const id = `wagtail-vega-voyager-${++uid}`;
    const dialog = document.createElement("dialog");
    dialog.className = "wagtail-vega-voyager";
    dialog.setAttribute("aria-labelledby", `${id}-title`);
    dialog.setAttribute("aria-describedby", `${id}-status`);
    dialog.innerHTML = `
      <header class="wagtail-vega-voyager__header">
        <h2 class="wagtail-vega-voyager__title" id="${id}-title">Build a chart with Voyager</h2>
        <div class="wagtail-vega-voyager__dataset" data-dataset-picker hidden>
          <label for="${id}-dataset">Dataset</label>
          <select id="${id}-dataset" data-dataset></select>
        </div>
        <button type="button" class="wagtail-vega-voyager__close" data-cancel aria-label="Close without using the chart">${icon("cross")}</button>
      </header>
      <div class="wagtail-vega-voyager__body"></div>
      <footer class="wagtail-vega-voyager__footer">
        <div class="wagtail-vega-voyager__messages">
          <p class="wagtail-vega-voyager__status" id="${id}-status" role="status"><span data-notice></span> <span data-status></span></p>
          <ul class="wagtail-vega-voyager__errors" role="alert" data-errors></ul>
        </div>
        <div class="wagtail-vega-voyager__actions" data-actions>
          <button type="button" class="button button-secondary" data-cancel>Cancel</button>
          <button type="button" class="button" data-use disabled>Use this chart</button>
        </div>
        <div class="wagtail-vega-voyager__actions wagtail-vega-voyager__confirm" data-confirm hidden>
          <p id="${id}-confirm">This replaces the spec that's in the field now.</p>
          <button type="button" class="button button-secondary" data-confirm-back>Keep editing</button>
          <button type="button" class="button" data-confirm-replace aria-describedby="${id}-confirm">Replace spec</button>
        </div>
      </footer>`;
    document.body.append(dialog);
    return dialog;
  }

  /** One opening of the lightbox for one spec field. */
  class Session {
    constructor(launcher, trigger, textarea, datasets) {
      this.launcher = launcher;
      this.trigger = trigger;
      this.textarea = textarea;
      this.datasets = datasets;
      this.config = launcher.config;
      this.spec = null;
      this.ready = false;
      this.firstLoad = true;
      try {
        this.previous = JSON.parse(textarea.value);
      } catch {
        this.previous = null;
      }
      const wanted = this.previous?.data?.name;
      this.datasetName = datasets.some((d) => d.name === wanted) ? wanted : datasets[0].name;
      this.seed = toVoyagerSpec(this.previous);
      this.onMessage = this.onMessage.bind(this);
    }

    $(selector) {
      return this.dialog.querySelector(selector);
    }

    open() {
      this.dialog = buildDialog();
      const select = this.$("[data-dataset]");
      for (const dataset of this.datasets) select.add(new Option(dataset.name, dataset.name));
      select.value = this.datasetName;
      this.$("[data-dataset-picker]").hidden = this.datasets.length < 2;
      select.addEventListener("change", () => {
        this.datasetName = select.value;
        this.seed = null; // the field's spec was made for the other dataset
        this.firstLoad = false;
        this.sendData();
      });

      for (const button of this.dialog.querySelectorAll("[data-cancel]")) {
        button.addEventListener("click", () => this.close());
      }
      this.$("[data-use]").addEventListener("click", () => this.use());
      this.$("[data-confirm-back]").addEventListener("click", () => this.showConfirm(false));
      this.$("[data-confirm-replace]").addEventListener("click", () => this.write());
      // Escape (native "cancel") and dialog.close() both end up here
      this.dialog.addEventListener("close", () => this.cleanUp());

      window.addEventListener("message", this.onMessage);
      this.iframe = document.createElement("iframe");
      this.iframe.className = "wagtail-vega-voyager__frame";
      this.iframe.title = "Voyager chart builder";
      // No allow-same-origin: Voyager gets an opaque origin (see views.py)
      this.iframe.setAttribute("sandbox", "allow-scripts");
      this.iframe.src = this.config.frameUrl;
      this.$(".wagtail-vega-voyager__body").append(this.iframe);

      this.setStatus("Loading Voyager…");
      document.documentElement.classList.add("wagtail-vega-voyager-open");
      this.dialog.showModal();
    }

    setStatus(text) {
      this.$("[data-status]").textContent = text;
    }

    setNotice(text) {
      this.$("[data-notice]").textContent = text;
    }

    setErrors(messages) {
      const list = this.$("[data-errors]");
      list.replaceChildren(
        ...messages.map((m) => Object.assign(document.createElement("li"), { textContent: m })),
      );
    }

    post(type, payload) {
      // The frame's origin is opaque, so "*" is the only targetOrigin that
      // reaches it; it is only used after the frame has said it's ready.
      this.iframe.contentWindow.postMessage({ channel: CHANNEL, type, ...payload }, "*");
    }

    onMessage(event) {
      if (!this.iframe || event.source !== this.iframe.contentWindow) return;
      if (event.origin !== "null") return; // must be the sandboxed frame
      const data = event.data;
      if (!isObject(data) || data.channel !== CHANNEL) return;
      if (data.type === "ready") {
        this.ready = true;
        this.sendData();
      } else if (data.type === "loaded") {
        this.onLoaded(data);
      } else if (data.type === "spec") {
        this.spec = isObject(data.spec) ? data.spec : null;
        this.$("[data-use]").disabled = !this.spec;
        this.showConfirm(false);
        this.setErrors([]);
        this.setStatus(
          this.spec
            ? "“Use this chart” writes the chart above to the spec field."
            : "Drag fields onto the encoding shelves, or choose a related view, to make a chart.",
        );
      } else if (data.type === "close") {
        this.close();
      } else if (data.type === "error") {
        this.setErrors([`Voyager: ${String(data.message).slice(0, 300)}`]);
      }
    }

    async sendData() {
      if (!this.ready) return;
      const dataset = this.datasets.find((d) => d.name === this.datasetName);
      this.spec = null;
      this.$("[data-use]").disabled = true;
      this.setErrors([]);
      this.setNotice("");
      this.setStatus(`Loading “${dataset.name}”…`);
      let values;
      try {
        values = await loadRows(dataset, this.config);
      } catch (e) {
        this.setStatus("");
        this.setErrors([e.message]);
        return;
      }
      if (!this.dialog || dataset.name !== this.datasetName) return; // closed or switched meanwhile
      if (!values.length) {
        this.setStatus("");
        this.setErrors([`“${dataset.name}” has no rows yet.`]);
        return;
      }
      this.post("load", { values, spec: this.seed });
    }

    onLoaded({ seeded, warning }) {
      if (seeded) {
        this.setNotice("Opened the field's current chart.");
      } else if (this.firstLoad && this.textarea.value.trim()) {
        this.setNotice("Voyager can't open the field's current spec, so this starts from the data.");
      }
      if (warning) console.warn("wagtail-vega: Voyager couldn't open the spec:", warning);
    }

    async use() {
      if (!this.spec) return;
      const spec = fromVoyagerSpec(this.spec, this.datasetName, this.previous);
      const button = this.$("[data-use]");
      button.disabled = true;
      this.setErrors([]);
      try {
        const errors = await checkSpec(spec, this.config);
        if (errors.length) {
          this.setErrors(["This chart can't be used as it is:", ...errors]);
          return;
        }
      } catch (e) {
        this.setErrors([e.message]);
        return;
      } finally {
        if (this.dialog) button.disabled = !this.spec;
      }
      if (!this.dialog) return; // closed while the spec was being checked
      this.result = spec;
      const current = this.textarea.value.trim();
      if (current && current !== JSON.stringify(spec, null, 2)) {
        this.showConfirm(true);
      } else {
        this.write();
      }
    }

    showConfirm(show) {
      if (!this.dialog) return;
      const confirm = this.$("[data-confirm]");
      if (confirm.hidden === !show) return;
      confirm.hidden = !show;
      this.$("[data-actions]").hidden = show;
      this.$(".wagtail-vega-voyager__messages").hidden = show;
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
      window.removeEventListener("message", this.onMessage);
      this.dialog.remove();
      this.dialog = null;
      this.iframe = null;
      document.documentElement.classList.remove("wagtail-vega-voyager-open");
      this.trigger.focus();
      this.launcher.note(this.written ? "The chart from Voyager is now in the spec field." : "");
    }
  }

  // -- The button on each spec field -----------------------------------------

  class VoyagerLauncher extends HTMLElement {
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
      this.button = this.querySelector("[data-voyager-open]");
      this.noteEl = this.querySelector("[data-voyager-note]");
      this.noteEl.id = `wagtail-vega-voyager-note-${++uid}`;
      this.button.addEventListener("click", () => this.open());
      // StructBlock renders its fields one after another; look for the
      // datasets field once they're all there.
      setTimeout(() => this.refresh());
    }

    get config() {
      let allowedHosts = [];
      try {
        allowedHosts = JSON.parse(this.dataset.allowedHosts || "[]");
      } catch {
        allowedHosts = [];
      }
      return {
        frameUrl: this.dataset.frameUrl,
        rowsUrl: this.dataset.rowsUrl,
        validateUrl: this.dataset.validateUrl,
        allowedHosts,
      };
    }

    refresh() {
      const { dataField } = chartContext(this);
      if (!dataField) {
        // e.g. a BaseChartBlock subclass whose data comes from code
        this.button.disabled = true;
        this.note("Voyager works with datasets added in this form. This chart's data comes from code.");
      }
    }

    note(text) {
      this.noteEl.textContent = text;
      this.noteEl.hidden = !text;
      if (text) this.button.setAttribute("aria-describedby", this.noteEl.id);
      else this.button.removeAttribute("aria-describedby");
    }

    open() {
      const { textarea, dataField } = chartContext(this);
      if (!textarea || !dataField) return this.refresh();
      const datasets = readDatasets(dataField);
      if (!datasets.length) {
        this.note("Add data to this chart's datasets first, then build the chart from it.");
        return;
      }
      this.note("");
      new Session(this, this.button, textarea, datasets).open();
    }
  }

  if (!window.customElements.get("wagtail-vega-voyager")) {
    window.customElements.define("wagtail-vega-voyager", VoyagerLauncher);
  }

  // Internal helpers, exposed for tests. Not a public API.
  window.wagtailVegaVoyager = {
    _internal: { toVoyagerSpec, fromVoyagerSpec, urlAllowed, formatFromUrl, deepMerge, problemMessages },
  };
})();
