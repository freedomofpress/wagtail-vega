import assert from "node:assert/strict";
import { test } from "node:test";
import { loadAdmin, plain } from "./load.mjs";

const { window, registered } = loadAdmin();
const { detectFormat, parseDelimited, valueType, columnType, summarise } =
  window.wagtailVegaAdmin._internal;

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

test("summarise: long column lists are truncated", () => {
  const header = Array.from({ length: 10 }, (_, i) => `c${i}`).join(",");
  const result = summarise(`${header}\n${"1,".repeat(9)}1`);
  assert.match(result.message, /, and 2 more$/);
});
