import assert from "node:assert/strict";
import { test } from "node:test";
import { loadCodeEditor, plain } from "./load.mjs";

const { window, registered } = loadCodeEditor();
const { jsonDiagnostics, pathDiagnostics, messageDiagnostics, diff } =
  window.wagtailVegaAdmin.codeEditor._internal;

const SPEC = `{
  "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
  "data": {"url": "https://evil.example/data.csv"},
  "mark": "bar",
  "encoding": {"x": {"field": "a", "type": "nominl"}}
}`;
const covered = (text, d) => text.slice(d.from, d.to);

test("registers the widget and block definitions", () => {
  assert.equal(typeof registered["wagtail_vega.widgets.CodeEditor"], "function");
  assert.equal(typeof registered["wagtail_vega.blocks.CodeFieldBlock"], "function");
});

test("jsonDiagnostics: one error, where the problem is", () => {
  assert.deepEqual(plain(jsonDiagnostics(SPEC)), []);
  const [d, ...rest] = jsonDiagnostics('{"a": [1, 2,]}');
  assert.equal(rest.length, 0);
  assert.equal(d.severity, "error");
  assert.equal(covered('{"a": [1, 2,]}', d), ",");
});

test("pathDiagnostics maps the endpoint's paths to ranges", () => {
  const diagnostics = pathDiagnostics(SPEC, [
    { path: ["encoding", "x", "type"], message: "'nominl' is not valid" },
    { path: ["data", "url"], message: "Loading data from https://evil.example/data.csv is not allowed." },
    { path: [], message: "'mark' is a required property" },
  ]);
  assert.deepEqual(
    diagnostics.map((d) => [covered(SPEC, d), d.message]),
    [
      ['"nominl"', "'nominl' is not valid"],
      ['"https://evil.example/data.csv"', "Loading data from https://evil.example/data.csv is not allowed."],
      ["{", "'mark' is a required property"],
    ],
  );
  assert.deepEqual(plain(pathDiagnostics("{oops", [{ path: [], message: "x" }])), []);
});

test("messageDiagnostics parses the leading path of saved errors", () => {
  const diagnostics = messageDiagnostics(SPEC, [
    "encoding.x.type: 'nominl' is not valid under any of the given schemas",
    "data.url: Loading data from https://evil.example/data.csv is not allowed.",
    'The spec needs a "$schema", e.g. "https://vega.github.io/schema/vega-lite/v6.json".',
  ]);
  assert.deepEqual(
    diagnostics.map((d) => [covered(SPEC, d), d.message]),
    [
      ['"nominl"', "'nominl' is not valid under any of the given schemas"],
      ['"https://evil.example/data.csv"', "Loading data from https://evil.example/data.csv is not allowed."],
      ["{", 'The spec needs a "$schema", e.g. "https://vega.github.io/schema/vega-lite/v6.json".'],
    ],
  );
});

test("diff finds the smallest change", () => {
  assert.deepEqual(plain(diff("abcdef", "abXYef")), { from: 2, to: 4, insert: "XY" });
  assert.deepEqual(plain(diff("abc", "abc")), { from: 3, to: 3, insert: "" });
  assert.deepEqual(plain(diff("", "new")), { from: 0, to: 0, insert: "new" });
  assert.deepEqual(plain(diff("aaa", "aa")), { from: 2, to: 3, insert: "" });
  for (const [a, b] of [["x1y", "x22y"], ["{}", '{"a": 1}'], ["same", ""]]) {
    const { from, to, insert } = diff(a, b);
    assert.equal(a.slice(0, from) + insert + a.slice(to), b);
  }
});
