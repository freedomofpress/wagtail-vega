/* wagtail-vega admin: DatasetBlock form behaviour.
 *
 * - The Paste / Document / URL toggle shows only the matching inputs.
 * - Pasted data gets a live summary (format, rows, columns and their
 *   inferred types) so editors can check it was read as intended.
 *
 * Detection and typing mirror wagtail_vega/data.py; keep them in sync.
 */
(() => {
  "use strict";

  const SOURCE_FIELDS = { paste: ["paste"], document: ["document"], url: ["url", "format"] };
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

  function parseDelimited(text, delimiter) {
    const rows = [];
    let row = [];
    let field = "";
    let quoted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; } else quoted = false;
        } else field += c;
      } else if (c === '"') quoted = true;
      else if (c === delimiter) { row.push(field); field = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(field); rows.push(row); row = []; field = "";
      } else field += c;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    return rows;
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

  /** Returns {ok, message, warning} describing the pasted text. */
  function summarise(text) {
    if (!text.trim()) return null;
    const fmt = detectFormat(text);
    let header;
    let rows;
    let warning = "";
    if (fmt === "json") {
      let data;
      try {
        data = JSON.parse(text);
      } catch (e) {
        return { ok: false, message: `This looks like JSON but couldn't be read: ${e.message}` };
      }
      if (data && !Array.isArray(data) && Array.isArray(data.values)) data = data.values;
      if (!Array.isArray(data)) return { ok: false, message: "JSON data must be an array of rows." };
      header = [...new Set(data.flatMap((r) => (r && typeof r === "object" ? Object.keys(r) : [])))];
      rows = data.map((r) => header.map((k) => (r && typeof r === "object" ? r[k] : undefined)));
    } else {
      const parsed = parseDelimited(text.trim(), DELIMITERS[fmt]);
      header = parsed.shift() || [];
      rows = parsed;
      const bad = rows.findIndex((r) => r.length !== header.length);
      if (bad !== -1) {
        const n = rows[bad].length;
        // +2: one for the header line, one because lines count from 1
        warning = `Line ${bad + 2} has ${n} value${n === 1 ? "" : "s"} but there are ${header.length} columns.`;
      }
    }
    if (!rows.length) {
      return { ok: false, message: "No data rows found. The first row should be the column names." };
    }
    const columns = header.map((name, i) => `${name || "(blank)"} (${columnType(rows.map((r) => r[i]))})`);
    const listed = columns.slice(0, MAX_COLUMNS_LISTED).join(", ");
    const more = columns.length > MAX_COLUMNS_LISTED ? `, and ${columns.length - MAX_COLUMNS_LISTED} more` : "";
    return {
      ok: true,
      message: `${FORMAT_LABELS[fmt]} · ${rows.length} row${rows.length === 1 ? "" : "s"} · ${listed}${more}`,
      warning,
    };
  }

  function fieldWrapper(root, name) {
    return root.querySelector(`[data-contentpath="${name}"]`);
  }

  class DatasetBlockDefinition extends window.wagtailStreamField.blocks.StructBlockDefinition {
    render(placeholder, prefix, initialState, initialError) {
      const block = super.render(placeholder, prefix, initialState, initialError);
      const root = block.container?.[0] ?? block.container;
      if (!root) return block;

      // Toggle which inputs are visible
      const toggle = fieldWrapper(root, "source_type");
      toggle?.classList.add("wagtail-vega-source-toggle");
      const sync = () => {
        // Read the radio directly: Wagtail's RadioSelect widget shares its
        // getState() with CheckboxSelectMultiple and may return an array.
        const current = toggle?.querySelector("input[type=radio]:checked")?.value || "paste";
        for (const [source, names] of Object.entries(SOURCE_FIELDS)) {
          for (const name of names) {
            const wrapper = fieldWrapper(root, name);
            if (wrapper) wrapper.hidden = source !== current;
          }
        }
      };
      toggle?.addEventListener("change", sync);
      sync();

      // Live summary of pasted data
      const paste = fieldWrapper(root, "paste");
      const textarea = paste?.querySelector("textarea");
      if (textarea) {
        const summary = document.createElement("div");
        summary.className = "wagtail-vega-summary";
        summary.setAttribute("aria-live", "polite");
        paste.append(summary);
        let timer;
        const update = () => {
          const result = summarise(textarea.value);
          summary.replaceChildren();
          summary.hidden = !result;
          if (!result) return;
          summary.classList.toggle("is-error", !result.ok);
          const line = document.createElement("p");
          line.textContent = `${result.ok ? "✓" : "⚠"} ${result.message}`;
          summary.append(line);
          if (result.warning) {
            const warn = document.createElement("p");
            warn.className = "wagtail-vega-summary__warning";
            warn.textContent = `⚠ ${result.warning}`;
            summary.append(warn);
          }
        };
        textarea.addEventListener("input", () => {
          clearTimeout(timer);
          timer = setTimeout(update, 150);
        });
        update();
      }
      return block;
    }
  }

  window.telepath.register("wagtail_vega.blocks.DatasetBlock", DatasetBlockDefinition);
})();
