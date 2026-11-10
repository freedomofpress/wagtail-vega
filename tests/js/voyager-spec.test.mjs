// Voyager's side of the chart editor: converting its Vega-Lite 2 specs to
// Vega-Lite 6, what opening a chart in it would lose, and when its reports
// are written to the field (voyager-spec.js), plus the iframe messenger's
// origin checks (voyager-editor.js). Voyager itself is tested in the
// browser (tests/e2e/test_voyager.py).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { loadVoyager, plain } from "./load.mjs";

const VL6 = "https://vega.github.io/schema/vega-lite/v6.json";
const VG6 = "https://vega.github.io/schema/vega/v6.json";

const window = loadVoyager();
const { toVoyagerSpec, fromVoyagerSpec, voyagerProblems, lostPaths, Baseline, specText } =
  window.wagtailVegaAdmin.voyagerSpec;

// Shared with tests/test_voyager.py, which validates every "expected" spec
// against the vendored Vega-Lite v6 schema.
const FIXTURES = JSON.parse(readFileSync(new URL("./fixtures/voyager-specs.json", import.meta.url), "utf8"));

// The test project's first demo chart (tests/testapp/demo.py): grouped bars
const GROUPED = {
  $schema: VL6,
  title: "Requests by quarter",
  width: "container",
  data: { name: "source" },
  mark: { type: "bar", tooltip: true },
  encoding: {
    x: { field: "quarter", type: "nominal", title: null },
    y: { field: "requests", type: "quantitative" },
    color: { field: "agency", type: "nominal" },
    xOffset: { field: "agency" },
  },
};

// A chart Voyager can show as it is
const PLAIN = {
  $schema: VL6,
  title: "Weather",
  width: "container",
  data: { name: "weather" },
  mark: "bar",
  encoding: {
    x: { field: "date", timeUnit: "month", type: "ordinal" },
    y: { aggregate: "count", type: "quantitative" },
    color: { field: "weather", type: "nominal" },
  },
};

// -- Conversion -----------------------------------------------------------------

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
    { ...unit, $schema: VG6 }, // Vega
    { ...unit, $schema: undefined },
    { $schema: VL6, layer: [unit] },
    { ...unit, layer: [] },
    { ...unit, hconcat: [] },
    { ...unit, facet: { row: { field: "a" } } },
    { ...unit, repeat: ["a"] },
    { ...unit, mark: { point: true } }, // no mark type
    { ...unit, mark: "arc" }, // not in Vega-Lite 2
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

// -- What Voyager would lose ----------------------------------------------------------

test("lostPaths reports what's missing or different, not what's added", () => {
  const original = {
    $schema: VL6,
    title: "T",
    mark: { type: "bar", cornerRadius: 3 },
    encoding: { x: { field: "a", type: "nominal", axis: { format: "%" } }, theta: { field: "b" } },
    config: { axis: { grid: false, labelFontSize: 14 } },
    params: [{ name: "p" }],
  };
  const converted = {
    $schema: VL6,
    title: "T",
    mark: "bar",
    encoding: { x: { field: "a", type: "nominal" }, y: { field: "c", type: "quantitative" } },
    config: { axis: { grid: false, labelFontSize: 12 }, line: { point: true } },
  };
  assert.deepEqual(plain(lostPaths(original, converted)), [
    ["mark", "cornerRadius"],
    ["encoding", "x", "axis"],
    ["encoding", "theta"],
    ["config", "axis", "labelFontSize"],
    ["params"],
  ]);
  // A different mark type is the whole mark
  assert.deepEqual(plain(lostPaths({ mark: "bar" }, { mark: "line" })), [["mark"]]);
  assert.deepEqual(plain(lostPaths(original, original)), []);
});

test("grouped bars: Voyager would stack them, and drop what it doesn't know", () => {
  const { blocked, lost, voyager } = voyagerProblems(GROUPED, "source");
  assert.equal(blocked, null);
  assert.deepEqual(plain(lost), [
    { key: "voyager.lost.grouped", vars: {} },
    { key: "voyager.lost.path", vars: { path: "mark.tooltip" } },
    { key: "voyager.lost.path", vars: { path: "encoding.x.title" } },
  ]);
  // It still opens, without the offset
  assert.equal("xOffset" in voyager.encoding, false);
  assert.equal(voyager.mark, "bar");
});

