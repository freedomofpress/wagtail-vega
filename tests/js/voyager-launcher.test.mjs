import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { loadVoyagerLauncher, plain } from "./load.mjs";

const window = loadVoyagerLauncher();
const { toVoyagerSpec, fromVoyagerSpec, urlAllowed, formatFromUrl, problemMessages } =
  window.wagtailVegaVoyager._internal;

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

const VL6 = "https://vega.github.io/schema/vega-lite/v6.json";
// Shared with tests/test_voyager_specs.py, which validates every "expected"
// spec against the vendored Vega-Lite v6 schema.
const FIXTURES = JSON.parse(
  readFileSync(new URL("./fixtures/voyager-specs.json", import.meta.url), "utf8"),
);

test("defines the launcher element once", () => {
  assert.equal(typeof window.customElements.get("wagtail-vega-voyager"), "function");
});

for (const { name, voyager, dataset, previous, expected } of FIXTURES) {
  test(`fromVoyagerSpec: ${name}`, () => {
    assert.deepEqual(plain(fromVoyagerSpec(voyager, dataset, previous)), expected);
  });
}

test("fromVoyagerSpec doesn't modify its arguments", () => {
  const voyager = { data: { values: [] }, mark: "bar", encoding: { x: { aggregate: "count", field: "*", type: "quantitative" } } };
  const previous = { $schema: VL6, title: "T", config: { a: { b: 1 } } };
  const before = JSON.stringify([voyager, previous]);
  fromVoyagerSpec(voyager, "source", previous);
  assert.equal(JSON.stringify([voyager, previous]), before);
});

test("fromVoyagerSpec never keeps inline data", () => {
  const spec = fromVoyagerSpec(
    { data: { values: [{ a: 1 }] }, datasets: { x: [] }, mark: "bar", encoding: {} },
    "source",
    { $schema: VL6, data: { values: [{ a: 2 }] }, datasets: { y: [] } },
  );
  assert.deepEqual(plain(spec.data), { name: "source" });
  assert.equal("datasets" in spec, false);
  assert.equal(spec.$schema, VL6);
});

test("toVoyagerSpec keeps the mark and field encodings Voyager understands", () => {
  const spec = {
    $schema: VL6,
    title: "Requests",
    width: "container",
    data: { name: "source" },
    mark: { type: "bar", tooltip: true },
    encoding: {
      x: { field: "quarter", type: "nominal", title: null },
      y: { field: "requests", type: "quantitative", aggregate: "sum", axis: { grid: false } },
      color: { field: "agency", type: "nominal", scale: { scheme: "set2" } },
      xOffset: { field: "agency" }, // not in Vega-Lite 2
      opacity: { value: 0.5 }, // not a field
      size: { field: "n" }, // no type
      detail: { aggregate: "count", type: "quantitative" },
      row: { field: "d", type: "temporal", timeUnit: "utcyearmonth", bin: { maxbins: 10 } },
      column: { field: "d", type: "temporal", timeUnit: { unit: "month" } },
    },
  };
  assert.deepEqual(plain(toVoyagerSpec(spec)), {
    mark: "bar",
    encoding: {
      x: { field: "quarter", type: "nominal" },
      y: { field: "requests", type: "quantitative", aggregate: "sum" },
      color: { field: "agency", type: "nominal" },
      detail: { aggregate: "count", field: "*", type: "quantitative" },
      row: { field: "d", type: "temporal", timeUnit: "utcyearmonth", bin: true },
      column: { field: "d", type: "temporal" },
    },
  });
});

test("toVoyagerSpec returns null for what Voyager can't open", () => {
  const unit = { $schema: VL6, mark: "bar", encoding: { x: { field: "a", type: "nominal" } } };
  assert.notEqual(toVoyagerSpec(unit), null);
  for (const spec of [
    null,
    "text",
    [],
    { ...unit, $schema: "https://vega.github.io/schema/vega/v6.json" }, // Vega
    { ...unit, $schema: undefined },
    { $schema: VL6, layer: [unit] },
    { ...unit, layer: [] },
    { ...unit, hconcat: [] },
    { ...unit, facet: { row: { field: "a" } } },
    { ...unit, repeat: ["a"] },
    { ...unit, mark: { point: true } }, // no mark type
    { ...unit, encoding: { x: { value: 1 } } }, // no fields
    { $schema: VL6, mark: "bar" }, // no encoding
  ]) {
    assert.equal(toVoyagerSpec(spec), null, JSON.stringify(spec));
  }
});

test("a spec survives toVoyagerSpec and fromVoyagerSpec", () => {
  const spec = {
    $schema: VL6,
    title: "T",
    data: { name: "source" },
    mark: "line",
    encoding: { x: { field: "d", type: "temporal", timeUnit: "month" }, y: { aggregate: "count", type: "quantitative" } },
  };
  assert.deepEqual(plain(fromVoyagerSpec(toVoyagerSpec(spec), "source", spec)), spec);
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
  assert.equal(check("//data.org/x.csv"), false); // refused by the server too
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
