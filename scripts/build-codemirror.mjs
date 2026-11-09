#!/usr/bin/env node
// Build the vendored CodeMirror 6 bundle used by the admin code editor.
//
//   npm ci && npm run build
//
// CodeMirror 6 ships as ES modules split over many packages, so they are
// bundled with esbuild into one classic script that sets
// window.wagtailVegaCodeMirror. Versions are pinned exactly in package.json
// and package-lock.json (npm ci checks each tarball's integrity hash), and
// the output is deterministic, so CI rebuilds it and fails on any diff.
// The output is committed: installing the Python package needs no Node.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as esbuild from "esbuild";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(ROOT, "wagtail_vega/static/wagtail_vega/admin/vendor");
const BUNDLE = "codemirror.js";

const result = await esbuild.build({
  entryPoints: ["scripts/codemirror/entry.mjs"],
  absWorkingDir: ROOT,
  bundle: true,
  format: "iife",
  globalName: "wagtailVegaCodeMirror",
  minify: true,
  target: ["es2020"],
  legalComments: "none",
  metafile: true,
  write: false,
});

// Every npm package that ended up in the bundle, with its version and licence
const packages = new Map();
for (const input of Object.keys(result.metafile.inputs)) {
  const match = input.match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//);
  if (!match || packages.has(match[1])) continue;
  const dir = join(ROOT, "node_modules", match[1]);
  const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
  let licenseText = "";
  for (const name of ["LICENSE", "LICENSE.md", "LICENSE.txt"]) {
    try {
      licenseText = readFileSync(join(dir, name), "utf8").trim();
      break;
    } catch {
      // try the next name
    }
  }
  if (!licenseText) throw new Error(`No licence file found for ${match[1]}`);
  packages.set(match[1], { version: pkg.version, license: pkg.license, licenseText });
}
const names = [...packages.keys()].sort();
const describe = (n) => `${n}@${packages.get(n).version}`;

const banner = [
  "/* CodeMirror 6 for wagtail-vega, built by scripts/build-codemirror.mjs. Do not edit.",
  ...names.map((n) => ` * ${describe(n)} (${packages.get(n).license})`),
  " * Licence texts: codemirror.LICENSE */",
  "",
].join("\n");

const code = result.outputFiles[0].text;
writeFileSync(join(OUT, BUNDLE), banner + code);
writeFileSync(
  join(OUT, "codemirror.LICENSE"),
  names.map((n) => `${describe(n)}\n\n${packages.get(n).licenseText}\n`).join("\n---\n\n"),
);
writeFileSync(
  join(OUT, "codemirror.VERSIONS.json"),
  `${JSON.stringify(Object.fromEntries(names.map((n) => [n, packages.get(n).version])), null, 2)}\n`,
);
console.log(`wrote ${BUNDLE}: ${(code.length / 1024).toFixed(1)} KiB, ${names.map(describe).join(", ")}`);
