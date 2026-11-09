// The chart builder's model: specs it writes, and specs it opens.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { loadChartSpec, plain } from "./load.mjs";

const window = loadChartSpec();
const S = window.wagtailVegaAdmin.chartSpec;
const { parseRows } = window.wagtailVegaAdmin.dataFormat;

// Shared with tests/test_chart_builder.py, which checks that every spec in
// it passes the checks that saving runs (the Vega-Lite 6 schema included).
const FIXTURES = JSON.parse(readFileSync(new URL("./fixtures/chart-specs.json", import.meta.url), "utf8"));
const columns = S.describeColumns(FIXTURES.rows);
const VL6 = "https://vega.github.io/schema/vega-lite/v6.json";

/** A state built the way the builder's controls build it. */
function build(recipe) {
  const state = S.emptyState();
  for (const key of ["mark", "arrangement", "tooltip", "point", "donut", "title", "width", "height"]) {
    if (key in recipe) state[key] = recipe[key];
  }
  for (const [name, settings] of Object.entries(recipe.channels)) {
    const ch = state.channels[name];
    S.setField(ch, settings.field, columns);
    for (const [key, value] of Object.entries(settings)) {
      if (key === "type") ch.typeImplied = false;
      if (key !== "field") ch[key] = value;
    }
  }
  return state;
}

const roundTrip = (spec) => {
  const opened = S.fromSpec(spec);
  assert.equal(opened.problem, undefined, opened.problem);
  return S.toSpec(opened.state, opened.dataset);
};

// -- Columns ---------------------------------------------------------------

test("describeColumns infers types with data-format.js's rules", () => {
  assert.deepEqual(
    plain(columns.map(({ name, type, utc }) => [name, type, utc])),
    [
      ["quarter", "nominal", false],
      ["agency", "nominal", false],
      ["requests", "quantitative", false],
      ["date", "temporal", true],
      ["temp", "quantitative", false],
      ["wind", "quantitative", false],
      ["weather", "nominal", false],
    ],
  );
});

test("describeColumns: pasted data, as the server parses it", () => {
  const rows = parseRows("zip\tcount\twhen\tflag\tmixed\n02134\t1,200\t2024-01-01T10:00\ttrue\t1\n10001\t950\t2024-01-02T11:30\tfalse\tx\n");
  const described = Object.fromEntries(S.describeColumns(rows).map((c) => [c.name, [c.type, c.utc]]));
  assert.deepEqual(plain(described), {
    zip: ["nominal", false], // "02134" stays text, so the column is mixed
    count: ["quantitative", false],
    when: ["temporal", false], // has times: local time units
    flag: ["nominal", false],
    mixed: ["nominal", false],
  });
  assert.deepEqual(plain(S.describeColumns([])), []);
  // JSON rows with missing keys and nested values
  assert.deepEqual(
    plain(S.describeColumns([{ a: 1 }, { a: null, b: { c: 1 } }]).map((c) => [c.name, c.type])),
    [["a", "quantitative"], ["b", "nominal"]],
  );
});

// -- Writing specs -----------------------------------------------------------------

for (const { name, recipe, expected } of FIXTURES.charts) {
  test(`toSpec: ${name}`, () => {
    const { spec, kept } = S.toSpec(build(recipe), "source");
    assert.deepEqual(plain(spec), expected);
    assert.deepEqual(plain(kept), []);
  });

  test(`round trip: ${name}`, () => {
    const { spec, kept } = roundTrip(expected);
    assert.deepEqual(plain(spec), expected);
    assert.deepEqual(plain(kept), []);
  });
}

test("specs refer to the dataset by name, never inline data", () => {
  for (const { recipe } of FIXTURES.charts) {
    const { spec } = S.toSpec(build(recipe), "budget");
    assert.deepEqual(plain(spec.data), { name: "budget" });
    assert.equal("datasets" in spec, false);
    assert.equal(JSON.stringify(spec).includes('"values"'), false);
    assert.equal(spec.$schema, VL6);
  }
});

test("grouped bars need a colour field to group by", () => {
  const state = build({ mark: "bar", arrangement: "grouped", channels: { x: { field: "quarter" }, y: { field: "requests" } } });
  const { spec } = S.toSpec(state, "source");
  assert.equal("xOffset" in spec.encoding, false);
});

test("stacking only applies to bars and areas", () => {
  const state = build({ mark: "line", arrangement: "normalize", channels: { x: { field: "date" }, y: { field: "temp" } } });
  assert.equal("stack" in S.toSpec(state, "source").spec.encoding.y, false);
});

test("channels the mark doesn't use aren't written", () => {
  const state = build({ mark: "bar", channels: { x: { field: "quarter" }, y: { field: "requests" }, theta: { field: "temp" }, size: { field: "wind" } } });
  assert.deepEqual(Object.keys(S.toSpec(state, "source").spec.encoding), ["x", "y"]);
  state.mark = "arc";
  assert.deepEqual(Object.keys(S.toSpec(state, "source").spec.encoding), ["theta"]);
});

