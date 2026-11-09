import assert from "node:assert/strict";
import { test } from "node:test";
import { loadFrontend, plain, registeredFormats } from "./load.mjs";

const window = loadFrontend();
const { hostAllowed, makeLoader, makeLogger, dsvReader, useCspSafeFormats } =
  window.wagtailVega._internal;

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

test("makeLoader doesn't apply the data allowlist to hyperlinks", async () => {
  const loader = makeLoader([]);
  assert.deepEqual(await loader.sanitize("https://elsewhere.org/story", { context: "href" }), {
    href: "https://elsewhere.org/story",
  });
  await assert.rejects(loader.sanitize("https://elsewhere.org/x.png", { context: "image" }), /not allowed/);
});

test("resolveVars leaves data alone", () => {
  const w = loadFrontend({ getComputedStyle: () => ({ getPropertyValue: () => "red" }) });
  const spec = {
    mark: { color: "var(--a)" },
    data: { values: [{ label: "var(--a)" }] },
    datasets: { s: [{ label: "var(--a)" }] },
    layer: [{ data: { values: ["var(--a)"] }, encoding: { color: { value: "var(--a)" } } }],
  };
  const out = plain(w.wagtailVega._internal.resolveVars(spec, {}, {}));
  assert.equal(out.mark.color, "red");
  assert.equal(out.layer[0].encoding.color.value, "red");
  assert.deepEqual(out.data, spec.data);
  assert.deepEqual(out.datasets, spec.datasets);
  assert.deepEqual(out.layer[0].data, spec.layer[0].data);
});

test("useCspSafeFormats rewrites only our delimited data to private readers", () => {
  const spec = {
    data: { url: "/d.csv" },
    layer: [
      { data: { url: "https://x.org/rows.TSV?v=1" } },
      { data: { url: "/rows.json" } },
      { data: { url: "/rows", format: { type: "dsv", delimiter: "|" } } },
      { data: { values: "a,b\n1,2", format: { type: "csv" } } },
      { data: { name: "source" } },
    ],
  };
  const out = plain(useCspSafeFormats(spec));
  assert.deepEqual(out.data, { url: "/d.csv", format: { type: "wagtail-vega-csv" } });
  assert.equal(out.layer[0].data.format.type, "wagtail-vega-tsv");
  assert.equal(out.layer[1].data.format, undefined);
  assert.deepEqual(out.layer[2].data.format, { type: "wagtail-vega-dsv", delimiter: "|" });
  assert.equal(out.layer[3].data.format.type, "wagtail-vega-csv");
  assert.deepEqual(out.layer[4].data, { name: "source" });
  assert.deepEqual(plain(spec.data), { url: "/d.csv" }); // input untouched
});

test("CSP-safe readers never replace Vega's own formats", () => {
  window.wagtailVega._internal.installCspSafeFormats();
  assert.deepEqual(Object.keys(registeredFormats).sort(), [
    "wagtail-vega-csv",
    "wagtail-vega-dsv",
    "wagtail-vega-tsv",
  ]);
});

test("makeLogger reports data failures and still logs them", () => {
  const errors = [];
  const logger = makeLogger((args) => errors.push(args.join(" ")));
  logger.warn("Loading failed", "/x.csv", "404");
  logger.warn("Data ingestion failed", "/y.csv");
  logger.warn("Infinite extent for field");
  assert.deepEqual(errors, ["Loading failed /x.csv 404", "Data ingestion failed /y.csv"]);
  assert.equal(logger.warned.length, 3);
});

test("useCspSafeFormats leaves inline rows alone", () => {
  const spec = {
    data: { values: [{ url: "https://example.org/report.csv", n: 1 }] },
    datasets: { links: [{ url: "/files/a.tsv" }] },
    layer: [{ data: { url: "/d.csv" } }],
  };
  const out = plain(useCspSafeFormats(spec));
  assert.deepEqual(out.data, spec.data);
  assert.deepEqual(out.datasets, spec.datasets);
  assert.equal(out.layer[0].data.format.type, "wagtail-vega-csv");
});
