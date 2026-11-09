/* wagtail-vega admin: the chart builder's model, and its Vega-Lite specs.
 *
 * The builder (chart-builder.js) edits a plain "state" object; this file
 * turns it into a Vega-Lite 6 spec (toSpec) and reads a spec back into a
 * state (fromSpec). No DOM, so it's unit-tested in Node (tests/js).
 *
 * ROUND TRIP. A spec the builder opens is either:
 *
 * - A single view it understands (one Vega-Lite mark, data by name). The
 *   builder's controls cover the mark type and the common parts of the
 *   x, y, theta, colour, size, row and column encodings. Everything else is
 *   kept exactly as it was and written back untouched ("extras"): top-level
 *   keys such as config, transform or params; mark properties such as
 *   cornerRadius; encoding properties such as axis, scale or legend; and
 *   other channels such as tooltip or opacity. A value the builder can't
 *   show in a control (e.g. a sort by a custom order) is also kept, and the
 *   control says "Custom (from the spec)" until it's changed.
 *
 *   Extras belong to what they were written for: a channel's extras apply
 *   while it shows the same field, and the mark's while it's the same mark
 *   type. So changing the x field drops x's axis format, and changing back
 *   restores it. toSpec reports which extras it kept, and the builder lists
 *   both those and the ones the editor's changes removed.
 *
 * - Anything else: a Vega spec, a layered, concatenated, repeated or
 *   faceted (operator) view, a mark the builder doesn't offer, or inline or
 *   URL data. fromSpec returns {problem}, and the builder says so and offers
 *   to start a new chart instead; it never writes a partial copy.
 *
 * So opening a spec and choosing "Use this chart" without changes gives
 * back the same spec (tests/js/chart-spec.test.mjs checks this).
 *
 * Field types are inferred with data-format.js's rules (columnType), so the
 * builder agrees with the summary shown under pasted data.
 *
 * Exposed as window.wagtailVegaAdmin.chartSpec. Needs data-format.js.
 */
