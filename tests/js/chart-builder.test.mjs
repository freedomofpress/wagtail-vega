// The chart builder lightbox's helpers: data loading rules, validation
// messages and the preview's theming. The lightbox itself is tested in the
// browser (tests/e2e/test_chart_builder.py).
import assert from "node:assert/strict";
import { test } from "node:test";
import { loadChartBuilder, plain } from "./load.mjs";

const window = loadChartBuilder();
const { urlAllowed, formatFromUrl, problemMessages, deepMerge, previewSpec } =
  window.wagtailVegaAdmin.chartBuilder._internal;

test("defines the button element once", () => {
  assert.equal(typeof window.customElements.get("wagtail-vega-chart-builder"), "function");
});

test("problemMessages formats validate-spec errors like a failed save", () => {
  assert.deepEqual(
    plain(
      problemMessages([
        { path: ["encoding", "x", "type"], message: "bad type" },
        { path: [], message: "whole spec" },
        { message: "no path" },
      ]),
    ),
    ["encoding.x.type: bad type", "whole spec", "no path"],
  );
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
  const light = previewSpec(spec, rows, theme, false);
  assert.deepEqual(plain(light.datasets), { source: rows });
  assert.deepEqual(plain(light.data), { name: "source" });
  // Theme, then the spec's own config
  assert.deepEqual(plain(light.config), {
    axis: { grid: false, labelColor: "#333" },
    background: "var(--chart-bg, white)",
  });
  const dark = previewSpec(spec, rows, theme, true);
  assert.deepEqual(plain(dark.config.axis), { grid: false, labelColor: "#ddd" });
  // No theme: the spec as it is, plus data
  const plainSpec = previewSpec({ ...spec, config: undefined }, rows, null, false);
  assert.equal("config" in plainSpec, false);
  assert.equal("datasets" in spec, false); // not modified
});
