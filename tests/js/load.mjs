// Load a browser script into an isolated context with stubbed globals.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const STATIC = fileURLToPath(new URL("../../wagtail_vega/static/wagtail_vega/", import.meta.url));

/** Run one or more scripts (in order) in a fresh context. */
export function loadScript(paths, globals = {}) {
  const window = { ...globals };
  window.window = window;
  window.globalThis = window;
  const context = vm.createContext(window);
  for (const path of [paths].flat()) {
    vm.runInContext(readFileSync(STATIC + path, "utf8"), context, { filename: path });
  }
  return window;
}

export const registeredFormats = {};

export function loadFrontend(extra = {}) {
  const defined = {};
  const loader = {
    sanitize: async (uri) => ({ href: uri }),
  };
  return loadScript("wagtail-vega.js", {
    vegaEmbed: async () => ({ view: { finalize() {} } }),
    vega: {
      loader: () => ({ ...loader }),
      formats: (name, reader) => { registeredFormats[name] = reader; },
      Warn: 2,
      logger: () => ({ warned: [], warn(...args) { this.warned.push(args); return this; } }),
    },
    customElements: { get: (n) => defined[n], define: (n, c) => { defined[n] = c; } },
    HTMLElement: class {},
    CustomEvent: class {},
    Event: class {},
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    document: { addEventListener() {}, baseURI: "https://site.test/page/", querySelectorAll: () => [] },
    location: { origin: "https://site.test" },
    URL,
    getComputedStyle: () => ({ getPropertyValue: () => "" }),
    structuredClone,
    console,
    ...extra,
  });
}

const ADMIN_HELPERS = ["admin/json-source.js", "admin/data-format.js"];

function adminGlobals(registered, extra = {}) {
  return {
    wagtailStreamField: {
      blocks: { StructBlockDefinition: class {}, FieldBlockDefinition: class {} },
    },
    telepath: {
      constructors: { "wagtail.widgets.Widget": class {} },
      register: (name, cls) => {
        registered[name] = cls;
      },
    },
    document: {},
    ...extra,
  };
}

/** The dataset block and the helpers it needs. */
export function loadAdmin() {
  const registered = {};
  const window = loadScript([...ADMIN_HELPERS, "admin/dataset-block.js"], adminGlobals(registered));
  return { window, registered };
}

/** The code editor's helpers (CodeMirror itself isn't loaded). */
export function loadCodeEditor() {
  const registered = {};
  const window = loadScript([...ADMIN_HELPERS, "admin/code-editor.js"], adminGlobals(registered));
  return { window, registered };
}

/** The chart builder's model (chart-spec.js) and the helpers it needs. */
export function loadChartSpec() {
  return loadScript([...ADMIN_HELPERS, "admin/chart-spec.js"], { document: {} });
}

/** The chart builder: its model and the lightbox's script. */
export function loadChartBuilder() {
  const defined = {};
  return loadScript([...ADMIN_HELPERS, "admin/chart-spec.js", "admin/chart-builder.js"], {
    customElements: { get: (n) => defined[n], define: (n, c) => { defined[n] = c; } },
    HTMLElement: class {},
    Event: class {},
    URL,
    document: { baseURI: "https://site.test/admin/pages/1/edit/", documentElement: { classList: { contains: () => false } } },
    console,
  });
}

// Values created inside a vm context have that context's prototypes, which
// deepStrictEqual treats as different. Round-trip through JSON to compare.
export const plain = (value) => JSON.parse(JSON.stringify(value));

/** The chart block's admin script (labels and the dataset name check). */
export function loadChartBlock() {
  const registered = {};
  const window = loadScript("admin/chart-block.js", adminGlobals(registered, { URL }));
  return { window, registered };
}