test("a chart Voyager can show loses nothing", () => {
  const { blocked, lost } = voyagerProblems(PLAIN, "weather");
  assert.equal(blocked, null);
  assert.deepEqual(plain(lost), []);
  // ...unless it's opened with another dataset
  assert.deepEqual(plain(voyagerProblems(PLAIN, "source").lost), [{ key: "voyager.lost.data", vars: {} }]);
});

test("params, selections, transforms and other channels are reported", () => {
  const spec = {
    ...PLAIN,
    params: [{ name: "brush", select: "interval" }],
    transform: [{ calculate: "datum.a * 2", as: "b" }],
    encoding: { ...PLAIN.encoding, strokeDash: { field: "weather", type: "nominal" } },
  };
  assert.deepEqual(plain(voyagerProblems(spec, "weather").lost), [
    { key: "voyager.lost.params", vars: {} },
    { key: "voyager.lost.transform", vars: {} },
    { key: "voyager.lost.channel", vars: { channel: "strokeDash" } },
  ]);
});

test("what Voyager changed once it opened the chart is reported too", () => {
  // Say Voyager dropped the x axis's time unit
  const shown = toVoyagerSpec(PLAIN);
  const reported = { ...shown, encoding: { ...shown.encoding, x: { field: "date", type: "ordinal" } } };
  assert.deepEqual(plain(voyagerProblems(PLAIN, "weather", reported).lost), [
    { key: "voyager.lost.path", vars: { path: "encoding.x.timeUnit" } },
  ]);
});

test("specs Voyager can't open at all say why", () => {
  const cases = [
    [[1, 2], "voyager.blocked.notObject"],
    [{ $schema: VG6, marks: [] }, "voyager.blocked.vega"],
    [{ mark: "bar", encoding: {} }, "voyager.blocked.noSchema"],
    [{ $schema: VL6, layer: [PLAIN] }, "voyager.blocked.composite", { key: "layer" }],
    [{ ...PLAIN, hconcat: [] }, "voyager.blocked.composite", { key: "hconcat" }],
    [{ $schema: VL6, facet: { row: { field: "a" } }, spec: PLAIN }, "voyager.blocked.composite", { key: "facet" }],
    [{ ...PLAIN, mark: undefined }, "voyager.blocked.noMark"],
    [{ ...PLAIN, mark: { type: "arc", innerRadius: 50 } }, "voyager.blocked.mark", { mark: "arc" }],
    [{ ...PLAIN, encoding: { x: { value: 3 } } }, "voyager.blocked.encoding"],
  ];
  for (const [spec, key, vars] of cases) {
    const problems = voyagerProblems(spec, "source");
    assert.equal(problems.blocked.key, key, JSON.stringify(spec));
    if (vars) assert.deepEqual(plain(problems.blocked.vars), vars);
    assert.equal(problems.voyager, null);
  }
});

// -- When to write ----------------------------------------------------------------------

const opened = (spec = GROUPED, options = {}) =>
  new Baseline({ text: specText(spec), previous: spec, datasetName: "source", ...options });

test("Voyager opening the chart writes nothing, however often it reports", () => {
  const baseline = opened();
  const shown = toVoyagerSpec(GROUPED);
  assert.equal(baseline.report(shown, { user: false }), null);
  // Voyager settling on something else, before the editor has done anything
  assert.equal(baseline.report({ ...shown, mark: "point" }, { user: false }), null);
  assert.equal(baseline.report(null, { user: false }), null);
  assert.equal(baseline.dirty, false);
});

test("the editor's change in Voyager is written, converted", () => {
  const baseline = opened();
  baseline.report(toVoyagerSpec(GROUPED), { user: false });
  // A click that changes nothing writes nothing
  assert.equal(baseline.report(toVoyagerSpec(GROUPED), { user: true }), null);
  const text = baseline.report({ mark: "point", encoding: { x: { field: "quarter", type: "nominal" } } }, { user: true });
  assert.deepEqual(JSON.parse(text), {
    $schema: VL6,
    title: "Requests by quarter",
    width: "container",
    data: { name: "source" },
    mark: "point",
    encoding: { x: { field: "quarter", type: "nominal" } },
  });
  assert.equal(text, JSON.stringify(JSON.parse(text), null, 2));
  assert.equal(baseline.dirty, true);
});

