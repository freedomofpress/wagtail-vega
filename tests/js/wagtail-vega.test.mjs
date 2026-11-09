import assert from "node:assert/strict";
import { test } from "node:test";
import { loadFrontend, plain } from "./load.mjs";

const window = loadFrontend();
const { resolveVars, hostAllowed, makeLoader, dsvReader } = window.wagtailVega._internal;

test("defines the custom element once", () => {
  assert.equal(typeof window.customElements.get("wagtail-vega-chart"), "function");
});

test("does nothing when vega-embed is missing", () => {
  const w = loadFrontend({ vegaEmbed: undefined });
  assert.equal(w.wagtailVega, undefined);
});

test("hostAllowed", () => {
  const allowed = ["data.org", "*.example.org"];
  const check = (url) => hostAllowed(new URL(url, "https://site.test/"), allowed);
  assert.equal(check("/media/x.csv"), true); // same origin
  assert.equal(check("https://data.org/x.csv"), true);
  assert.equal(check("https://a.example.org/x.csv"), true);
  assert.equal(check("https://example.org/x.csv"), true);
  assert.equal(check("https://example.org.evil.org/x.csv"), false);
  assert.equal(check("https://evil.org/x.csv"), false);
  assert.equal(check("data:text/csv,a"), false);
  assert.equal(check("javascript:alert(1)"), false);
});

test("makeLoader rejects disallowed hosts", async () => {
  const loader = makeLoader(["data.org"]);
  assert.deepEqual(await loader.sanitize("https://data.org/x.csv"), { href: "https://data.org/x.csv" });
  assert.deepEqual(await loader.sanitize("/local.csv"), { href: "/local.csv" });
  await assert.rejects(loader.sanitize("https://evil.org/x.csv"), /not allowed/);
});

test("resolveVars uses CSS, then fallbacks, then var() defaults", () => {
  const w = loadFrontend({
    getComputedStyle: () => ({ getPropertyValue: (n) => (n === "--css" ? " red " : "") }),
  });
  const { resolveVars } = w.wagtailVega._internal;
  const config = {
    a: "var(--css)",
    b: ["var(--fb)", "var(--none, #000)", "var(--missing)", 4],
    c: { d: "plain" },
  };
  assert.deepEqual(plain((resolveVars(config, {}, { "--fb": "blue" }))), {
    a: "red",
    b: ["blue", "#000", "var(--missing)", 4],
    c: { d: "plain" },
  });
});

test("CSP-safe DSV reader parses without eval", () => {
  const csv = dsvReader(",");
  assert.equal(csv.responseType, "text");
  assert.deepEqual(plain((csv('a,b\n1,"x, y"\n2,z\n'))), [
    { a: "1", b: "x, y" },
    { a: "2", b: "z" },
  ]);
  const dsv = dsvReader(null);
  assert.deepEqual(plain((dsv("a|b\n1|2", { delimiter: "|" }))), [{ a: "1", b: "2" }]);
  assert.deepEqual(plain((csv("1,2", { header: ["x", "y"] }))), [{ x: "1", y: "2" }]);
});
