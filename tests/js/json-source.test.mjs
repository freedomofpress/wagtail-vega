import assert from "node:assert/strict";
import { test } from "node:test";
import { loadCodeEditor, plain } from "./load.mjs";

const { window } = loadCodeEditor();
const { parse, lineColumn, find, rangeForPath, resolveDotted, splitMessage } =
  window.wagtailVegaAdmin.jsonSource;

const SPEC = `{
  "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
  "data": {"name": "source"},
  "mark": "bar",
  "encoding": {
    "x": {"field": "a", "type": "nominl"},
    "y": {"field": "b", "type": "quantitative"}
  },
  "layer": [{"mark": "point"}, {"mark": {"type": "line", "colour": "red"}}],
  "a.b": {"c": 1}
}`;

const textAt = (text, range) => text.slice(range.from, range.to);
const root = parse(SPEC).root;

test("parse accepts everything JSON.parse accepts", () => {
  const samples = [
    "0", "-1.5e+10", '"a\\"b\\u00e9\\n"', "true", "null", "[]", "{}", " [1, [2, {}], {\"a\": null}] ",
    SPEC,
  ];
  for (const text of samples) {
    JSON.parse(text);
    assert.equal(parse(text).error, null, text);
  }
  assert.deepEqual(plain(parse("   ")), { root: null, error: null });
});

test("parse records where values and keys are", () => {
  assert.equal(root.type, "object");
  const encoding = root.entries.find((e) => e.key === "encoding");
  assert.equal(textAt(SPEC, { from: encoding.keyFrom, to: encoding.keyTo }), '"encoding"');
  const x = encoding.value.entries[0].value;
  assert.equal(textAt(SPEC, x), '{"field": "a", "type": "nominl"}');
});

// Each case: text, expected message (regex), and the text the error covers
const SYNTAX_ERRORS = [
  ["[oops", /Expected a value, but found 'oops'/, "oops"],
  ['{"a": 1,}', /Trailing commas/, ","],
  ["[1, 2,]", /Trailing commas/, ","],
  ['{"a": 1 "b": 2}', /Expected a comma or \}, but found "b"/, '"b"'],
  ["{'a': 1}", /double quotes/, "'a'"],
  ['{"a" 1}', /Expected a colon/, "1"],
  ['{"a": 01}', /01 isn't a valid JSON number/, "01"],
  ['{"a": NaN}', /NaN isn't allowed/, "NaN"],
  ['{"a": "x\\q"}', /Invalid escape sequence \\q/, "\\q"],
  ['{"a": "unclosed\n}', /isn't closed before the end of the line/, '"unclosed'],
  ['{"a": 1', /Expected a comma or \}, but the text ended/, ""],
  ['{"a": 1} x', /Unexpected text after the end/, "x"],
  ['{"a": tru}', /Expected a value, but found 'tru'/, "tru"],
];

test("syntax errors say what's wrong and where", () => {
  for (const [text, message, covered] of SYNTAX_ERRORS) {
    const { root: r, error } = parse(text);
    assert.equal(r, null, text);
    assert.match(error.message, message, text);
    assert.equal(textAt(text, error), covered, text);
    assert.throws(() => JSON.parse(text), SyntaxError, `JSON.parse should reject ${text}`);
  }
});

test("parse can start after a byte order mark", () => {
  assert.equal(parse('\ufeff[{"a": 1}]', 1).error, null);
  assert.notEqual(parse('\ufeff[{"a": 1}]').error, null);
});

test("lineColumn counts from 1", () => {
  assert.deepEqual(plain(lineColumn("ab\ncd", 0)), { line: 1, column: 1 });
  assert.deepEqual(plain(lineColumn("ab\ncd", 4)), { line: 2, column: 2 });
});

test("find follows keys and indices", () => {
  assert.equal(find(root, ["layer", 1, "mark", "type"]).complete, true);
  const missing = find(root, ["encoding", "z", "type"]);
  assert.equal(missing.complete, false);
  assert.equal(textAt(SPEC, { from: missing.entry.keyFrom, to: missing.entry.keyTo }), '"encoding"');
});

test("rangeForPath underlines scalars whole", () => {
  assert.equal(textAt(SPEC, rangeForPath(root, ["encoding", "x", "type"])), '"nominl"');
  assert.equal(textAt(SPEC, rangeForPath(root, ["layer", "1", "mark", "type"])), '"line"');
  assert.equal(textAt(SPEC, rangeForPath(root, ["mark"])), '"bar"');
});

test("rangeForPath underlines the key of an object or array value", () => {
  assert.equal(textAt(SPEC, rangeForPath(root, ["encoding", "x"])), '"x"');
  assert.equal(textAt(SPEC, rangeForPath(root, ["layer"])), '"layer"');
  // An array item has no key: its opening bracket
  assert.equal(textAt(SPEC, rangeForPath(root, ["layer", 0])), "{");
  // The whole spec
  assert.equal(textAt(SPEC, rangeForPath(root, [])), "{");
});

test("rangeForPath points at the unexpected property", () => {
  const message = "Additional properties are not allowed ('colour' was unexpected)";
  assert.equal(textAt(SPEC, rangeForPath(root, ["layer", 1, "mark"], message)), '"colour"');
  const several = "Additional properties are not allowed ('colour', 'zz' were unexpected)";
  assert.equal(textAt(SPEC, rangeForPath(root, ["layer", 1, "mark"], several)), '"colour"');
});

test("rangeForPath falls back to the deepest part of the path that exists", () => {
  assert.equal(textAt(SPEC, rangeForPath(root, ["encoding", "x", "missing"])), '"x"');
});

test("resolveDotted uses the document to split the path", () => {
  assert.deepEqual(plain(resolveDotted(root, "encoding.x.type")), ["encoding", "x", "type"]);
  assert.deepEqual(plain(resolveDotted(root, "layer.1.mark.type")), ["layer", 1, "mark", "type"]);
  assert.deepEqual(plain(resolveDotted(root, "a.b.c")), ["a.b", "c"]);
  assert.equal(resolveDotted(root, "layer.5"), null);
  assert.equal(resolveDotted(root, "encoding.z"), null);
});

test("splitMessage separates a leading path from the message", () => {
  assert.deepEqual(
    plain(splitMessage(root, "encoding.x.type: 'nominl' is not valid under any of the given schemas")),
    { path: ["encoding", "x", "type"], message: "'nominl' is not valid under any of the given schemas" },
  );
  assert.deepEqual(plain(splitMessage(root, "'mark' is a required property")), {
    path: null,
    message: "'mark' is a required property",
  });
  // "Couldn't read this data" isn't a path in the document
  assert.equal(splitMessage(root, "Couldn't read this data: oops").path, null);
  assert.equal(splitMessage(null, "encoding: x").path, null);
});
