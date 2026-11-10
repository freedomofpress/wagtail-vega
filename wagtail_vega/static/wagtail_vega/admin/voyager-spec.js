/* wagtail-vega admin: Vega Voyager's specs, and when to write them.
 *
 * Voyager (the chart editor's "Voyager" mode, see voyager-editor.js) only
 * knows Vega-Lite 2, and only single views: a mark with field encodings.
 * This file converts between that and the Vega-Lite 6 specs charts use. No
 * DOM, so it's unit-tested in Node (tests/js/voyager-spec.test.mjs).
 *
 * - toVoyagerSpec(spec): the parts of a spec Voyager can open, or null.
 * - fromVoyagerSpec(voyagerSpec, datasetName, previous): Voyager's chart as
 *   Vega-Lite 6 that loads the dataset by name ({"data": {"name": ...}},
 *   never inline data). The title, description, size, autosize, padding,
 *   background and config are kept from `previous`, the field's spec.
 * - voyagerProblems(spec, datasetName): what opening `spec` in Voyager would
 *   lose: {blocked} if Voyager can't open it at all (a Vega spec, layers,
 *   concatenated or faceted views, a mark it doesn't have...), else {lost},
 *   the parts that a change made in Voyager would drop (grouped bars become
 *   stacked; params, selections, transforms, axis and legend settings...).
 *   Found by comparing the spec with its round trip through the conversion.
 * - Baseline: decides when Voyager's reports are the editor's changes, and
 *   so are written to the field. See its comment.
 *
 * Messages are {key, vars}, translated by chart-builder.js (the "voyager.*"
 * keys in builder_strings.py).
 *
 * Exposed as window.wagtailVegaAdmin.voyagerSpec.
 */