// -- Opening specs -------------------------------------------------------------------

for (const { name, spec, kept } of FIXTURES.roundTrip) {
  test(`round trip keeps what the builder doesn't edit: ${name}`, () => {
    const before = JSON.stringify(spec);
    const result = roundTrip(spec);
    assert.deepEqual(plain(result.spec), spec);
    assert.deepEqual(plain(result.kept).sort(), [...kept].sort());
    assert.equal(JSON.stringify(spec), before, "fromSpec must not modify the spec");
  });
}

test("the sandbox's grouped bars open as grouped bars, not stacked", () => {
  const [grouped] = FIXTURES.roundTrip;
  const { state } = S.fromSpec(grouped.spec);
  assert.equal(state.mark, "bar");
  assert.equal(state.arrangement, "grouped");
  assert.equal(state.channels.color.field, "agency");
  assert.equal(state.title, "Requests by quarter");
  assert.equal("xOffset" in state.encodingExtras, false);
});

test("values the controls can't show are marked as custom", () => {
  const custom = FIXTURES.roundTrip.find((f) => f.name.startsWith("values the controls"));
  const { state } = S.fromSpec(custom.spec);
  const { x, y, color } = state.channels;
  assert.deepEqual(plain(Object.keys(x.extras).sort()), ["sort", "timeUnit"]);
  assert.equal(x.type, "ordinal");
  assert.deepEqual(plain(Object.keys(y.extras).sort()), ["aggregate", "stack"]);
  assert.equal(S.customArrangement(state), true);
  assert.deepEqual(plain(Object.keys(color.extras)), ["bin"]);
  assert.deepEqual(plain(Object.keys(state.extras).sort()), ["title", "width"]);
});

test("a channel's extras apply while it shows the same field", () => {
  const everything = FIXTURES.roundTrip.find((f) => f.name.startsWith("everything"));
  const { state } = S.fromSpec(everything.spec);
  S.setField(state.channels.x, "agency", columns);
  let { spec, kept } = S.toSpec(state, "source");
  assert.deepEqual(plain(spec.encoding.x), { field: "agency", type: "nominal", sort: "descending" });
  assert.equal(kept.includes("encoding.x.axis"), false);
  // Back to the original field: its axis settings come back
  S.setField(state.channels.x, "quarter", columns);
  state.channels.x.type = "ordinal";
  ({ spec, kept } = S.toSpec(state, "source"));
  assert.deepEqual(plain(spec.encoding.x), everything.spec.encoding.x);
  assert.equal(kept.includes("encoding.x.axis"), true);
});

test("the mark's extras apply while it's the same mark type", () => {
  const everything = FIXTURES.roundTrip.find((f) => f.name.startsWith("everything"));
  const { state } = S.fromSpec(everything.spec);
  state.mark = "line";
  let { spec } = S.toSpec(state, "source");
  assert.deepEqual(plain(spec.mark), { type: "line", tooltip: true });
  state.mark = "bar";
  ({ spec } = S.toSpec(state, "source"));
  assert.deepEqual(plain(spec.mark), everything.spec.mark);
});

test("a builder channel replaces a kept channel of the same name", () => {
  const facets = FIXTURES.roundTrip.find((f) => f.name.startsWith("facets"));
  const { state } = S.fromSpec(facets.spec);
  S.setField(state.channels.color, "weather", columns);
  const { spec, kept } = S.toSpec(state, "source");
  assert.deepEqual(plain(spec.encoding.color), { field: "weather", type: "nominal" });
  assert.equal(kept.includes("encoding.color"), false);
});

test("swapping x and y keeps each channel's settings", () => {
  const everything = FIXTURES.roundTrip.find((f) => f.name.startsWith("everything"));
  const { state } = S.fromSpec(everything.spec);
  const { channels } = state;
  [channels.x, channels.y] = [channels.y, channels.x];
  const { spec } = S.toSpec(state, "source");
  assert.deepEqual(plain(spec.encoding.x), everything.spec.encoding.y);
  assert.deepEqual(plain(spec.encoding.y), everything.spec.encoding.x);
});

