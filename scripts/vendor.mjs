#!/usr/bin/env node
// Copy the Vega libraries and JSON schemas into the package.
//
//   npm ci --ignore-scripts && npm run vendor
//
// Versions are pinned exactly in package.json, and package-lock.json records
// each tarball's integrity hash, which `npm ci` checks. CI re-runs this and
// fails on any diff, and Dependabot proposes version bumps. The output is
// committed: installing the Python package needs no Node.
//
// vega-embed bundles vega-interpreter (used when charts are embedded with
// ast: true, e.g. in CSP-safe mode), so it isn't copied separately.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const STATIC = join(ROOT, "wagtail_vega/static/wagtail_vega/vendor");
const SCHEMAS = join(ROOT, "wagtail_vega/schemas");
const PACKAGES = ["vega", "vega-lite", "vega-embed"];

// [package, file inside the package, destination]
const FILES = [
  ["vega", "build/vega.min.js", join(STATIC, "vega.min.js")],
  ["vega-lite", "build/vega-lite.min.js", join(STATIC, "vega-lite.min.js")],
  ["vega-embed", "build/vega-embed.min.js", join(STATIC, "vega-embed.min.js")],
  ["vega", "build/vega-schema.json", join(SCHEMAS, "vega.json")],
  ["vega-lite", "build/vega-lite-schema.json", join(SCHEMAS, "vega-lite.json")],
];

const pkgDir = (name) => join(ROOT, "node_modules", name);

// The .map files aren't vendored, and a dangling reference breaks Django's
// ManifestStaticFilesStorage
function stripSourceMaps(source) {
  return source
    .replace(/^\s*\/\/# sourceMappingURL=\S*\s*$/gm, "")
    .replace(/\/\*# sourceMappingURL=[^*]*\*\//g, "");
}

mkdirSync(STATIC, { recursive: true });
mkdirSync(SCHEMAS, { recursive: true });

for (const [name, file, dest] of FILES) {
  let content = readFileSync(join(pkgDir(name), file));
  if (dest.endsWith(".js")) content = stripSourceMaps(content.toString("utf8"));
  writeFileSync(dest, content);
  console.log(`wrote ${relative(ROOT, dest)}`);
}

const versions = {};
for (const name of PACKAGES) {
  versions[name] = JSON.parse(readFileSync(join(pkgDir(name), "package.json"), "utf8")).version;
  writeFileSync(join(STATIC, `${name}.LICENSE`), readFileSync(join(pkgDir(name), "LICENSE")));
}
writeFileSync(join(STATIC, "VERSIONS.json"), JSON.stringify(versions, null, 2) + "\n");
console.log(`wrote ${relative(ROOT, join(STATIC, "VERSIONS.json"))}`);
