// The chart editor's helpers: data loading rules, and how the preview fills
// in data and applies themes. The field and the editor are tested in the
// browser (tests/e2e/test_chart_builder.py).
import assert from "node:assert/strict";
import { test } from "node:test";
import { checkbox, control, customDataset, radio, select, textarea, wrapper } from "./fake-dom.mjs";
import { loadChartBuilder, plain } from "./load.mjs";

const window = loadChartBuilder();
const { urlAllowed, formatFromUrl, deepMerge, previewSpec, sampleRows, t } =
  window.wagtailVegaAdmin.chartBuilder._internal;

test("defines the button element once", () => {
  assert.equal(typeof window.customElements.get("wagtail-vega-chart-builder"), "function");
});

// Mirrors wagtail_vega.spec.host_allowed (see tests/test_spec.py)
test("urlAllowed", () => {
  const base = "https://site.test/admin/pages/1/edit/";
  const allowed = ["data.org", "*.example.org"];
  const check = (url) => urlAllowed(url, allowed, base);
  assert.equal(check("/media/x.csv"), true);
  assert.equal(check("media/x.csv"), true);
  assert.equal(check("https://site.test/media/x.csv"), true); // same origin
  assert.equal(check("https://data.org/x.csv"), true);
  assert.equal(check("http://data.org/x.csv"), true);
  assert.equal(check("https://DATA.org/x.csv"), true);
  assert.equal(check("https://a.example.org/x.csv"), true);
  assert.equal(check("https://example.org/x.csv"), true);
  assert.equal(check("https://example.org.evil.org/x.csv"), false);
  assert.equal(check("https://evil.org/x.csv"), false);
  // Scheme-relative URLs are fetched with the page's scheme, so a host on
  // the allowlist is fine (as on the server, since #17)
  assert.equal(check("//data.org/x.csv"), true);
  assert.equal(check("//evil.example/x"), false);
  // Parsed the way the browser will fetch them (spec.normalize_url)
  assert.equal(check("/\\evil.example/x"), false); // backslash: //evil.example
  assert.equal(check(" //evil.example/x"), false); // leading space stripped
  assert.equal(check("\t/\\data.org/x"), true);
  assert.equal(check("\u0000//evil.example/x"), false); // control character stripped
  assert.equal(check("/\\site.test/x"), true); // this site
  assert.equal(check("javascript://data.org/%0aalert(1)"), false);
  assert.equal(check("/\\evil.org/x.csv"), false); // browsers read this as //evil.org
  assert.equal(check("data:text/csv,a"), false);
  assert.equal(check("javascript:alert(1)"), false);
  assert.equal(check("ftp://data.org/x.csv"), false);
  assert.equal(check(""), false);
  assert.equal(urlAllowed("https://anything.test/x", ["*"], base), true);
  assert.equal(urlAllowed("https://data.org/x", [], base), false);
});

test("formatFromUrl", () => {
  assert.equal(formatFromUrl(new URL("https://x.test/a.CSV")), "csv");
  assert.equal(formatFromUrl(new URL("https://x.test/a.tsv?x=1")), "tsv");
  assert.equal(formatFromUrl(new URL("https://x.test/a.json")), "json");
  assert.equal(formatFromUrl(new URL("https://x.test/api/data")), "json"); // Vega's default
});

// Mirrors wagtail_vega.spec.deep_merge
test("deepMerge: later arguments win, objects merge, others are replaced", () => {
  const a = { axis: { grid: true, labelColor: "#333" }, range: { category: ["a", "b"] }, font: "Georgia" };
  const b = { axis: { labelColor: "#ddd" }, range: { category: ["c"] } };
  assert.deepEqual(plain(deepMerge(a, null, b, undefined, { font: null })), {
    axis: { grid: true, labelColor: "#ddd" },
    range: { category: ["c"] },
    font: null,
  });
  assert.deepEqual(plain(a.axis), { grid: true, labelColor: "#333" }); // not modified
});