(() => {
  "use strict";

  const admin = (window.wagtailVegaAdmin = window.wagtailVegaAdmin || {});

  const VL_SCHEMA = "https://vega.github.io/schema/vega-lite/v6.json";

  const MARKS = [
    ["bar", "Bar"],
    ["line", "Line"],
    ["area", "Area"],
    ["point", "Point (scatter plot)"],
    ["circle", "Circle"],
    ["square", "Square"],
    ["tick", "Tick (strip plot)"],
    ["arc", "Arc (pie or donut)"],
    ["rect", "Rectangle (heatmap)"],
    ["rule", "Rule"],
  ];
  const MARK_TYPES = new Set(MARKS.map(([value]) => value));

  const CHANNELS = {
    x: { label: "X axis (horizontal)", titleLabel: "Axis title" },
    y: { label: "Y axis (vertical)", titleLabel: "Axis title" },
    theta: { label: "Slice size", titleLabel: "Legend title" },
    color: { label: "Colour", titleLabel: "Legend title" },
    size: { label: "Size", titleLabel: "Legend title" },
    column: { label: "Columns (a small chart for each value)", titleLabel: "Heading" },
    row: { label: "Rows (a small chart for each value)", titleLabel: "Heading" },
  };
  // Order of the encodings in specs the builder writes
  const ENCODING_ORDER = ["x", "y", "xOffset", "yOffset", "theta", "color", "size", "column", "row"];

  const TYPES = [
    ["quantitative", "Number (quantitative)"],
    ["nominal", "Category (nominal)"],
    ["ordinal", "Ordered category (ordinal)"],
    ["temporal", "Date or time (temporal)"],
  ];
  const AGGREGATES = [
    ["sum", "Sum"],
    ["mean", "Mean (average)"],
    ["median", "Median"],
    ["min", "Minimum"],
    ["max", "Maximum"],
    ["count", "Count"],
    ["distinct", "Count of distinct values"],
  ];
  const TIME_UNITS = [
    ["year", "Year"],
    ["yearquarter", "Year and quarter"],
    ["yearmonth", "Year and month"],
    ["yearmonthdate", "Date"],
    ["yearmonthdatehours", "Date and hour"],
    ["quarter", "Quarter (all years together)"],
    ["month", "Month (all years together)"],
    ["date", "Day of the month"],
    ["day", "Day of the week"],
    ["hours", "Hour of the day"],
  ];
  const TIME_UNIT_RE = new RegExp(`^(utc)?(${TIME_UNITS.map(([u]) => u).join("|")})$`);
  const SORT_CHANNELS = ["x", "y", "theta", "color", "size"];
  const SORT_RE = new RegExp(`^(ascending|descending|-?(${SORT_CHANNELS.join("|")}))$`);

  // How bars and areas that share a position are arranged ("" = Vega-Lite's
  // default, stacked). "grouped" is bars side by side (xOffset/yOffset).
  const ARRANGEMENTS = [
    ["", "Stacked", ["bar", "area"]],
    ["normalize", "Stacked to 100%", ["bar", "area"]],
    ["center", "Stacked around the centre (streamgraph)", ["area"]],
    ["grouped", "Side by side (grouped)", ["bar"]],
    ["none", "Overlapping", ["bar", "area"]],
  ];
  const STACK_VALUES = { normalize: "normalize", center: "center", none: null };

  // Views the builder can't edit
  const COMPOSITE = ["layer", "concat", "hconcat", "vconcat", "repeat", "facet", "spec"];
  // Top-level keys the builder controls (others are extras)
  const CONTROLLED = new Set(["$schema", "data", "mark", "encoding", "title", "width", "height"]);
  // Order of top-level keys in specs the builder writes; others go last
  const TOP_ORDER = [
    "$schema", "title", "description", "width", "height", "autosize", "padding",
    "background", "data", "transform", "params", "mark", "encoding",
  ];
  const DONUT_RADIUS = 50;

  const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const clone = (v) => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
  const COUNT = "__count__"; // the "Count of rows" field option

  /** JSON with object keys sorted, to compare specs whatever their key order. */
  function canonical(value) {
    return JSON.stringify(value, (key, v) =>
      isObject(v) ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]])) : v,
    );
  }

  const sameSpec = (a, b) => canonical(a) === canonical(b);

  // -- Columns ----------------------------------------------------------------

  const DATE_ONLY_RE = /^\d{4}-\d{2}(?:-\d{2})?$/;

  /** The dataset's columns: [{name, type, utc, distinct}], in first-seen
   * order. `type` is a Vega-Lite type, from data-format.js's columnType:
   * numbers are quantitative, dates temporal, anything else nominal. `utc`
   * is true for dates without a time, which browsers read as UTC midnight;
   * time units then need to be UTC too, or Jan 1 falls in December west of
   * Greenwich. */
  function describeColumns(rows) {
    const { columnType } = admin.dataFormat;
    const names = [];
    const seen = new Set();
    for (const row of rows) {
      if (!isObject(row)) continue;
      for (const key of Object.keys(row)) {
        if (!seen.has(key)) {
          seen.add(key);
          names.push(key);
        }
      }
    }
    return names.map((name) => {
      const values = rows
        .map((row) => (isObject(row) ? row[name] : undefined))
        .filter((v) => v !== null && v !== undefined && v !== "")
        .map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v)));
      const kind = columnType(values);
      const type = kind === "number" ? "quantitative" : kind === "date" ? "temporal" : "nominal";
      return {
        name,
        type,
        utc: type === "temporal" && values.every((v) => DATE_ONLY_RE.test(v.trim())),
        distinct: new Set(values).size,
      };
    });
  }

  // -- State ------------------------------------------------------------------

  function emptyChannel() {
    return {
      field: "",
      count: false, // aggregate "count" with no field
      type: "",
      typeImplied: false, // the spec left the type for Vega-Lite to infer
      aggregate: "",
      bin: false,
      timeUnit: "",
      utc: false,
      sort: "", // "" default, "none" (null: data order), or a sort string
      title: "",
      extras: {}, // kept from the spec while the channel shows extrasFor
      extrasFor: null,
    };
  }

  function emptyState() {
    return {
      schema: VL_SCHEMA,
      mark: "bar",
      tooltip: true,
      point: false,
      donut: false,
      innerRadius: DONUT_RADIUS,
      arrangement: "",
      offsetExtras: {},
      markExtras: {},
      markExtrasFor: null,
      title: "",
      width: "container", // "container", "" (automatic) or a number
      height: "", // "" (automatic) or a number
      channels: Object.fromEntries(Object.keys(CHANNELS).map((c) => [c, emptyChannel()])),
      encodingExtras: {}, // other channels, kept as they are
      extras: {}, // other top-level keys, kept as they are
    };
  }

  function channelsFor(mark) {
    if (mark === "arc") return ["theta", "color", "column", "row"];
    const channels = ["x", "y", "color"];
    if (mark === "point" || mark === "circle" || mark === "square") channels.push("size");
    return [...channels, "column", "row"];
  }

  const channelKey = (ch) => (ch.count ? COUNT : ch.field);
  const hasField = (ch) => Boolean(ch && (ch.field || ch.count));
  const extrasApply = (ch) => ch.extrasFor !== null && ch.extrasFor === channelKey(ch);
  const markExtrasApply = (state) => state.markExtrasFor === state.mark;

  /** The type Vega-Lite gives a field that has none. */
  function impliedType(ch) {
    if (ch.timeUnit) return "temporal";
    if (ch.count || ch.aggregate || ch.bin) return "quantitative";
    return "nominal";
  }

  const isMeasure = (ch) =>
    hasField(ch) && (ch.count || Boolean(ch.aggregate) || (ch.type || impliedType(ch)) === "quantitative");

  /** The position channel that bars and areas stack along. */
  function measureChannel(state) {
    const { x, y } = state.channels;
    if (isMeasure(y)) return "y";
    if (isMeasure(x)) return "x";
    return "y";
  }

  const offsetChannel = (state) => (measureChannel(state) === "y" ? "xOffset" : "yOffset");

  /** Point a channel at a column (or COUNT, or "" for none). */
  function setField(ch, value, columns) {
    const column = columns.find((c) => c.name === value);
    ch.count = value === COUNT;
    ch.field = ch.count ? "" : value;
    ch.typeImplied = false;
    if (ch.count) {
      ch.type = "quantitative";
      ch.aggregate = "";
      ch.bin = false;
      ch.timeUnit = "";
    } else if (value) {
      ch.type = column ? column.type : ch.type || "nominal";
      ch.utc = Boolean(column?.utc);
      if (ch.type !== "quantitative") ch.aggregate = ch.aggregate === "count" || ch.aggregate === "distinct" ? ch.aggregate : "";
      if (ch.type !== "quantitative") ch.bin = false;
      if (ch.type !== "temporal") ch.timeUnit = "";
    }
    return ch;
  }

  // -- Suggestions --------------------------------------------------------------

  /** A few sensible starting charts for the dataset's columns: [{label, apply}],
   * where apply(state) sets the mark and encodings. Simple rules, best first. */
  function suggest(columns) {
    const byType = (type) => columns.filter((c) => c.type === type);
    const quantitative = byType("quantitative");
    const temporal = byType("temporal");
    const nominal = byType("nominal");
    // Along an axis: the category with the most values (within reason)
    const n1 =
      [...nominal].sort((a, b) => b.distinct - a.distinct).find((c) => c.distinct <= 50) || nominal[0];
    // By colour or slice: categories with few enough values to tell apart
    const groups = nominal.filter((c) => c.distinct <= 12).sort((a, b) => a.distinct - b.distinct);
    const g = groups.find((c) => c !== n1);
    const [q1, q2, q3] = quantitative;
    const [t] = temporal;
    const out = [];
    const add = (label, mark, channels, extra = {}) => out.push({ label, mark, channels, ...extra });

    if (t && q1) {
      add(`Line: ${q1.name} over time (${t.name})`, "line", { x: [t], y: [q1] });
      if (g) {
        add(`Lines: ${q1.name} over time, one for each ${g.name}`, "line", { x: [t], y: [q1], color: [g] });
        add(`Stacked areas: ${q1.name} over time by ${g.name}`, "area", { x: [t], y: [q1], color: [g] });
      }
    }
    if (n1 && q1) {
      add(`Bars: ${q1.name} by ${n1.name}`, "bar", { x: [n1], y: [q1, "sum"] });
      if (g) {
        add(`Grouped bars: ${q1.name} by ${n1.name} and ${g.name}`, "bar", { x: [n1], y: [q1, "sum"], color: [g] }, { arrangement: "grouped" });
        add(`Stacked bars: ${q1.name} by ${n1.name} and ${g.name}`, "bar", { x: [n1], y: [q1, "sum"], color: [g] });
        add(`Heatmap: ${q1.name} by ${n1.name} and ${g.name}`, "rect", { x: [n1], y: [g], color: [q1, "sum"] });
      }
      const slices = groups.find((c) => c.distinct <= 8);
      if (slices) add(`Pie: share of ${q1.name} by ${slices.name}`, "arc", { theta: [q1, "sum"], color: [slices] });
    }
    if (q1 && q2) {
      const color = g ? { color: [g] } : {};
      const size = q3 ? { size: [q3] } : {};
      add(`Scatter plot: ${q2.name} against ${q1.name}`, "point", { x: [q1], y: [q2], ...color, ...size });
    }
    if (t && !q1) add(`Bars: rows per month (${t.name})`, "bar", { x: [t, null, "yearmonth"], y: [COUNT] });
    if (n1 && !q1) add(`Bars: number of rows by ${n1.name}`, "bar", { x: [n1], y: [COUNT] });
    if (q1 && !n1 && !t && !q2) add(`Histogram of ${q1.name}`, "bar", { x: [q1, null, null, true], y: [COUNT] });
    return out;
  }

  /** Set up `state` (a new chart) from a suggestion. Keeps the title, size
   * and the spec's top-level extras; the channels start again. */
  function applySuggestion(state, suggestion, columns) {
    state.mark = suggestion.mark;
    state.arrangement = suggestion.arrangement || "";
    for (const name of Object.keys(CHANNELS)) state.channels[name] = emptyChannel();
    for (const [name, [column, aggregate, timeUnit, bin]] of Object.entries(suggestion.channels)) {
      const ch = state.channels[name];
      setField(ch, column === COUNT ? COUNT : column.name, columns);
      if (aggregate) ch.aggregate = aggregate;
      if (timeUnit) ch.timeUnit = timeUnit;
      if (bin) ch.bin = true;
    }
    return state;
  }

  /** A new chart for the columns: the first suggestion, or an empty bar chart. */
  function initialState(columns) {
    const state = emptyState();
    const [first] = suggest(columns);
    return first ? applySuggestion(state, first, columns) : state;
  }

  // -- Reading a spec -------------------------------------------------------------

  function isVegaLite(spec) {
    return isObject(spec) && typeof spec.$schema === "string" && spec.$schema.includes("/vega-lite/");
  }

  /** Can a builder channel show this encoding? (Fields and counts, not
   * constant values, conditions or repeat references.) */
  function editableChannel(def) {
    if (!isObject(def)) return false;
    if ("value" in def || "datum" in def || "condition" in def) return false;
    if (typeof def.field === "string" && def.field) return true;
    return def.aggregate === "count" && !("field" in def);
  }

  function readChannel(def) {
    const ch = emptyChannel();
    const extras = clone(def);
    if (typeof extras.field === "string" && extras.field) {
      ch.field = extras.field;
      delete extras.field;
    } else {
      ch.count = true;
      delete extras.aggregate;
    }
    if (typeof extras.aggregate === "string" && AGGREGATES.some(([a]) => a === extras.aggregate)) {
      ch.aggregate = extras.aggregate;
      delete extras.aggregate;
    }
    if (extras.bin === true) {
      ch.bin = true;
      delete extras.bin;
    }
    const unit = typeof extras.timeUnit === "string" && TIME_UNIT_RE.exec(extras.timeUnit);
    if (unit) {
      ch.utc = Boolean(unit[1]);
      ch.timeUnit = unit[2];
      delete extras.timeUnit;
    }
    if ("type" in extras) {
      if (TYPES.some(([t]) => t === extras.type)) {
        ch.type = extras.type;
        delete extras.type;
      }
    } else {
      ch.type = impliedType(ch);
      ch.typeImplied = true;
    }
    if (extras.sort === null) {
      ch.sort = "none";
      delete extras.sort;
    } else if (typeof extras.sort === "string" && SORT_RE.test(extras.sort)) {
      ch.sort = extras.sort;
      delete extras.sort;
    }
    if (typeof extras.title === "string" && extras.title) {
      ch.title = extras.title;
      delete extras.title;
    }
    ch.extras = extras;
    ch.extrasFor = channelKey(ch);
    return ch;
  }

  /**
   * Read a spec into a builder state.
   *
   * Returns {state, dataset} (the dataset name the spec uses, if any), or
   * {problem} with a sentence fragment saying why the builder can't open it
   * ("it's a Vega spec…"). An empty spec (null) gives {state: null}.
   */
  function fromSpec(spec) {
    if (spec === null || spec === undefined) return { state: null };
    if (!isObject(spec)) return { problem: "it isn't a JSON object" };
    if (!isVegaLite(spec)) {
      if (typeof spec.$schema === "string" && spec.$schema.includes("/vega/")) {
        return { problem: "it's a Vega spec, and the builder makes Vega-Lite charts" };
      }
      return { problem: "it has no Vega-Lite $schema" };
    }
    const composite = COMPOSITE.find((key) => key in spec);
    if (composite) {
      return { problem: `it combines several views (it has “${composite}”), and the builder makes one view at a time` };
    }
    const markType = isObject(spec.mark) ? spec.mark.type : spec.mark;
    if (!MARK_TYPES.has(markType)) {
      return {
        problem: markType
          ? `the builder doesn't offer its mark type, “${markType}”`
          : "it has no mark",
      };
    }
    let dataset = null;
    if ("data" in spec) {
      const data = spec.data;
      if (!isObject(data) || typeof data.name !== "string" || Object.keys(data).length !== 1) {
        return { problem: "it doesn't load its data from one of the chart's datasets by name" };
      }
      dataset = data.name;
    }
    if ("encoding" in spec && !isObject(spec.encoding)) {
      return { problem: "its encoding isn't an object" };
    }

    const state = emptyState();
    state.schema = spec.$schema;
    state.mark = markType;

    // The mark
    const mark = isObject(spec.mark) ? clone(spec.mark) : {};
    delete mark.type;
    state.tooltip = mark.tooltip === true;
    if (state.tooltip) delete mark.tooltip;
    if ((markType === "line" || markType === "area") && mark.point === true) {
      state.point = true;
      delete mark.point;
    }
    if (markType === "arc" && typeof mark.innerRadius === "number") {
      state.donut = true;
      state.innerRadius = mark.innerRadius;
      delete mark.innerRadius;
    }
    state.markExtras = mark;
    state.markExtrasFor = markType;

    // Top-level settings
    for (const [key, value] of Object.entries(spec)) {
      if (!CONTROLLED.has(key)) state.extras[key] = clone(value);
    }
    if (typeof spec.title === "string" && spec.title) state.title = spec.title;
    else if ("title" in spec) state.extras.title = clone(spec.title);
    if (!("width" in spec)) state.width = "";
    else if (spec.width === "container" || typeof spec.width === "number") state.width = spec.width;
    else state.extras.width = clone(spec.width);
    if (typeof spec.height === "number") state.height = spec.height;
    else if ("height" in spec) state.extras.height = clone(spec.height);

    // Encodings
    const shown = new Set(channelsFor(markType));
    for (const [name, def] of Object.entries(spec.encoding || {})) {
      if (shown.has(name) && editableChannel(def)) state.channels[name] = readChannel(def);
      else state.encodingExtras[name] = clone(def);
    }

    // Stacking and grouping, for bars and areas
    if (markType === "bar" || markType === "area") {
      const measure = state.channels[measureChannel(state)];
      const other = state.channels[measureChannel(state) === "y" ? "x" : "y"];
      const stack = measure.extras.stack;
      if ("stack" in measure.extras && !("stack" in other.extras)) {
        const found = Object.entries(STACK_VALUES).find(([, v]) => v === stack);
        const allowed = found && ARRANGEMENTS.find(([a]) => a === found[0])[2].includes(markType);
        if (allowed) {
          state.arrangement = found[0];
          delete measure.extras.stack;
        }
      }
      const offsetName = offsetChannel(state);
      const offset = state.encodingExtras[offsetName];
      const color = state.channels.color;
      if (
        markType === "bar" &&
        !state.arrangement &&
        !("stack" in measure.extras) &&
        isObject(offset) &&
        typeof offset.field === "string" &&
        color.field &&
        offset.field === color.field &&
        !("xOffset" in state.encodingExtras && "yOffset" in state.encodingExtras)
      ) {
        state.arrangement = "grouped";
        state.offsetExtras = clone(offset);
        delete state.offsetExtras.field;
        delete state.encodingExtras[offsetName];
      }
    }
    return { state, dataset };
  }

  /** Field names a spec uses that aren't in the data (e.g. made by a
   * transform), so the builder can still offer them. */
  function specFields(state) {
    const fields = [];
    for (const ch of Object.values(state.channels)) {
      if (ch.field && !fields.includes(ch.field)) fields.push(ch.field);
    }
    return fields;
  }

  // -- Writing a spec ---------------------------------------------------------------

  function writeChannel(ch, path, kept) {
    const out = {};
    const extras = extrasApply(ch) ? ch.extras : {};
    if (ch.field) out.field = ch.field;
    const type = ch.type || impliedType(ch);
    if (!(ch.typeImplied && type === impliedType(ch))) out.type = type;
    if (ch.count) out.aggregate = "count";
    else if (ch.aggregate) out.aggregate = ch.aggregate;
    if (ch.bin && !ch.count) out.bin = true;
    if (ch.timeUnit && !ch.count) out.timeUnit = (ch.utc ? "utc" : "") + ch.timeUnit;
    if (ch.sort === "none") out.sort = null;
    else if (ch.sort) out.sort = ch.sort;
    if (ch.title) out.title = ch.title;
    for (const [key, value] of Object.entries(extras)) {
      // A kept value wins over the control, which shows "Custom"
      out[key] = clone(value);
      kept.push(`${path}.${key}`);
    }
    return out;
  }

  function ordered(object, order) {
    const out = {};
    for (const key of order) if (key in object) out[key] = object[key];
    for (const key of Object.keys(object)) if (!(key in out)) out[key] = object[key];
    return out;
  }

  /**
   * The Vega-Lite spec for a state, loading `dataset` by name. Returns
   * {spec, kept}: `kept` lists the paths (e.g. "encoding.x.axis") of the
   * extras it wrote, kept from the spec the builder opened.
   */
  function toSpec(state, dataset) {
    const kept = [];
    const spec = { $schema: state.schema || VL_SCHEMA };
    for (const [key, value] of Object.entries(state.extras)) {
      spec[key] = clone(value);
      kept.push(key);
    }
    if (!("title" in state.extras) && state.title) spec.title = state.title;
    if (!("width" in state.extras) && state.width !== "") spec.width = state.width;
    if (!("height" in state.extras) && state.height !== "") spec.height = state.height;
    spec.data = { name: dataset };

    // The mark
    const mark = { type: state.mark };
    if (state.tooltip) mark.tooltip = true;
    if (state.point && (state.mark === "line" || state.mark === "area")) mark.point = true;
    if (state.donut && state.mark === "arc") mark.innerRadius = state.innerRadius;
    if (markExtrasApply(state)) {
      for (const [key, value] of Object.entries(state.markExtras)) {
        mark[key] = clone(value);
        kept.push(`mark.${key}`);
      }
    }
    spec.mark = Object.keys(mark).length === 1 ? state.mark : mark;

    // Encodings
    const encoding = {};
    const channelPaths = {};
    for (const name of channelsFor(state.mark)) {
      const ch = state.channels[name];
      if (hasField(ch)) {
        const channelKept = [];
        encoding[name] = writeChannel(ch, `encoding.${name}`, channelKept);
        channelPaths[name] = channelKept;
      }
    }
    if (state.mark === "bar" || state.mark === "area") {
      const measure = measureChannel(state);
      const value = STACK_VALUES[state.arrangement];
      if (state.arrangement in STACK_VALUES && encoding[measure] && !("stack" in encoding[measure])) {
        encoding[measure].stack = value;
      }
      const color = encoding.color;
      if (state.arrangement === "grouped" && state.mark === "bar" && color?.field) {
        encoding[offsetChannel(state)] = { field: color.field, ...clone(state.offsetExtras) };
        for (const key of Object.keys(state.offsetExtras)) {
          kept.push(`encoding.${offsetChannel(state)}.${key}`);
        }
      }
    }
    for (const paths of Object.values(channelPaths)) kept.push(...paths);
    for (const [name, def] of Object.entries(state.encodingExtras)) {
      if (name in encoding) continue; // replaced by a builder channel
      encoding[name] = clone(def);
      kept.push(`encoding.${name}`);
    }
    spec.encoding = ordered(encoding, ENCODING_ORDER);
    return { spec: ordered(spec, TOP_ORDER), kept };
  }

  /** Is the arrangement value for this state one the spec set and the
   * control can't show ("Custom")? */
  function customArrangement(state) {
    const ch = state.channels[measureChannel(state)];
    return extrasApply(ch) && "stack" in ch.extras;
  }

  admin.chartSpec = {
    VL_SCHEMA,
    MARKS,
    CHANNELS,
    TYPES,
    AGGREGATES,
    TIME_UNITS,
    ARRANGEMENTS,
    SORT_CHANNELS,
    COUNT,
    describeColumns,
    emptyState,
    emptyChannel,
    initialState,
    suggest,
    applySuggestion,
    channelsFor,
    setField,
    hasField,
    extrasApply,
    markExtrasApply,
    measureChannel,
    customArrangement,
    impliedType,
    fromSpec,
    toSpec,
    specFields,
    sameSpec,
    canonical,
    clone,
    isObject,
  };
})();
