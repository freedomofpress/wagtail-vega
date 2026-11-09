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
 */
(() => {
  "use strict";

  if (!window.vegaEmbed || customElements.get("wagtail-vega-chart")) return;

  const VAR_RE = /var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*?)\s*)?\)/g;
  const darkQuery = window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

  function resolveVars(value, el, fallbacks) {
    if (Array.isArray(value)) return value.map((v) => resolveVars(v, el, fallbacks));
    if (value && typeof value === "object") {
      const out = {};
      for (const [k, v] of Object.entries(value)) out[k] = resolveVars(v, el, fallbacks);
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

  // A loader that refuses non-allowlisted hosts. The server already rejects
  // literal URLs on save; this also covers URLs built from signals at runtime.
  function makeLoader(allowedHosts) {
    const loader = vega.loader();
    const sanitize = loader.sanitize;
    loader.sanitize = async function (uri, options) {
      const result = await sanitize.call(this, uri, options);
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

  let cspFormatsInstalled = false;
  function installCspSafeFormats() {
    if (cspFormatsInstalled) return;
    vega.formats("csv", dsvReader(","));
    vega.formats("tsv", dsvReader("\t"));
    vega.formats("dsv", dsvReader(null));
    cspFormatsInstalled = true;
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
      const spec = structuredClone(p.spec);
      if (p.darkConfig && this.colorScheme === "dark") spec.config = p.darkConfig;
      if (spec.config) spec.config = resolveVars(spec.config, this, p.fallbacks || {});

      const options = { ...p.embed, loader: makeLoader(p.allowedHosts || []) };
      if (p.cspSafe) {
        installCspSafeFormats();
        options.ast = true;
        options.expr = window.vegaInterpreter.expressionInterpreter;
      }

      const target = document.createElement("div");
      target.className = "wagtail-vega__target";
      this.append(target);
      try {
        const result = await vegaEmbed(target, spec, options);
        this.view?.finalize();
        this.view = result.view;
        // Remove the SSR SVG / noscript / previous render
        for (const child of [...this.children]) if (child !== target) child.remove();
        this.classList.remove("has-error");
        this.classList.add("is-rendered");
        this.dispatchEvent(
          new CustomEvent("wagtail-vega:rendered", { bubbles: true, detail: result })
        );
      } catch (error) {
        target.remove();
        this.classList.add("has-error");
        console.error("wagtail-vega:", error);
      }
    }
  }

  customElements.define("wagtail-vega-chart", WagtailVegaChart);

  document.addEventListener("wagtail-vega:refresh", () => {
    for (const el of document.querySelectorAll("wagtail-vega-chart")) el.refresh();
  });
})();
