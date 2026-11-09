/* wagtail-vega: renders <wagtail-vega-chart> elements with vega-embed.
 *
 * Each element points (data-payload) at a JSON script tag containing:
 *   spec        the final spec (data and light theme config already applied)
 *   darkConfig  config to use when the colour scheme is dark (or null)
 *   embed       vega-embed options
 *   fallbacks   values for var(--token) strings missing from the page CSS
 *   allowedHosts / cspSafe  security settings mirrored from the server
 *
 * Colour scheme: the nearest [data-color-scheme="light|dark"] ancestor wins,
 * otherwise prefers-color-scheme. After changing a site-level toggle, dispatch
 * `document.dispatchEvent(new Event("wagtail-vega:refresh"))`.
 *
 * Events (bubbling, on the <wagtail-vega-chart> element):
 *   wagtail-vega:rendered  detail: the vega-embed result
 *   wagtail-vega:error     detail: {error} — the spec failed, or data didn't load
 *
 * While it renders, the element has aria-busy="true". If it fails, it gets
 * the has-error class and a <p class="wagtail-vega__error"> with the text of
 * its data-error-message attribute (set by the chart template, translated).
 */
(() => {
  "use strict";

  if (!window.vegaEmbed || customElements.get("wagtail-vega-chart")) return;

  const VAR_RE = /var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*?)\s*)?\)/g;
  const darkQuery = window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

  // var(--token) is resolved anywhere in the spec except inside data, the
  // same rule as the server (wagtail_vega.themes.resolve_css_vars).
  const DATA_KEYS = new Set(["data", "datasets", "values"]);

  function resolveVars(value, el, fallbacks) {
    if (Array.isArray(value)) return value.map((v) => resolveVars(v, el, fallbacks));
    if (value && typeof value === "object") {
      const out = {};
      for (const [k, v] of Object.entries(value)) {
        out[k] = DATA_KEYS.has(k) ? v : resolveVars(v, el, fallbacks);
      }
      return out;
    }
    if (typeof value === "string" && value.includes("var(")) {
      const styles = getComputedStyle(el);
      return value.replace(VAR_RE, (match, name, fallback) => {
        const css = styles.getPropertyValue(name).trim();
        return css || fallbacks[name] || fallback || match;
      });
    }
    return value;
  }

  function hostAllowed(url, allowedHosts) {
    if (url.origin === window.location.origin) return true;
    if (url.protocol !== "http:" && url.protocol !== "https:") return false;
    const host = url.hostname.toLowerCase();
    return allowedHosts.some((pattern) => {
      pattern = pattern.toLowerCase();
      if (pattern === "*" || pattern === host) return true;
      return (
        pattern.startsWith("*.") &&
        (host === pattern.slice(2) || host.endsWith(pattern.slice(1)))
      );
    });
  }

  // A loader that refuses to fetch from non-allowlisted hosts. The server
  // already rejects literal URLs on save; this also covers URLs built from
  // signals at runtime. Hyperlinks (context "href") aren't fetched, so they
  // only get Vega's own sanitising (which blocks javascript: URLs).
  function makeLoader(allowedHosts) {
    const loader = vega.loader();
    const sanitize = loader.sanitize;
    loader.sanitize = async function (uri, options) {
      const result = await sanitize.call(this, uri, options);
      if (options?.context === "href") return result;
      const url = new URL(result.href, document.baseURI);
      if (!hostAllowed(url, allowedHosts)) {
        throw new Error(`wagtail-vega: loading ${url.href} is not allowed`);
      }
      return result;
    };
    return loader;
  }

  // Vega's built-in CSV/TSV readers use d3-dsv, which compiles row objects
  // with `new Function` and so fails without 'unsafe-eval'. In CSP-safe
  // mode, swap in an eval-free RFC 4180 parser.
  function parseDelimited(text, delimiter) {
    const rows = [];
    let row = [];
    let field = "";
    let quoted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; }
          else quoted = false;
        } else field += c;
      } else if (c === '"') quoted = true;
      else if (c === delimiter) { row.push(field); field = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(field); rows.push(row); row = []; field = "";
      } else field += c;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    return rows;
  }

  function dsvReader(fixedDelimiter) {
    const reader = (data, format = {}) => {
      const rows = parseDelimited(String(data), fixedDelimiter || format.delimiter || ",");
      const header = format.header || rows.shift() || [];
      return rows.map((cells) => {
        const obj = {};
        header.forEach((name, i) => { obj[name] = cells[i] ?? ""; });
        return obj;
      });
    };
    reader.responseType = "text";
    return reader;
  }

  // The eval-free readers are registered under private names, and our specs
  // are rewritten to use them, so other Vega charts on the page keep Vega's
  // own readers.
  const CSP_FORMATS = { csv: "wagtail-vega-csv", tsv: "wagtail-vega-tsv", dsv: "wagtail-vega-dsv" };
  let cspFormatsInstalled = false;
  function installCspSafeFormats() {
    if (cspFormatsInstalled) return;
    vega.formats(CSP_FORMATS.csv, dsvReader(","));
    vega.formats(CSP_FORMATS.tsv, dsvReader("\t"));
    vega.formats(CSP_FORMATS.dsv, dsvReader(null));
    cspFormatsInstalled = true;
  }

  function urlExtension(url) {
    const match = /\.([a-z]+)(?:[?#].*)?$/i.exec(url);
    return match ? match[1].toLowerCase() : null;
  }

  // Point delimited-text data at the CSP-safe readers. Returns a new spec.
  function useCspSafeFormats(node) {
    if (Array.isArray(node)) return node.map(useCspSafeFormats);
    if (!node || typeof node !== "object") return node;
    const out = {};
    for (const [k, v] of Object.entries(node)) out[k] = useCspSafeFormats(v);
    const type = out.format?.type ?? (typeof out.url === "string" ? urlExtension(out.url) : null);
    if ((out.format || typeof out.url === "string") && CSP_FORMATS[type]) {
      out.format = { ...out.format, type: CSP_FORMATS[type] };
    }
    return out;
  }

  // Vega reports data that fails to load or parse as log warnings, after
  // vegaEmbed() has resolved. Catch them so the chart can report an error.
  const DATA_ERROR_RE = /^(Loading failed|Data ingestion failed)/;
  function makeLogger(onDataError) {
    const logger = vega.logger(vega.Warn);
    const warn = logger.warn;
    logger.warn = function (...args) {
      if (DATA_ERROR_RE.test(String(args[0]))) onDataError(args);
      return warn.apply(this, args);
    };
    return logger;
  }

  class WagtailVegaChart extends HTMLElement {
    connectedCallback() {
      if (this.payload) return;
      const script = document.getElementById(this.dataset.payload);
      if (!script) return;
      this.payload = JSON.parse(script.textContent);
      this.onSchemeChange = () => this.refresh();
      darkQuery?.addEventListener("change", this.onSchemeChange);
      this.refresh();
    }

    disconnectedCallback() {
      darkQuery?.removeEventListener("change", this.onSchemeChange);
      this.view?.finalize();
      this.view = null;
      this.payload = null;
    }

    get colorScheme() {
      const forced = this.closest("[data-color-scheme]")?.dataset.colorScheme;
      if (forced === "light" || forced === "dark") return forced;
      return darkQuery?.matches ? "dark" : "light";
    }

    async refresh() {
      const p = this.payload;
      if (!p) return;
      let spec = structuredClone(p.spec);
      if (p.darkConfig && this.colorScheme === "dark") spec.config = p.darkConfig;
      spec = resolveVars(spec, this, p.fallbacks || {});

      const dataErrors = [];
      const options = {
        ...p.embed,
        loader: makeLoader(p.allowedHosts || []),
        logger: makeLogger((args) => dataErrors.push(args.join(" "))),
      };
      if (p.cspSafe) {
        installCspSafeFormats();
        spec = useCspSafeFormats(spec);
        options.ast = true;
        options.expr = window.vegaInterpreter.expressionInterpreter;
      }

      const target = document.createElement("div");
      target.className = "wagtail-vega__target";
      this.append(target);
      this.setAttribute("aria-busy", "true");
      let embedded = false;
      try {
        const result = await vegaEmbed(target, spec, options);
        embedded = true;
        // Wait for data to load, so loading errors are known before we
        // report success.
        await result.view.runAsync();
        this.view?.finalize();
        this.view = result.view;
        // Remove the SSR SVG / noscript / previous render
        for (const child of [...this.children]) if (child !== target) child.remove();
        if (dataErrors.length) throw new Error(dataErrors.join("; "));
        this.classList.remove("has-error");
        this.classList.add("is-rendered");
        this.dispatchEvent(
          new CustomEvent("wagtail-vega:rendered", { bubbles: true, detail: result })
        );
      } catch (error) {
        // A data error still leaves a drawn (if empty) chart; a spec error doesn't
        if (!embedded) target.remove();
        this.classList.remove("is-rendered");
        this.classList.add("has-error");
        this.showError();
        console.error("wagtail-vega:", error);
        this.dispatchEvent(
          new CustomEvent("wagtail-vega:error", { bubbles: true, detail: { error } })
        );
      } finally {
        this.removeAttribute("aria-busy");
      }
    }

    /** Tell readers the chart failed, unless a server-rendered SVG of it is
     * still showing. The message goes when the chart next renders. */
    showError() {
      const children = [...this.children];
      if (children.some((el) => el.classList.contains("wagtail-vega__ssr"))) return;
      if (children.some((el) => el.classList.contains("wagtail-vega__error"))) return;
      const message = document.createElement("p");
      message.className = "wagtail-vega__error";
      message.textContent = this.dataset.errorMessage || "Sorry, this chart couldn't be displayed.";
      this.append(message);
    }
  }

  customElements.define("wagtail-vega-chart", WagtailVegaChart);

  // Internal helpers, exposed for tests. Not a public API.
  window.wagtailVega = {
    ...window.wagtailVega,
    _internal: {
      resolveVars,
      hostAllowed,
      makeLoader,
      makeLogger,
      parseDelimited,
      dsvReader,
      useCspSafeFormats,
      installCspSafeFormats,
    },
  };

  document.addEventListener("wagtail-vega:refresh", () => {
    for (const el of document.querySelectorAll("wagtail-vega-chart")) el.refresh();
  });
})();
