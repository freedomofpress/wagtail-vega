/* wagtail-vega admin: where things are in a JSON document.
 *
 * Browsers' JSON.parse errors don't reliably say where the problem is, and
 * JSON.parse forgets where each value was. This is a small strict JSON parser
 * (RFC 8259, like JSON.parse) that records the source range of every value
 * and property name, so that the code editor can:
 *
 * - underline a syntax error where it is;
 * - map a JSON path from the server, e.g. ["encoding", "x", "type"], or the
 *   dotted path that starts a saved error message ("encoding.x.type: ..."),
 *   to the text it refers to.
 *
 * No dependencies; exposed as window.wagtailVegaAdmin.jsonSource.
 */
(() => {
  "use strict";

  // Translations come from Django's JavaScript catalogue (wagtail_vega's
  // djangojs domain, loaded by the admin), looked up when a message is made.
  // Without a catalogue, the English text is used.
  const gettext = (s) => (window.gettext ? window.gettext(s) : s);
  const ngettext = (s, p, n) => (window.ngettext ? window.ngettext(s, p, n) : n === 1 ? s : p);
  const fill = (s, params) => s.replace(/%\((\w+)\)s/g, (m, k) => (k in params ? String(params[k]) : m));

  const NUMBER_RE = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d+)?/y;
  const WORD_RE = /[\w$.+-]+/y;
  const ESCAPES = new Set(['"', "\\", "/", "b", "f", "n", "r", "t"]);
  const LITERALS = { true: "boolean", false: "boolean", null: "null" };

  class JSONSourceError extends Error {
    constructor(message, from, to) {
      super(message);
      this.from = from;
      this.to = to;
    }
  }

  /**
   * Parse `text`, starting at `start` (e.g. to skip a byte order mark).
   *
   * Returns {root, error}. `root` is a tree of nodes:
   *   {type: "object", from, to, entries: [{key, keyFrom, keyTo, value}]}
   *   {type: "array", from, to, items: [node]}
   *   {type: "string" | "number" | "boolean" | "null", from, to}
   * or null if the text is blank or invalid. `error` is {message, from, to}
   * for the first syntax error, or null.
   */
  function parse(text, start = 0) {
    const n = text.length;
    let i = start;

    const skipSpace = () => {
      while (i < n) {
        const c = text[i];
        if (c === " " || c === "\n" || c === "\r" || c === "\t") i++;
        else break;
      }
    };
    // The extent of the token at `pos`, to underline something readable
    const tokenEnd = (pos) => {
      if (pos >= n) return n;
      const quote = text[pos];
      if (quote === '"' || quote === "'") {
        const close = text.indexOf(quote, pos + 1);
        const eol = text.indexOf("\n", pos);
        return close !== -1 && (eol === -1 || close < eol) ? close + 1 : pos + 1;
      }
      WORD_RE.lastIndex = pos;
      return WORD_RE.test(text) ? WORD_RE.lastIndex : pos + 1;
    };
    const fail = (message, from = i, to = tokenEnd(from)) => {
      throw new JSONSourceError(message, from, to);
    };
    const unexpected = (expected) => {
      if (i >= n) fail(fill(gettext("%(expected)s, but the text ended"), { expected }), n, n);
      const token = text.slice(i, tokenEnd(i));
      if (text[i] === "'") fail(gettext("Strings must use double quotes"));
      if (/^(?:NaN|-?Infinity|undefined)$/.test(token)) fail(fill(gettext("%(token)s isn't allowed in JSON"), { token }));
      const shown = token.length > 20 ? `${token.slice(0, 20)}…` : token;
      fail(fill(gettext("%(expected)s, but found %(token)s"), { expected, token: token[0] === '"' ? shown : `'${shown}'` }));
    };

    function string() {
      const from = i;
      i++; // opening quote
      while (true) {
        if (i >= n) fail(gettext("This string isn't closed"), from, n);
        const c = text[i];
        if (c === '"') {
          i++;
          return { type: "string", from, to: i, value: text.slice(from + 1, i - 1) };
        }
        if (c === "\\") {
          const e = text[i + 1];
          if (e === "u") {
            if (!/^[0-9a-fA-F]{4}$/.test(text.slice(i + 2, i + 6))) {
              fail(gettext("Invalid \\u escape: it needs four hex digits"), i, Math.min(i + 6, n));
            }
            i += 6;
          } else if (ESCAPES.has(e)) {
            i += 2;
          } else {
            fail(fill(gettext("Invalid escape sequence %(escape)s"), { escape: `\\${e ?? ""}` }), i, Math.min(i + 2, n));
          }
        } else if (c === "\n" || c === "\r") {
          fail(gettext("This string isn't closed before the end of the line"), from, i);
        } else if (c < " ") {
          fail(gettext("Control characters in strings must be escaped"), i, i + 1);
        } else {
          i++;
        }
      }
    }

    function number() {
      const from = i;
      NUMBER_RE.lastIndex = i;
      const match = NUMBER_RE.exec(text);
      const end = tokenEnd(from);
      if (!match || match[0].length !== end - from) {
        const token = text.slice(from, end);
        if (/^-?Infinity$/.test(token)) fail(fill(gettext("%(token)s isn't allowed in JSON"), { token }), from, end);
        fail(fill(gettext("%(token)s isn't a valid JSON number"), { token }), from, end);
      }
      i += match[0].length;
      return { type: "number", from, to: i };
    }

    function object() {
      const node = { type: "object", from: i, to: i, entries: [] };
      i++;
      skipSpace();
      if (text[i] === "}") {
        i++;
        node.to = i;
        return node;
      }
      while (true) {
        skipSpace();
        if (text[i] !== '"') {
          if (text[i] === "}" && node.entries.length) {
            fail(gettext("Trailing commas aren't allowed in JSON"), lastComma(), lastComma() + 1);
          }
          unexpected(gettext("Expected a property name in double quotes"));
        }
        const key = string();
        skipSpace();
        if (text[i] !== ":") unexpected(gettext("Expected a colon after the property name"));
        i++;
        node.entries.push({ key: decode(key), keyFrom: key.from, keyTo: key.to, value: value() });
        skipSpace();
        if (text[i] === ",") {
          i++;
          continue;
        }
        if (text[i] === "}") {
          i++;
          node.to = i;
          return node;
        }
        unexpected(gettext("Expected a comma or }"));
      }
    }

    function array() {
      const node = { type: "array", from: i, to: i, items: [] };
      i++;
      skipSpace();
      if (text[i] === "]") {
        i++;
        node.to = i;
        return node;
      }
      while (true) {
        skipSpace();
        if (text[i] === "]" && node.items.length) {
          fail(gettext("Trailing commas aren't allowed in JSON"), lastComma(), lastComma() + 1);
        }
        node.items.push(value());
        skipSpace();
        if (text[i] === ",") {
          i++;
          continue;
        }
        if (text[i] === "]") {
          i++;
          node.to = i;
          return node;
        }
        unexpected(gettext("Expected a comma or ]"));
      }
    }

    // Only called just after skipping a comma and whitespace
    function lastComma() {
      return text.lastIndexOf(",", i);
    }

    function value() {
      skipSpace();
      const c = text[i];
      if (c === "{") return object();
      if (c === "[") return array();
      if (c === '"') return string();
      if (c === "-" || (c >= "0" && c <= "9")) return number();
      for (const [word, type] of Object.entries(LITERALS)) {
        if (text.startsWith(word, i) && tokenEnd(i) === i + word.length) {
          const from = i;
          i += word.length;
          return { type, from, to: i };
        }
      }
      return unexpected(gettext("Expected a value"));
    }

    try {
      skipSpace();
      if (i >= n) return { root: null, error: null };
      const root = value();
      skipSpace();
      if (i < n) fail(gettext("Unexpected text after the end of the JSON value"));
      return { root, error: null };
    } catch (e) {
      if (!(e instanceof JSONSourceError)) throw e;
      return { root: null, error: { message: e.message, from: e.from, to: e.to } };
    }
  }

  function decode(stringNode) {
    try {
      return JSON.parse(`"${stringNode.value}"`);
    } catch {
      return stringNode.value;
    }
  }

  /** The line (from 1) and column (from 1) of an offset. */
  function lineColumn(text, offset) {
    let line = 1;
    let lineStart = 0;
    for (let i = text.indexOf("\n"); i !== -1 && i < offset; i = text.indexOf("\n", i + 1)) {
      line++;
      lineStart = i + 1;
    }
    return { line, column: offset - lineStart + 1 };
  }

  /**
   * Follow a path (property names and array indices) from `root`. Returns
   * {node, entry, complete}: the deepest node reached, the object entry it
   * is the value of (or null), and whether the whole path was found.
   */
  function find(root, path) {
    let node = root;
    let entry = null;
    for (const step of path) {
      let next = null;
      if (node.type === "object") {
        // Duplicate keys: the last one wins, as in JSON.parse and Python
        next = node.entries.findLast((e) => e.key === String(step)) ?? null;
      } else if (node.type === "array" && /^\d+$/.test(String(step))) {
        const item = node.items[Number(step)];
        next = item ? { value: item, keyFrom: null } : null;
      }
      if (!next) return { node, entry, complete: false };
      node = next.value;
      entry = next.keyFrom === null ? null : next;
    }
    return { node, entry, complete: true };
  }

  // jsonschema: "Additional properties are not allowed ('foo' was unexpected)"
  const UNEXPECTED_KEY_RE = /\('((?:[^'\\]|\\.)*)'(?:, '(?:[^'\\]|\\.)*')* (?:was|were) unexpected\)/;

  /**
   * The range to underline for a problem at `path`. Scalars are underlined
   * whole; for objects and arrays (which may span many lines) the property
   * name is underlined, or the opening bracket if there isn't one. If the
   * message names an unexpected property, that property is underlined.
   */
  function rangeForPath(root, path, message = "") {
    const { node, entry } = find(root, path);
    const unexpected = node.type === "object" && UNEXPECTED_KEY_RE.exec(message);
    if (unexpected) {
      const key = node.entries.find((e) => e.key === unexpected[1]);
      if (key) return { from: key.keyFrom, to: key.keyTo };
    }
    if (node.type !== "object" && node.type !== "array") return { from: node.from, to: node.to };
    if (entry) return { from: entry.keyFrom, to: entry.keyTo };
    return { from: node.from, to: node.from + 1 };
  }

  /**
   * Turn a dotted path ("layer.0.encoding.x") into a path array, using the
   * document to tell keys that contain dots from nested keys. Returns null
   * unless the whole path exists in the document.
   */
  function resolveDotted(node, dotted) {
    if (node.type === "object") {
      const entries = [...node.entries].sort((a, b) => b.key.length - a.key.length);
      for (const e of entries) {
        if (dotted === e.key) return [e.key];
        if (dotted.startsWith(`${e.key}.`)) {
          const rest = resolveDotted(e.value, dotted.slice(e.key.length + 1));
          if (rest) return [e.key, ...rest];
        }
      }
    } else if (node.type === "array") {
      const match = /^(\d+)(\.|$)/.exec(dotted);
      const index = match && Number(match[1]);
      if (match && index < node.items.length) {
        if (!match[2]) return [index];
        const rest = resolveDotted(node.items[index], dotted.slice(match[0].length));
        if (rest) return [index, ...rest];
      }
    }
    return null;
  }

  /**
   * Split a server error message like "encoding.x.type: 'nominl' is not
   * valid" into {path: ["encoding", "x", "type"], message: "'nominl' is not
   * valid"}. Messages that don't start with a path found in the document
   * give {path: null, message}.
   */
  function splitMessage(root, message) {
    if (root) {
      for (let at = message.indexOf(": "); at > 0; at = message.indexOf(": ", at + 1)) {
        const path = resolveDotted(root, message.slice(0, at));
        if (path) return { path, message: message.slice(at + 2) };
      }
    }
    return { path: null, message };
  }

  window.wagtailVegaAdmin = window.wagtailVegaAdmin || {};
  window.wagtailVegaAdmin.jsonSource = {
    parse,
    lineColumn,
    find,
    rangeForPath,
    resolveDotted,
    splitMessage,
  };
})();