test("previewSpec fills in the data and applies the theme like the page does", () => {
  const spec = {
    $schema: "https://vega.github.io/schema/vega-lite/v6.json",
    data: { name: "source" },
    mark: "bar",
    config: { axis: { grid: false } },
  };
  const theme = {
    config: { axis: { grid: true, labelColor: "#333" }, background: "var(--chart-bg, white)" },
    dark: { axis: { labelColor: "#ddd" } },
  };
  const rows = [{ a: 1 }];
  const light = previewSpec(spec, { source: rows, other: [] }, theme, false);
  assert.deepEqual(plain(light.datasets), { source: rows, other: [] });
  assert.deepEqual(plain(light.data), { name: "source" });
  // Theme, then the spec's own config
  assert.deepEqual(plain(light.config), {
    axis: { grid: false, labelColor: "#333" },
    background: "var(--chart-bg, white)",
  });
  const dark = previewSpec(spec, { source: rows }, theme, true);
  assert.deepEqual(plain(dark.config.axis), { grid: false, labelColor: "#ddd" });
  // No theme: the spec as it is, plus data
  const plainSpec = previewSpec({ ...spec, config: undefined }, { source: rows }, null, false);
  assert.equal("config" in plainSpec, false);
  assert.equal("datasets" in spec, false); // not modified
  // The spec's own inline datasets win
  const own = previewSpec({ ...spec, datasets: { source: [{ a: 2 }] } }, { source: rows }, null, false);
  assert.deepEqual(plain(own.datasets), { source: [{ a: 2 }] });
});

test("previewSpec fills in a Vega spec's named data", () => {
  const spec = {
    $schema: "https://vega.github.io/schema/vega/v6.json",
    data: [{ name: "source" }, { name: "derived", source: "source" }, { name: "own", values: [1] }, { name: "missing" }],
  };
  const out = previewSpec(spec, { source: [{ a: 1 }], own: [{ b: 2 }] }, null, false);
  assert.deepEqual(plain(out.data), [
    { name: "source", values: [{ a: 1 }] },
    { name: "derived", source: "source" },
    { name: "own", values: [1] },
    { name: "missing" },
  ]);
  assert.equal("datasets" in out, false);
});

test("sampleRows keeps the first rows of large datasets, and says which", () => {
  const big = Array.from({ length: 12 }, (_, i) => ({ i }));
  const { rows, sampled } = sampleRows({ big, small: [{ i: 0 }] }, 10);
  assert.equal(rows.big.length, 10);
  assert.deepEqual(plain(rows.big[9]), { i: 9 });
  assert.equal(rows.small.length, 1);
  assert.deepEqual(plain(sampled), [{ name: "big", shown: 10, total: 12 }]);
});

// -- Custom dataset sources (#34) ---------------------------------------------

const { hasData, readDataset, loadRows } = window.wagtailVegaAdmin.chartBuilder._internal;
const { sources } = window.wagtailVegaAdmin;
const config = { rowsUrl: "/admin/wagtail-vega/document-rows/", allowedHosts: [] };

function stubFetch(status, body) {
  const calls = [];
  window.fetch = async (url, options) => {
    calls.push({ url: String(url), options });
    return { ok: status < 400, status, json: async () => body };
  };
  return calls;
}

const donations = (props = {}) =>
  customDataset({
    name: "donations",
    source: "donations",
    fields: {
      year: [select(["", "2025", "2026"], ["2026"])],
      group_by: [checkbox("quarter", true), checkbox("month", true)],
    },
    sourceFields: { donations: ["year", "group_by"] },
    rowsUrls: { donations: "/admin/donation-rows/" },
    ...props,
  });

test("fieldValues reads inputs, selects, checkboxes, radios and textareas", () => {
  assert.deepEqual(plain(sources.fieldValues(wrapper([control({ value: "x" })]))), ["x"]);
  assert.deepEqual(plain(sources.fieldValues(wrapper([textarea("t")]))), ["t"]);
  assert.deepEqual(plain(sources.fieldValues(wrapper([select(["a", "b", "c"], ["a", "c"], true)]))), ["a", "c"]);
  assert.deepEqual(plain(sources.fieldValues(wrapper([checkbox("a", true), checkbox("b"), checkbox("c", true)]))), ["a", "c"]);
  assert.deepEqual(plain(sources.fieldValues(wrapper([radio("a"), radio("b", true)]))), ["b"]);
  // Unnamed, disabled and button-like controls aren't values
  const skipped = [control({ name: "", value: "x" }), control({ disabled: true, value: "y" }), control({ type: "button", value: "z" })];
  assert.deepEqual(plain(sources.fieldValues(wrapper(skipped))), []);
  assert.deepEqual(plain(sources.fieldValues(null)), []);
});