test("fromSpec: what the builder can't open", () => {
  const unit = { $schema: VL6, data: { name: "source" }, mark: "bar", encoding: { x: { field: "a", type: "nominal" } } };
  assert.equal(S.fromSpec(unit).problem, undefined);
  const cases = [
    [[], /isn't a JSON object/],
    ["text", /isn't a JSON object/],
    [{ ...unit, $schema: "https://vega.github.io/schema/vega/v6.json" }, /Vega spec/],
    [{ ...unit, $schema: undefined }, /no Vega-Lite \$schema/],
    [{ $schema: VL6, layer: [unit] }, /several views \(it has “layer”\)/],
    [{ ...unit, hconcat: [] }, /“hconcat”/],
    [{ ...unit, vconcat: [] }, /“vconcat”/],
    [{ ...unit, concat: [] }, /“concat”/],
    [{ ...unit, repeat: ["a"] }, /“repeat”/],
    [{ ...unit, facet: { row: { field: "a" } }, spec: {} }, /“facet”/],
    [{ ...unit, mark: "geoshape" }, /mark type, “geoshape”/],
    [{ ...unit, mark: { point: true } }, /no mark/],
    [{ ...unit, mark: undefined }, /no mark/],
    [{ ...unit, data: { url: "/x.csv" } }, /by name/],
    [{ ...unit, data: { values: [{ a: 1 }] } }, /by name/],
    [{ ...unit, data: { name: "source", format: { type: "json" } } }, /by name/],
    [{ ...unit, encoding: [] }, /encoding/],
  ];
  for (const [spec, problem] of cases) {
    const result = S.fromSpec(spec);
    assert.match(result.problem || "", problem, JSON.stringify(spec));
    assert.equal(result.state, undefined);
  }
  assert.deepEqual(plain(S.fromSpec(null)), { state: null });
});

test("fromSpec reports the dataset the spec uses", () => {
  assert.equal(S.fromSpec({ $schema: VL6, data: { name: "budget" }, mark: "bar" }).dataset, "budget");
  assert.equal(S.fromSpec({ $schema: VL6, mark: "bar" }).dataset, null);
});

test("sameSpec ignores key order", () => {
  assert.equal(S.sameSpec({ a: 1, b: { c: 2, d: [1, { e: 1, f: 2 }] } }, { b: { d: [1, { f: 2, e: 1 }], c: 2 }, a: 1 }), true);
  assert.equal(S.sameSpec({ a: [1, 2] }, { a: [2, 1] }), false);
  assert.equal(S.sameSpec({ a: null }, {}), false);
});

// -- Suggestions ---------------------------------------------------------------------

test("suggestions from column types", () => {
  const labels = S.suggest(columns).map((s) => s.label);
  assert.deepEqual(plain(labels), [
    "Line: requests over time (date)",
    "Lines: requests over time, one for each agency",
    "Stacked areas: requests over time by agency",
    "Bars: requests by quarter",
    "Grouped bars: requests by quarter and agency",
    "Stacked bars: requests by quarter and agency",
    "Heatmap: requests by quarter and agency",
    "Pie: share of requests by agency",
    "Scatter plot: temp against requests",
  ]);
});

test("every suggestion makes a chart with fields", () => {
  for (const suggestion of S.suggest(columns)) {
    const state = S.applySuggestion(S.emptyState(), suggestion, columns);
    const { spec } = S.toSpec(state, "source");
    assert.ok(Object.keys(spec.encoding).length >= 2, suggestion.label);
  }
});

test("suggestions for data with few kinds of column", () => {
  const only = (rows) => S.suggest(S.describeColumns(rows)).map((s) => s.label);
  assert.deepEqual(plain(only([{ name: "a" }, { name: "b" }])), ["Bars: number of rows by name"]);
  assert.deepEqual(plain(only([{ n: 1 }, { n: 2 }])), ["Histogram of n"]);
  assert.deepEqual(plain(only([{ d: "2024-01-01" }])), ["Bars: rows per month (d)"]);
  assert.deepEqual(plain(only([])), []);
});

test("initialState is the first suggestion", () => {
  const { spec } = S.toSpec(S.initialState(columns), "source");
  assert.deepEqual(plain(spec.encoding), {
    x: { field: "date", type: "temporal" },
    y: { field: "requests", type: "quantitative" },
  });
  assert.equal(S.initialState([]).mark, "bar");
});

test("grouped bar suggestion is grouped", () => {
  const grouped = S.suggest(columns).find((s) => s.label.startsWith("Grouped"));
  const { spec } = S.toSpec(S.applySuggestion(S.emptyState(), grouped, columns), "source");
  assert.deepEqual(plain(spec.encoding.xOffset), { field: "agency" });
});

test("setField infers the type and clears settings that don't fit", () => {
  const ch = S.emptyChannel();
  S.setField(ch, "requests", columns);
  ch.aggregate = "sum";
  ch.bin = true;
  assert.equal(ch.type, "quantitative");
  S.setField(ch, "date", columns);
  assert.deepEqual([ch.type, ch.utc, ch.aggregate, ch.bin], ["temporal", true, "", false]);
  ch.timeUnit = "year";
  S.setField(ch, "weather", columns);
  assert.deepEqual([ch.type, ch.timeUnit], ["nominal", ""]);
  S.setField(ch, S.COUNT, columns);
  assert.deepEqual([ch.count, ch.field, ch.type], [true, "", "quantitative"]);
  S.setField(ch, "", columns);
  assert.equal(S.hasField(ch), false);
});
