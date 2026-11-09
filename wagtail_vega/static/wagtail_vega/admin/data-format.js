/* wagtail-vega admin: reading pasted data (CSV, TSV, semicolon-separated or
 * JSON) the way the server will, to tell editors what was read and where any
 * problems are.
 *
 * - analyse(text): format, header, rows and problems (with source ranges).
 * - summarise(text): the one-line summary shown under the paste field.
 * - diagnose(text): the problems, for the code editor to mark in place.
 * - parseRows(text, format): typed rows, as the server parses them.
 *
 * Detection and typing mirror wagtail_vega/data.py; keep them in sync.
 * Needs json-source.js. Exposed as window.wagtailVegaAdmin.dataFormat.
 */
(() => {
  "use strict";

  const { jsonSource } = window.wagtailVegaAdmin;

  const DELIMITERS = { tsv: "\t", csv: ",", ssv: ";" }; // ties go to the first
  const FORMAT_LABELS = {
    tsv: "Tab-separated (e.g. copied from a spreadsheet)",
    csv: "Comma-separated",
    ssv: "Semicolon-separated",
    json: "JSON",
  };
  const NUMBER_RE = /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$/;
  const THOUSANDS_RE = /^[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$/;
  const LEADING_ZERO_RE = /^[-+]?0\d/;
  const DATE_RE = /^\d{4}-\d{2}(?:-\d{2})?(?:[T ][\d:.]+(?:Z|[-+][\d:]+)?)?$/;
  const MAX_COLUMNS_LISTED = 8;

  function detectFormat(text) {
    text = text.replace(/^[﻿\r\n ]+/, "");
    if (text[0] === "[" || text[0] === "{") return "json";
    const header = text.split("\n", 1)[0];
    let best = "csv";
    let bestCount = 0;
    for (const [fmt, d] of Object.entries(DELIMITERS)) {
      const count = header.split(d).length - 1;
      if (count > bestCount) [best, bestCount] = [fmt, count];
    }
    return best;
  }

  /** Parse delimited text into rows, and each row's [from, to] in `text`.
   * Blank lines are skipped, as Python's csv module does. */
  function parseDelimitedSpans(text, delimiter) {
    const rows = [];
    const spans = [];
    let row = [];
    let field = "";
    let quoted = false;
    let blank = true; // nothing at all on this line yet
    let rowStart = 0;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (c !== "\n" && c !== "\r") blank = false;
      if (quoted) {
        if (c === '"') {
          if (text[i + 1] === '"') {
            field += '"';
            i++;
          } else quoted = false;
        } else field += c;
      } else if (c === '"') quoted = true;
      else if (c === delimiter) {
        row.push(field);
        field = "";
      } else if (c === "\n" || c === "\r") {
        const rowEnd = i;
        if (c === "\r" && text[i + 1] === "\n") i++;
        if (!blank) {
          row.push(field);
          rows.push(row);
          spans.push([rowStart, rowEnd]);
        }
        blank = true;
        row = [];
        field = "";
        rowStart = i + 1;
      } else field += c;
    }
    if (field !== "" || row.length) {
      row.push(field);
      rows.push(row);
      spans.push([rowStart, text.length]);
    }
    return { rows, spans };
  }

  function parseDelimited(text, delimiter) {
    return parseDelimitedSpans(text, delimiter).rows;
  }

  function valueType(raw) {
    const v = String(raw ?? "").trim();
    if (v === "") return null;
    if (/^(true|false)$/i.test(v)) return "true/false";
    if (LEADING_ZERO_RE.test(v)) return "text";
    if (NUMBER_RE.test(v) || THOUSANDS_RE.test(v)) return "number";
    if (DATE_RE.test(v)) return "date";
    return "text";
  }

  function columnType(values) {
    const types = new Set(values.map(valueType).filter(Boolean));
    if (types.size === 0) return "empty";
    if (types.size === 1) return [...types][0];
    return "mixed";
  }

  // Mirrors wagtail_vega.data._coerce: numbers, booleans and blanks become
  // typed values; leading-zero codes and everything else stay as text.
  function coerce(value) {
    const stripped = value.trim();
    if (stripped === "") return null;
    const lowered = stripped.toLowerCase();
    if (lowered === "true" || lowered === "false") return lowered === "true";
    if (LEADING_ZERO_RE.test(stripped)) return value;
    let number = stripped;
    if (THOUSANDS_RE.test(stripped)) number = stripped.replaceAll(",", "");
    else if (!NUMBER_RE.test(stripped)) return value;
    return Number(number);
  }

  /** Rows (objects) from CSV/TSV/JSON text, typed exactly as the server's
   * wagtail_vega.data.parse_text does, for the chart builder.
   * `format` is "csv", "tsv", "json", or empty to detect it. Throws on JSON
   * that isn't an array of rows. Delimited text works like csv.DictReader:
   * short rows are padded with null and extra cells are dropped. */
  function parseRows(text, format) {
    text = String(text ?? "").replace(/^﻿/, "");
    if (!text.trim()) return [];
    const fmt = format || detectFormat(text);
    if (fmt === "json") {
      let data = JSON.parse(text);
      if (data && typeof data === "object" && !Array.isArray(data) && "values" in data) {
        data = data.values;
      }
      if (!Array.isArray(data)) throw new Error("JSON data must be an array of rows.");
      return data;
    }
    const [header = [], ...rows] = parseDelimited(text.trim(), DELIMITERS[fmt] ?? ",");
    return rows.map((row) => Object.fromEntries(header.map((name, i) => [name, coerce(row[i] ?? "")])));
  }

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  /**
   * Read pasted text. Returns null for blank text, otherwise
   * {format, header, rows, error, problems}: `error` is a message if the data
   * can't be used at all; `problems` are {from, to, severity, message} with
   * offsets into `text`.
   */
  function analyse(text) {
    if (!text.trim()) return null;
    const format = detectFormat(text);
    const result = { format, header: [], rows: [], error: null, problems: [] };
    const problem = (severity, message, from, to) => {
      result.problems.push({ from, to, severity, message });
    };

    if (format === "json") {
      // Like data.py, a leading byte order mark is ignored
      const start = text[0] === "﻿" ? 1 : 0;
      const { root, error } = jsonSource.parse(text, start);
      if (error) {
        const { line, column } = jsonSource.lineColumn(text, error.from);
        result.error = `This looks like JSON but couldn't be read: ${error.message} (line ${line}, column ${column}).`;
        problem("error", error.message, error.from, error.to);
        return result;
      }
      let data = JSON.parse(text.slice(start));
      let node = root;
      if (data && !Array.isArray(data) && Array.isArray(data.values)) {
        data = data.values;
        node = jsonSource.find(root, ["values"]).node;
      }
      if (!Array.isArray(data)) {
        result.error = "JSON data must be an array of rows.";
        const { from, to } = jsonSource.rangeForPath(root, []);
        problem("error", result.error, from, to);
        return result;
      }
      data.forEach((r, i) => {
        if (!r || typeof r !== "object" || Array.isArray(r)) {
          const item = node.items[i];
          problem("warning", "Each row should be an object, like {\"name\": value}.", item.from, item.type === "object" || item.type === "array" ? item.from + 1 : item.to);
        }
      });
      result.header = [...new Set(data.flatMap((r) => (r && typeof r === "object" ? Object.keys(r) : [])))];
      result.rows = data.map((r) => result.header.map((k) => (r && typeof r === "object" ? r[k] : undefined)));
    } else {
      // The server strips surrounding whitespace before parsing
      const offset = text.length - text.trimStart().length;
      const { rows, spans } = parseDelimitedSpans(text.trim(), DELIMITERS[format]);
      result.header = rows.shift() || [];
      spans.shift();
      result.rows = rows;
      rows.forEach((r, i) => {
        if (r.length === result.header.length) return;
        const from = spans[i][0] + offset;
        const { line } = jsonSource.lineColumn(text, from);
        problem(
          "warning",
          `Line ${line} has ${plural(r.length, "value")} but there are ${result.header.length} columns.`,
          from,
          spans[i][1] + offset,
        );
      });
    }
    if (!result.rows.length && !result.error) {
      result.error = "No data rows found. The first row should be the column names.";
    }
    return result;
  }

  /** Returns {ok, message, warning} describing the pasted text, or null. */
  function summarise(text) {
    const result = analyse(text);
    if (!result) return null;
    if (result.error) return { ok: false, message: result.error };
    const { format, header, rows, problems } = result;
    const columns = header.map((name, i) => `${name || "(blank)"} (${columnType(rows.map((r) => r[i]))})`);
    const listed = columns.slice(0, MAX_COLUMNS_LISTED).join(", ");
    const more = columns.length > MAX_COLUMNS_LISTED ? `, and ${columns.length - MAX_COLUMNS_LISTED} more` : "";
    let warning = problems[0]?.message ?? "";
    if (problems.length > 1) warning += ` ${problems.length - 1} more ${problems.length === 2 ? "row has" : "rows have"} problems too.`;
    return {
      ok: true,
      message: `${FORMAT_LABELS[format]} · ${plural(rows.length, "row")} · ${listed}${more}`,
      warning,
    };
  }

  /** Problems with the pasted text, as {from, to, severity, message}. */
  function diagnose(text) {
    return analyse(text)?.problems ?? [];
  }

  window.wagtailVegaAdmin.dataFormat = {
    detectFormat,
    parseDelimited,
    parseDelimitedSpans,
    valueType,
    columnType,
    analyse,
    summarise,
    diagnose,
    coerce,
    parseRows,
  };
})();
