import assert from "node:assert/strict";
import { test } from "node:test";
import { loadAdmin, plain } from "./load.mjs";

const { window, registered } = loadAdmin();
const { detectFormat, parseDelimited, valueType, columnType, summarise, coerce, parseRows } =
  window.wagtailVegaAdmin.dataFormat;

test("registers the telepath definition", () => {
  assert.equal(typeof registered["wagtail_vega.blocks.DatasetBlock"], "function");
});

// Must match wagtail_vega.data.detect_format (see tests/test_data.py)
test("detectFormat", () => {
  assert.equal(detectFormat("a,b\n1,2"), "csv");
  assert.equal(detectFormat("a\tb\n1\t2"), "tsv");
  assert.equal(detectFormat("a\tb,c\n1\t2"), "tsv");
  assert.equal(detectFormat("a;b;c\n1;2;3"), "ssv");
  assert.equal(detectFormat('﻿  [{"a": 1}]'), "json");
  assert.equal(detectFormat('{"values": []}'), "json");
  assert.equal(detectFormat("single\n1"), "csv");
});

test("parseDelimited handles quotes, escaped quotes and CRLF", () => {
  assert.deepEqual(plain(parseDelimited('a,b\r\n"x, y","say ""hi"""\r\n', ",")), [
    ["a", "b"],
    ["x, y", 'say "hi"'],
  ]);
  assert.deepEqual(plain(parseDelimited('a\n"multi\nline"', ",")), [["a"], ["multi\nline"]]);
});

// Must match wagtail_vega.data._coerce (see tests/test_data.py)
test("valueType mirrors the server's type inference", () => {
  const cases = {
    "1": "number", "0": "number", "0.5": "number", "1e3": "number", ".5": "number",
    "1,234": "number", "-1,234.5": "number",
    "007": "text", "02134": "text", "1_000": "text", "nan": "text", "12,34": "text",
    "10%": "text", "$5": "text",
    "TRUE": "true/false", "false": "true/false",
    "2026-01-01": "date", "2026-01": "date", "2026-01-01T10:00:00Z": "date",
  };
  for (const [raw, type] of Object.entries(cases)) assert.equal(valueType(raw), type, raw);
  assert.equal(valueType(""), null);
  assert.equal(valueType(undefined), null);
});

test("columnType", () => {
  assert.equal(columnType(["1", "2", ""]), "number");
  assert.equal(columnType(["1", "x"]), "mixed");
  assert.equal(columnType(["", ""]), "empty");
});

test("summarise: spreadsheet paste", () => {
  const result = summarise("quarter\trequests\nQ1\t1,200\nQ2\t950\n");
  assert.equal(result.ok, true);
  assert.match(result.message, /^Tab-separated/);
  assert.match(result.message, /2 rows · quarter \(text\), requests \(number\)$/);
  assert.equal(result.warning, "");
});

test("summarise: ragged rows warn with the line number", () => {
  const result = summarise("year,count\n2024,10\n2025\n2026,12");
  assert.equal(result.ok, true);
  assert.equal(result.warning, "Line 3 has 1 value but there are 2 columns.");
});

test("summarise: JSON", () => {
  const result = summarise('[{"zip": "02134", "n": 3, "ok": true, "when": "2026-01-01"}]');
  assert.equal(result.message, "JSON · 1 row · zip (text), n (number), ok (true/false), when (date)");
  assert.equal(summarise('{"values": [{"a": 1}]}').ok, true);
});