test("rowsRequestUrl sends the fields as query parameters, on this site only", () => {
  const url = sources.rowsRequestUrl("/admin/rows/?v=1", { year: ["2026"], group_by: ["quarter", "month"], empty: [] });
  assert.equal(url.href, "https://site.test/admin/rows/?v=1&year=2026&group_by=quarter&group_by=month");
  assert.throws(() => sources.rowsRequestUrl("https://evil.test/rows/", {}), /can't be loaded from/);
});

test("loaderFor: built-in, then rows URL, then the registry, else none", () => {
  const settings = { rowsUrls: { a: "/rows/a/", paste: "/never/" } };
  assert.equal(sources.loaderFor("paste", settings).kind, "builtIn");
  assert.deepEqual(plain(sources.loaderFor("a", settings)), { kind: "rowsUrl", url: "/rows/a/" });
  sources.registerSource("loader-test", { loadRows: () => [] });
  assert.equal(sources.loaderFor("loader-test", settings).kind, "registry");
  assert.equal(sources.loaderFor("other", settings).kind, null);
});

test("registerSource needs a name and loadRows()", () => {
  assert.equal(window.wagtailVegaAdmin.registerSource, sources.registerSource);
  assert.throws(() => sources.registerSource("", { loadRows() {} }), { name: "TypeError" });
  assert.throws(() => sources.registerSource("x", {}), { name: "TypeError" });
});

test("readDataset reads only the selected source's inputs", () => {
  const dataset = readDataset(donations());
  assert.deepEqual(plain(dataset), {
    name: "donations",
    source: "donations",
    label: "Donations",
    fields: { year: ["2026"], group_by: ["quarter", "month"] },
    loader: "rowsUrl",
    rowsUrl: "/admin/donation-rows/",
  });
  assert.equal("paste" in dataset, false); // never the paste field's text
  assert.ok(dataset.el); // for registered sources, but not in the cache key
  assert.equal(Object.keys(dataset).includes("el"), false);

  const pasted = readDataset(donations({ source: "paste" }));
  assert.deepEqual(plain(pasted), { name: "donations", source: "paste", paste: "a\n1" });
});

test("hasData for custom sources", () => {
  assert.equal(hasData(readDataset(donations())), true);
  const blank = donations({ fields: { year: [select(["", "2026"], [""])], group_by: [checkbox("quarter")] } });
  assert.equal(hasData(readDataset(blank)), false);
  // A source that can't be previewed is still listed (with a note)
  const other = customDataset({ source: "totals", sourceFields: { totals: [] } });
  assert.equal(hasData(readDataset(other)), true);
});

test("loadRows fetches a rows URL with the fields", async () => {
  const calls = stubFetch(200, { rows: [{ quarter: "Q1", total: 1.5 }] });
  const rows = await loadRows(readDataset(donations()), config);
  assert.deepEqual(plain(rows), [{ quarter: "Q1", total: 1.5 }]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://site.test/admin/donation-rows/?year=2026&group_by=quarter&group_by=month");
  assert.equal(calls[0].options.credentials, "same-origin");
});

test("loadRows shows a rows URL's error", async () => {
  stubFetch(400, { error: "There are no donations in 2025." });
  await assert.rejects(loadRows(readDataset(donations()), config), { message: "There are no donations in 2025." });
  stubFetch(500, null);
  await assert.rejects(loadRows(readDataset(donations()), config), { message: "Couldn't load the data (500)." });
});

test("loadRows uses a registered source", async () => {
  let seen = null;
  sources.registerSource("sample", {
    hasData: (el) => sources.readFields(el, ["points"]).points[0] !== "0",
    loadRows: async (el, cfg) => {
      seen = { el, cfg };
      return [{ x: 1 }];
    },
  });
  const el = customDataset({
    source: "sample",
    fields: { points: [control({ name: "points", value: "3" })] },
    sourceFields: { sample: ["points"] },
  });
  const dataset = readDataset(el);
  assert.equal(dataset.loader, "registry");
  assert.deepEqual(plain(dataset.fields), { points: ["3"] });
  assert.equal(hasData(dataset), true);
  assert.deepEqual(plain(await loadRows(dataset, config)), [{ x: 1 }]);
  assert.equal(seen.el, el);
  assert.equal(seen.cfg, config);

  const none = customDataset({
    source: "sample",
    fields: { points: [control({ name: "points", value: "0" })] },
    sourceFields: { sample: ["points"] },
  });
  assert.equal(hasData(readDataset(none)), false);
});

test("loadRows can't preview a source with neither, and doesn't read the paste field", async () => {
  const calls = stubFetch(200, { rows: [] });
  const dataset = readDataset(customDataset({ name: "totals", source: "totals", sourceFields: { totals: [] } }));
  assert.equal(dataset.loader, null);
  await assert.rejects(loadRows(dataset, config), { message: "error.source" });
  assert.equal(calls.length, 0);
});

test("t fills in placeholders", () => {
  assert.equal(t("Line %(line)s: %(message)s", { line: 3, message: "x" }), "Line 3: x");
  assert.equal(t("%(missing)s stays"), "%(missing)s stays");
});
