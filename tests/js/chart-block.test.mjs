import assert from "node:assert/strict";
import { test } from "node:test";
import { loadChartBlock, plain } from "./load.mjs";

const { window, registered } = loadChartBlock();
const { datasetReferences, missingDatasets, chartLabel, format } =
  window.wagtailVegaAdmin.chartBlock._internal;

const VL = "https://vega.github.io/schema/vega-lite/v6.json";
const VG = "https://vega.github.io/schema/vega/v6.json";
const MESSAGES = {
  none: 'This chart has no dataset called "%(name)s". Add one under Data.',
  some: 'This chart has no dataset called "%(name)s". Use one of its datasets (%(names)s), or add one under Data.',
};

test("registers the telepath definition", () => {
  assert.equal(typeof registered["wagtail_vega.blocks.ChartBlock"], "function");
});

// Must match wagtail_vega.spec.dataset_references (tests/test_spec.py)
test("datasetReferences: Vega-Lite, at any depth", () => {
  const spec = {
    $schema: VL,
    datasets: { own: [{ a: 1 }] },
    layer: [
      { data: { name: "source", format: { type: "csv" } }, mark: "bar" },
      { data: { name: "own" }, mark: "rule" },
      { data: { url: "x.csv" }, mark: "point" },
      {
        mark: "line",
        transform: [{ lookup: "id", from: { data: { name: "extra" }, key: "id" } }],
        data: { values: [{ data: { name: "nope" } }] },
      },
    ],
  };
  assert.deepEqual(plain(datasetReferences(spec)), [
    { path: ["layer", 0, "data", "name"], name: "source" },
    { path: ["layer", 3, "transform", 0, "from", "data", "name"], name: "extra" },
  ]);
});

test("datasetReferences: Vega, top-level entries with only a name", () => {
  const spec = {
    $schema: VG,
    data: [
      { name: "source" },
      { name: "filtered", source: "source" },
      { name: "inline", values: [] },
      { name: "seq", transform: [{ type: "sequence", start: 0 }] },
    ],
  };
  assert.deepEqual(plain(datasetReferences(spec)), [{ path: ["data", 0, "name"], name: "source" }]);
});

test("datasetReferences: nothing without a known $schema", () => {
  for (const spec of [null, [], {}, { data: { name: "x" } }, { $schema: "x", data: { name: "x" } }]) {
    assert.deepEqual(plain(datasetReferences(spec)), []);
  }
});

test("missingDatasets uses the server's messages", () => {
  const spec = { $schema: VL, data: { name: "source" }, mark: "bar" };
  assert.deepEqual(plain(missingDatasets(spec, ["source"], MESSAGES)), []);
  assert.deepEqual(plain(missingDatasets(spec, [], MESSAGES)), [
    { path: ["data", "name"], message: 'This chart has no dataset called "source". Add one under Data.' },
  ]);
  assert.equal(
    missingDatasets(spec, ["sales", "x"], MESSAGES)[0].message,
    'This chart has no dataset called "source". Use one of its datasets (sales, x), or add one under Data.',
  );
});

test("format leaves unknown placeholders alone", () => {
  assert.equal(format("%(a)s and %(b)s", { a: "1" }), "1 and %(b)s");
});

test("chartLabel: the spec's title, then the caption, then the description", () => {
  const spec = (title) => JSON.stringify({ $schema: VL, title });
  assert.equal(chartLabel({ spec: spec("Requests"), caption: "Source", description: "D" }), "Requests");
  assert.equal(chartLabel({ spec: spec({ text: ["Two", "lines"] }), caption: "" }), "Two lines");
  assert.equal(chartLabel({ spec: spec(undefined), caption: "  Source:\n FOIA " }), "Source: FOIA");
  assert.equal(chartLabel({ spec: "{not json", caption: "", description: "Bars" }), "Bars");
  assert.equal(chartLabel({ spec: "", caption: "", description: "" }), null);
  assert.equal(chartLabel({ spec: spec("A long chart title"), caption: "" }, 10), "A long ch…");
});
