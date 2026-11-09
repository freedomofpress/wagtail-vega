// Load a browser script into an isolated context with stubbed globals.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const STATIC = fileURLToPath(new URL("../../wagtail_vega/static/wagtail_vega/", import.meta.url));

export function loadScript(path, globals = {}) {
  const window = { ...globals };
  window.window = window;
  window.globalThis = window;
  const context = vm.createContext(window);
  vm.runInContext(readFileSync(STATIC + path, "utf8"), context, { filename: path });
  return window;
}

export function loadFrontend(extra = {}) {
  const defined = {};
  const loader = {
    sanitize: async (uri) => ({ href: uri }),
  };
  return loadScript("wagtail-vega.js", {
    vegaEmbed: async () => ({ view: { finalize() {} } }),
    vega: { loader: () => ({ ...loader }), formats() {} },
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

export function loadAdmin() {
  const registered = {};
  const window = loadScript("admin/dataset-block.js", {
    wagtailStreamField: { blocks: { StructBlockDefinition: class {} } },
    telepath: { register: (name, cls) => { registered[name] = cls; } },
    document: {},
  });
  return { window, registered };
}

// Values created inside a vm context have that context's prototypes, which
// deepStrictEqual treats as different. Round-trip through JSON to compare.
export const plain = (value) => JSON.parse(JSON.stringify(value));