test("summarise: errors", () => {
  assert.equal(summarise("   "), null);
  assert.match(summarise("[oops").message, /couldn't be read/);
  assert.equal(summarise('{"a": 1}').message, "JSON data must be an array of rows.");
  assert.match(summarise("header_only").message, /No data rows/);
});

// parseRows / coerce must match wagtail_vega.data (same cases as tests/test_data.py),
// so Voyager sees the values the chart will.
test("parseRows infers types like parse_delimited", () => {
  assert.deepEqual(plain(parseRows("a,b,c,d\nx,1,2.5,true\ny,,nan,2024-01-01\n")), [
    { a: "x", b: 1, c: 2.5, d: true },
    { a: "y", b: null, c: "nan", d: "2024-01-01" },
  ]);
});

test("parseRows: spreadsheet paste", () => {
  assert.deepEqual(plain(parseRows("zip\tcount\tshare\n02134\t1,200\t12%\n10001\t950.5\t8%\n")), [
    { zip: "02134", count: 1200, share: "12%" },
    { zip: 10001, count: 950.5, share: "8%" },
  ]);
});

test("parseRows: BOM, JSON, explicit format and empty input", () => {
  assert.deepEqual(plain(parseRows("﻿a\tb\n1\t2\n")), [{ a: 1, b: 2 }]);
  assert.deepEqual(plain(parseRows('[{"a": 1}]')), [{ a: 1 }]);
  assert.deepEqual(plain(parseRows('{"values": [1]}')), [1]);
  assert.deepEqual(plain(parseRows("a;b\n1;2", "csv")), [{ "a;b": "1;2" }]);
  assert.deepEqual(plain(parseRows("a\tb\n1\t2", "tsv")), [{ a: 1, b: 2 }]);
  assert.deepEqual(plain(parseRows("   ")), []);
  assert.deepEqual(plain(parseRows(null)), []);
  assert.throws(() => parseRows('{"a": 1}'), /array of rows/);
  assert.throws(() => parseRows("[oops"));
});

test("parseRows: short, long and blank rows (like csv.DictReader)", () => {
  assert.deepEqual(plain(parseRows("a,b\n1\n\n2,3,4\n")), [
    { a: 1, b: null },
    { a: 2, b: 3 },
  ]);
});

test("coerce edge cases", () => {
  const cases = [
    ["007", "007"], ["0", 0], ["0.5", 0.5], ["1e3", 1000], ["1_000", "1_000"], ["nan", "nan"],
    ["12,34", "12,34"], ["-1,234.5", -1234.5], [" 5 ", 5], ["TRUE", true], ["", null], ["  ", null],
  ];
  for (const [raw, value] of cases) assert.equal(coerce(raw), value, raw);
});

test("summarise: long column lists are truncated", () => {
  const header = Array.from({ length: 10 }, (_, i) => `c${i}`).join(",");
  const result = summarise(`${header}\n${"1,".repeat(9)}1`);
  assert.match(result.message, /, and 2 more$/);
});

// -- Problems marked in the paste field's editor ------------------------------

const { diagnose } = window.wagtailVegaAdmin.dataFormat;
const marked = (text) => diagnose(text).map((d) => [d.severity, text.slice(d.from, d.to), d.message]);

test("diagnose: ragged rows are marked on their line", () => {
  const text = "year,count\n2024,10\n2025\n2026,12,9\n";
  assert.deepEqual(plain(marked(text)), [
    ["warning", "2025", "Line 3 has 1 value but there are 2 columns."],
    ["warning", "2026,12,9", "Line 4 has 3 values but there are 2 columns."],
  ]);
  assert.match(summarise(text).warning, /^Line 3 has 1 value .* 1 more row has problems too\.$/);
});

test("diagnose: line numbers count leading blank lines, CRLF and quoted newlines", () => {
  assert.deepEqual(plain(marked("\n\na\tb\r\n1\r\n")), [
    ["warning", "1", "Line 4 has 1 value but there are 2 columns."],
  ]);
  assert.deepEqual(plain(marked('a,b\n"x\ny",1\n2\n')), [
    ["warning", "2", "Line 4 has 1 value but there are 2 columns."],
  ]);
});

test("diagnose: blank lines are skipped, like the server's csv module", () => {
  assert.deepEqual(plain(diagnose("a,b\n1,2\n\n3,4\n")), []);
  assert.match(summarise("a,b\n1,2\n\n3,4\n").message, /2 rows/);
});

test("diagnose: JSON syntax errors at their location", () => {
  const text = '[\n  {"a": 1},\n  {"a": 2,}\n]';
  assert.deepEqual(plain(marked(text)), [["error", ",", "Trailing commas aren't allowed in JSON"]]);
  assert.equal(
    summarise(text).message,
    "This looks like JSON but couldn't be read: Trailing commas aren't allowed in JSON (line 3, column 10).",
  );
});

test("diagnose: JSON that isn't rows", () => {
  assert.deepEqual(plain(marked('{"a": 1}')), [["error", "{", "JSON data must be an array of rows."]]);
  assert.deepEqual(plain(marked('{"values": [{"a": 1}, 2]}')), [
    ["warning", "2", 'Each row should be an object, like {"name": value}.'],
  ]);
  assert.deepEqual(plain(diagnose('﻿[{"a": 1}]')), []);
});

test("diagnose: nothing to say", () => {
  assert.deepEqual(plain(diagnose("")), []);
  assert.deepEqual(plain(diagnose("quarter\trequests\nQ1\t1,200\n")), []);
});