test("back to the baseline puts back the field's text exactly", () => {
  const original = '{"$schema": "' + VL6 + '", "mark": "bar", "encoding": {"x": {"field": "a", "type": "nominal"}}}';
  const spec = JSON.parse(original);
  const baseline = new Baseline({ text: original, previous: spec, datasetName: "source" });
  const shown = toVoyagerSpec(spec);
  baseline.report(shown, { user: false });
  assert.notEqual(baseline.report({ ...shown, mark: "tick" }, { user: true }), null);
  // Key order doesn't matter
  const reordered = { encoding: shown.encoding, mark: shown.mark };
  assert.equal(baseline.report(reordered, { user: true }), original);
  assert.equal(baseline.dirty, false);
  // ...and once is enough
  assert.equal(baseline.report(shown, { user: true }), null);
});

test("no chart in Voyager writes nothing", () => {
  const baseline = opened();
  baseline.report(toVoyagerSpec(GROUPED), { user: false });
  assert.equal(baseline.report(null, { user: true }), null);
  assert.equal(baseline.dirty, false);
});

test("an empty field: the first chart the editor makes is written", () => {
  const baseline = new Baseline({ text: "", previous: null, datasetName: "source" });
  assert.equal(baseline.report(null, { user: false }), null);
  const text = baseline.report({ mark: "bar", encoding: { x: { field: "a", type: "nominal" } } }, { user: true });
  assert.deepEqual(JSON.parse(text).data, { name: "source" });
  // Clearing the shelves again writes nothing: the field keeps the chart
  assert.equal(baseline.report(null, { user: true }), null);
  assert.equal(baseline.dirty, true);
});

test("a load that's a change (another dataset) writes what Voyager shows", () => {
  const baseline = opened(GROUPED, { changed: true, datasetName: "budget" });
  assert.equal(baseline.report(null, { user: false }), null);
  const text = baseline.report(toVoyagerSpec(GROUPED), { user: false });
  assert.deepEqual(JSON.parse(text).data, { name: "budget" });
});

// -- The iframe's messages ----------------------------------------------------------------

function fakeFrameWindow() {
  const listeners = {};
  const contentWindow = { posted: [], postMessage(message, origin) { this.posted.push([message, origin]); } };
  const iframe = { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, remove() {}, contentWindow };
  const win = loadVoyager({
    addEventListener: (type, fn) => (listeners[type] = fn),
    removeEventListener: () => {},
    document: { createElement: () => iframe },
    setTimeout,
  });
  return { win, iframe, contentWindow, dispatch: (event) => listeners.message(event) };
}

test("VoyagerFrame: a sandboxed iframe, and messages only from it", () => {
  const { win, iframe, contentWindow, dispatch } = fakeFrameWindow();
  const received = [];
  const frame = new win.wagtailVegaAdmin.VoyagerFrame({ url: "/admin/voyager/", title: "Voyager", onMessage: (d) => received.push(d.type) });
  frame.element();
  assert.equal(iframe.attrs.sandbox, "allow-scripts");
  assert.equal(iframe.src, "/admin/voyager/");
  const message = (data, source = contentWindow, origin = "null") =>
    dispatch({ source, origin, data: { channel: "wagtail-vega-voyager", ...data } });

  // Loads wait for the frame to be ready
  frame.load({ generation: 1, values: [{ a: 1 }], spec: null });
  assert.equal(contentWindow.posted.length, 0);
  message({ type: "ready" }, {}); // another window
  message({ type: "ready" }, contentWindow, "https://site.test"); // not sandboxed
  dispatch({ source: contentWindow, origin: "null", data: { channel: "other", type: "ready" } });
  assert.deepEqual(received, []);
  message({ type: "ready" });
  assert.deepEqual(received, ["ready"]);
  assert.equal(contentWindow.posted.length, 1);
  const [posted, origin] = contentWindow.posted[0];
  assert.equal(posted.type, "load");
  assert.equal(origin, "*"); // the only target that reaches an opaque origin
});

test("VoyagerFrame.flush resolves with the frame's answer, or null", async () => {
  const { win, contentWindow, dispatch } = fakeFrameWindow();
  const frame = new win.wagtailVegaAdmin.VoyagerFrame({ url: "/v/", title: "V", onMessage: () => {} });
  assert.equal(await frame.flush(), null); // not running yet
  frame.element();
  dispatch({ source: contentWindow, origin: "null", data: { channel: "wagtail-vega-voyager", type: "ready" } });
  const flushed = frame.flush();
  const [request] = contentWindow.posted.at(-1);
  assert.equal(request.type, "flush");
  dispatch({
    source: contentWindow,
    origin: "null",
    data: { channel: "wagtail-vega-voyager", type: "spec", generation: 1, spec: { mark: "bar" }, user: true, flush: request.id },
  });
  assert.deepEqual(plain((await flushed).spec), { mark: "bar" });
});