(() => {
  "use strict";

  const admin = (window.wagtailVegaAdmin = window.wagtailVegaAdmin || {});

  const VL_SCHEMA = "https://vega.github.io/schema/vega-lite/v6.json";
  // Kept from the field's current spec when Voyager's chart replaces it
  const CARRY_OVER = ["title", "description", "width", "height", "autosize", "padding", "background"];
  // Encoding channels Voyager (Vega-Lite 2) understands
  const VOYAGER_CHANNELS = new Set([
    "x", "y", "x2", "y2", "color", "opacity", "size", "shape", "text", "tooltip", "detail",
    "row", "column",
  ]);
  // Vega-Lite 2's marks
  const VOYAGER_MARKS = new Set(["area", "bar", "line", "point", "text", "tick", "rect", "rule", "circle", "square"]);
  const FIELD_TYPES = new Set(["quantitative", "nominal", "ordinal", "temporal"]);
  // Views Voyager can't open
  const COMPOSITE = ["layer", "concat", "hconcat", "vconcat", "facet", "repeat", "spec"];

  const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const clone = (v) => JSON.parse(JSON.stringify(v));

  /** JSON with object keys sorted, to compare specs whatever their key order. */
  function canonical(value) {
    return JSON.stringify(value === undefined ? null : value, (key, v) =>
      isObject(v) ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]])) : v,
    );
  }

  const same = (a, b) => canonical(a) === canonical(b);

  /** Recursively merge objects; later arguments win (as spec.deep_merge). */
  function deepMerge(a, b) {
    const out = clone(a);
    for (const [k, v] of Object.entries(b)) {
      out[k] = isObject(v) && isObject(out[k]) ? deepMerge(out[k], v) : clone(v);
    }
    return out;
  }

  const isVega = (spec) => typeof spec?.$schema === "string" && spec.$schema.includes("/vega/");
  const isVegaLite = (spec) =>
    isObject(spec) && typeof spec.$schema === "string" && spec.$schema.includes("/vega-lite/");
  const markType = (mark) => (isObject(mark) ? mark.type : mark);

  // -- Conversion -------------------------------------------------------------

  /** The parts of a Vega-Lite spec that Voyager can open: a single view's
   * mark and field encodings. Returns null if there's nothing to open. */
  function toVoyagerSpec(spec) {
    if (!isVegaLite(spec) || !isObject(spec.encoding)) return null;
    if (COMPOSITE.some((key) => key in spec)) return null;
    const mark = markType(spec.mark);
    if (typeof mark !== "string" || !VOYAGER_MARKS.has(mark)) return null;
    const encoding = {};
    for (const [channel, def] of Object.entries(spec.encoding)) {
      if (!VOYAGER_CHANNELS.has(channel) || !isObject(def)) continue;
      if (def.aggregate === "count") {
        encoding[channel] = { aggregate: "count", field: "*", type: "quantitative" };
        continue;
      }
      if (typeof def.field !== "string" || !FIELD_TYPES.has(def.type)) continue;
      const out = { field: def.field, type: def.type };
      if (typeof def.aggregate === "string") out.aggregate = def.aggregate;
      if (def.bin === true || isObject(def.bin)) out.bin = true;
      if (typeof def.timeUnit === "string") out.timeUnit = def.timeUnit;
      encoding[channel] = out;
    }
    return Object.keys(encoding).length ? { mark, encoding } : null;
  }

  /** Voyager's (Vega-Lite 2) spec as Vega-Lite v6 that loads `datasetName`
   * by name. Presentation settings such as the title and width are kept
   * from `previous`, the field's current spec, and its config is merged
   * under Voyager's. */
  function fromVoyagerSpec(voyagerSpec, datasetName, previous) {
    const spec = clone(voyagerSpec);
    for (const key of ["$schema", "data", "datasets"]) delete spec[key];
    if (isObject(spec.encoding)) {
      for (const def of Object.values(spec.encoding)) {
        if (!isObject(def)) continue;
        // Vega-Lite 2 wrote count as {"aggregate": "count", "field": "*"}
        if (def.aggregate === "count" && def.field === "*") delete def.field;
        for (const [key, value] of Object.entries(def)) {
          if (isObject(value) && Object.keys(value).length === 0) delete def[key];
        }
      }
    }
    const out = { $schema: VL_SCHEMA };
    const prev = isVegaLite(previous) ? previous : null;
    for (const key of CARRY_OVER) {
      if (prev && key in prev && !(key in spec)) out[key] = clone(prev[key]);
    }
    out.data = { name: datasetName };
    Object.assign(out, spec);
    if (prev && isObject(prev.config)) out.config = deepMerge(prev.config, spec.config || {});
    return out;
  }

  /** The spec as the field gets it: formatted as the rest of the editor
   * writes specs. */
  const specText = (spec) => JSON.stringify(spec, null, 2);

  // -- What Voyager would lose ----------------------------------------------------

  /** Paths (arrays of keys) of the parts of `original` that `converted`
   * doesn't have, or has with another value. What `converted` adds isn't
   * reported. Encodings are compared channel by channel, the mark and the
   * config property by property. */
  function lostPaths(original, converted) {
    const lost = [];
    const conv = isObject(converted) ? converted : {};
    const leaves = (a, b, path) => {
      for (const [key, value] of Object.entries(a)) {
        if (isObject(value) && isObject(b?.[key])) leaves(value, b[key], [...path, key]);
        else if (!isObject(b) || !(key in b) || !same(value, b[key])) lost.push([...path, key]);
      }
    };
    for (const [key, value] of Object.entries(original)) {
      if (key === "$schema") continue;
      if (key === "encoding" && isObject(value) && isObject(conv.encoding)) {
        for (const [channel, def] of Object.entries(value)) {
          const other = conv.encoding[channel];
          if (other === undefined) lost.push(["encoding", channel]);
          else if (isObject(def) && isObject(other)) {
            for (const [prop, v] of Object.entries(def)) {
              if (!(prop in other) || !same(v, other[prop])) lost.push(["encoding", channel, prop]);
            }
          } else if (!same(def, other)) lost.push(["encoding", channel]);
        }
      } else if (key === "mark" && markType(value) === markType(conv.mark)) {
        const a = isObject(value) ? value : { type: value };
        const b = isObject(conv.mark) ? conv.mark : { type: conv.mark };
        for (const [prop, v] of Object.entries(a)) {
          if (!(prop in b) || !same(v, b[prop])) lost.push(["mark", prop]);
        }
      } else if (key === "config" && isObject(value)) {
        leaves(value, conv.config, ["config"]);
      } else if (!(key in conv) || !same(value, conv[key])) {
        lost.push([key]);
      }
    }
    return lost;
  }

  // The order the editor sees what would be lost in: what changes the chart
  // most first, then single settings
  const LOST_ORDER = [
    "voyager.lost.grouped", "voyager.lost.params", "voyager.lost.transform", "voyager.lost.data",
    "voyager.lost.channel", "voyager.lost.path",
  ];

  /** `lostPaths`, as messages for the editor, most important first. */
  function lostMessages(paths) {
    const messages = [];
    const seen = new Set();
    const add = (key, vars = {}) => {
      const id = canonical([key, vars]);
      if (seen.has(id)) return;
      seen.add(id);
      messages.push({ key, vars });
    };
    for (const path of paths) {
      const [top, channel] = path;
      if (top === "encoding" && (channel === "xOffset" || channel === "yOffset")) {
        add("voyager.lost.grouped");
      } else if (top === "params" || top === "transform" || top === "data") {
        add(`voyager.lost.${top}`);
      } else if (top === "encoding" && path.length === 2) {
        add("voyager.lost.channel", { channel });
      } else {
        add("voyager.lost.path", { path: path.join(".") });
      }
    }
    // A stable sort: paths stay in the spec's order
    return messages.sort((a, b) => LOST_ORDER.indexOf(a.key) - LOST_ORDER.indexOf(b.key));
  }

  /** Why Voyager can't open `spec` at all ({key, vars}), or null. */
  function blockedReason(spec) {
    if (!isObject(spec)) return { key: "voyager.blocked.notObject" };
    if (isVega(spec)) return { key: "voyager.blocked.vega" };
    if (!isVegaLite(spec)) return { key: "voyager.blocked.noSchema" };
    const composite = COMPOSITE.find((key) => key in spec);
    if (composite) return { key: "voyager.blocked.composite", vars: { key: composite } };
    const mark = markType(spec.mark);
    if (typeof mark !== "string") return { key: "voyager.blocked.noMark" };
    if (!VOYAGER_MARKS.has(mark)) return { key: "voyager.blocked.mark", vars: { mark } };
    if (!toVoyagerSpec(spec)) return { key: "voyager.blocked.encoding" };
    return null;
  }

  /** What opening `spec` in Voyager, with `datasetName`'s data, would
   * lose: {blocked: {key, vars}} if it can't open it, else {lost: [{key,
   * vars}]} (empty if nothing would be lost), and the spec to open it with
   * (`voyager`). Pass `reported`, the spec Voyager reported once it had
   * opened it, to include what Voyager itself changed. */
  function voyagerProblems(spec, datasetName, reported) {
    const blocked = blockedReason(spec);
    if (blocked) return { blocked, lost: [], voyager: null };
    const voyager = toVoyagerSpec(spec);
    const paths = lostPaths(spec, fromVoyagerSpec(voyager, datasetName, spec));
    if (isObject(reported)) {
      for (const path of lostPaths(spec, fromVoyagerSpec(reported, datasetName, spec))) {
        if (!paths.some((p) => p.join("\u0000") === path.join("\u0000"))) paths.push(path);
      }
    }
    return { blocked: null, lost: lostMessages(paths), voyager };
  }

  // -- When to write ------------------------------------------------------------------

  /** Voyager reports its chart whenever its state changes, including while
   * it opens a spec, and it changes what it's given (Vega-Lite 2 has no
   * grouped bars, for example). So the field mustn't change just because
   * Voyager reported something.
   *
   * One Baseline per load of Voyager (its data, and the field's chart if it
   * can open it). The specs Voyager reports before the editor has done
   * anything in it (`user` false: no click, key press or drop in the frame
   * since the load) are the baseline: what Voyager shows of the field's
   * chart. After that, a report that differs from the baseline is a change:
   * it's written. A report that's the baseline again (e.g. the editor
   * undid their changes in Voyager) puts back the field's text from when
   * Voyager loaded, exactly. A report with no chart (`spec` null: empty
   * shelves, or wildcards showing several charts) writes nothing.
   *
   * `report()` returns the text to write, or null for nothing.
   *
   * With `changed` (e.g. the editor chose another dataset for Voyager), the
   * load itself is a change: every chart Voyager reports is written. */
  class Baseline {
    constructor({ text, previous, datasetName, changed = false }) {
      this.text = text;
      this.previous = previous;
      this.datasetName = datasetName;
      this.changed = changed;
      this.baseline = undefined;
      this.written = false;
    }

    /** The spec text a report from Voyager means for the field, or null. */
    report(spec, { user = false } = {}) {
      const key = canonical(isObject(spec) ? spec : null);
      if (!this.changed && !user) {
        // Voyager opening (or settling on) the field's chart
        if (!this.written) this.baseline = key;
        return null;
      }
      if (!isObject(spec)) return null;
      if (!this.changed && key === this.baseline) {
        if (!this.written) return null;
        this.written = false;
        return this.text;
      }
      this.written = true;
      return specText(fromVoyagerSpec(spec, this.datasetName, this.previous));
    }

    /** True once a report has been written (and not undone). */
    get dirty() {
      return this.written;
    }
  }

  admin.voyagerSpec = {
    VL_SCHEMA,
    toVoyagerSpec,
    fromVoyagerSpec,
    voyagerProblems,
    lostPaths,
    lostMessages,
    blockedReason,
    specText,
    canonical,
    Baseline,
  };
})();
