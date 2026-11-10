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
//
// Vega Voyager, the admin's visual chart editor, is assembled here too: see
// vendorVoyager() below.
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
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
versions.voyager = vendorVoyager();
writeFileSync(join(STATIC, "VERSIONS.json"), JSON.stringify(versions, null, 2) + "\n");
console.log(`wrote ${relative(ROOT, join(STATIC, "VERSIONS.json"))}`);

// --------------------------------------------------------------------------
// Vega Voyager (the admin's visual chart editor)
//
// Voyager's last release (2018) builds against React 15, vega 4 and
// vega-lite 2, and its library build expects those as globals. It only ever
// runs in a sandboxed iframe in the admin (see wagtail_vega/views.py), so
// these old copies never meet the vega 6 used for charts. They're frozen:
// package.json pins them (the old vega packages under aliases, such as
// voyager-vega, next to vega 6), and .github/dependabot.yml ignores them.
//
// The scripts are concatenated in load order into voyager/voyager.js, with
// Voyager's styles and its inlined icon font in voyager/voyager.css, and
// every package's licence in voyager/LICENSES.txt. The output is
// byte-identical to what scripts/vendor.py, which this replaced, wrote.
// --------------------------------------------------------------------------

function vendorVoyager() {
  const VOYAGER = join(STATIC, "voyager");
  // [package, its directory in node_modules, file], in load order
  const SCRIPTS = [
    ["react", "react", "dist/react.min.js"],
    ["react-dom", "react-dom", "dist/react-dom.min.js"],
    ["prop-types", "prop-types", "prop-types.min.js"],
    ["redux", "redux", "dist/redux.min.js"],
    ["react-redux", "react-redux", "dist/react-redux.min.js"],
    ["redux-thunk", "redux-thunk", "dist/redux-thunk.min.js"],
    ["redux-undo", "redux-undo", "dist/redux-undo.js"],
    ["react-dnd", "react-dnd", "dist/ReactDnD.min.js"],
    ["react-dnd-html5-backend", "react-dnd-html5-backend", "dist/ReactDnDHTML5Backend.min.js"],
    ["tether", "tether", "dist/js/tether.min.js"],
    ["react-tether", "react-tether", "dist/react-tether.min.js"],
    ["moment", "moment", "min/moment.min.js"],
    ["vega", "voyager-vega", "build/vega.min.js"],
    ["vega-lite", "voyager-vega-lite", "build/vega-lite.min.js"],
    ["vega-tooltip", "voyager-vega-tooltip", "build/vega-tooltip.min.js"],
    ["lodash", "lodash", "lodash.min.js"],
    // react-css-modules only ships CommonJS: see wrapCommonJS()
    ["react-css-modules", "react-css-modules", null],
    ["datavoyager", "datavoyager", "build/lib-voyager.js"],
  ];
  // CommonJS packages bundled into react-css-modules' wrapper: [package,
  // file, or directory of files]
  const COMMONJS = [
    ["react-css-modules", "dist/"],
    ["object-unfreeze", "dist/objectUnfreeze.js"],
    ["hoist-non-react-statics", "dist/hoist-non-react-statics.cjs.js"],
  ];
  const LICENSE_FILES = ["LICENSE", "LICENSE.md", "LICENSE.txt", "license", "LICENCE"];
  // Packages whose npm tarball has no licence file: where the text lives
  const NO_LICENSE_FILE = {
    "vega-tooltip": "https://github.com/vega/vega-tooltip/blob/v0.4.4/LICENSE",
  };
  const dirOf = Object.fromEntries(SCRIPTS.map(([name, dir]) => [name, dir]));
  const dir = (name) => pkgDir(dirOf[name] || name);
  const readText = (name, file) => readFileSync(join(dir(name), file), "utf8");
  const manifest = (name) => JSON.parse(readText(name, "package.json"));
  const fail = (message) => {
    throw new Error(`vendor.mjs: ${message}`);
  };

  // lib-voyager's UMD wrapper reads its dependencies from these globals
  // (window["react-dom"] etc.); the libraries above define React, ReactDOM...
  const GLOBALS = `
(function (w) {
  var map = {
    "react": "React", "react-dom": "ReactDOM", "redux": "Redux",
    "react-redux": "ReactRedux", "redux-thunk": "ReduxThunk",
    "redux-undo": "ReduxUndo", "react-dnd": "ReactDnD",
    "react-dnd-html5-backend": "ReactDnDHTML5Backend",
    "react-tether": "TetherComponent", "vega-lite": "vl",
    "vega-tooltip": "vegaTooltip", "react-css-modules": "ReactCSSModules",
    "moment": "moment", "vega": "vega"
  };
  Object.keys(map).forEach(function (name) {
    var m = w[map[name]];
    if (!m) throw new Error("wagtail-vega: " + map[name] + " did not load");
    // Voyager's TypeScript reads default imports as \`module.default\`
    if (!("default" in m)) m.default = m;
    w[name] = m;
  });
  // A webpack-only side-effect import (Voyager's icon font, loaded here
  // through font-awesome.css instead)
  w["font-awesome-sass-loader"] = {};
})(window);
`;

  // [package, exact text, replacement]: small fixes to the published builds.
  // Each must match exactly once, so a version bump that changes them fails.
  const PATCHES = [
    // react-tether's dist build left prop-types out, as a stub that throws
    [
      "react-tether",
      "n(!function(){var e=new Error('Cannot find module \"prop-types\"');" +
        'throw e.code="MODULE_NOT_FOUND",e}())',
      "window.PropTypes",
    ],
    // Voyager was published with redux-logger switched on, which logs every
    // state change to the console
    ["datavoyager", "f=window.__REDUX_DEVTOOLS_EXTENSION_COMPOSE__||i.compose,p.push(d),", ""],
  ];

  function licenseText(name) {
    for (const candidate of LICENSE_FILES) {
      // On a case-insensitive disk "LICENSE" also finds "license": the same file
      const path = join(dir(name), candidate);
      if (existsSync(path)) return readFileSync(path, "utf8");
    }
    if (name in NO_LICENSE_FILE) {
      return (
        `${manifest(name).license} (per package.json; the npm tarball has no license file).\n` +
        `Copyright (c) the vega-tooltip authors. See ${NO_LICENSE_FILE[name]}`
      );
    }
    return fail(`no license file in ${name}`);
  }

  /** Bundle react-css-modules (CommonJS only) and its two small dependencies
   * into a classic script defining window.ReactCSSModules. require("react")
   * and require("lodash/<fn>") resolve to the React and lodash globals
   * loaded before it. */
  function wrapCommonJS() {
    const modules = new Map();
    const byName = (a, b) => {
      const [x, y] = [a.toLowerCase(), b.toLowerCase()];
      return x < y ? -1 : x > y ? 1 : 0;
    };
    for (const [name, path] of COMMONJS) {
      if (path.endsWith("/")) {
        // In the tarball's order: by name, ignoring case
        const files = readdirSync(join(dir(name), path)).filter((f) => f.endsWith(".js")).sort(byName);
        for (const file of files) modules.set(`./${file.slice(0, -3)}`, readText(name, path + file));
      } else {
        modules.set(name, readText(name, path));
      }
    }
    if (!modules.has("./index")) fail("react-css-modules: dist/index.js missing");
    for (const [key, source] of modules) {
      for (const [, raw] of source.matchAll(/require\(['"]([^'"]+)['"]\)/g)) {
        const dep = raw.replace(/\.js$/, "");
        if (dep === "react" || dep.startsWith("lodash/") || modules.has(dep)) continue;
        fail(`react-css-modules: ${key} requires unknown module ${JSON.stringify(dep)}`);
      }
    }
    const defs = [...modules]
      .map(
        ([key, source]) =>
          `defs[${JSON.stringify(key)}] = function (module, exports, require) {\n${stripSourceMaps(source)}\n};`,
      )
      .join("\n");
    return (
      "(function (root) {\n" +
      "var defs = {}, cache = {};\n" +
      `${defs}\n` +
      "function req(id) {\n" +
      '  if (id === "react") return root.React;\n' +
      '  if (id.indexOf("lodash/") === 0) return root._[id.slice(7)];\n' +
      '  id = id.replace(/\\.js$/, "");\n' +
      "  if (!cache[id]) {\n" +
      "    var module = (cache[id] = { exports: {} });\n" +
      "    defs[id](module, module.exports, req);\n" +
      "  }\n" +
      "  return cache[id].exports;\n" +
      "}\n" +
      'root.ReactCSSModules = req("./index");\n' +
      "})(window);\n"
    );
  }

  /** Font Awesome (Voyager's icons) followed by Voyager's own styles. The
   * font is inlined as a data: URI because the Voyager page runs in a
   * sandboxed iframe with an opaque origin, where loading a font file from
   * the static server would need CORS headers. */
  function voyagerCSS(voyagerVersion) {
    const fa = manifest("font-awesome").version;
    let css = readText("font-awesome", "css/font-awesome.min.css");
    const woff2 = readFileSync(join(dir("font-awesome"), "fonts/fontawesome-webfont.woff2")).toString("base64");
    const face = /@font-face\{[^}]*\}/.exec(css);
    if (!face) fail("font-awesome: @font-face not found");
    css = css.replace(
      face[0],
      () =>
        "@font-face{font-family:'FontAwesome';" +
        `src:url(data:font/woff2;base64,${woff2}) format('woff2');` +
        "font-weight:normal;font-style:normal}",
    );
    const voyager = readText("datavoyager", "build/style.css");
    if (voyager.includes("url(")) fail("datavoyager: style.css now references files; vendor them");
    return (
      `/* font-awesome@${fa} (CSS: MIT, font: OFL-1.1) */\n` +
      `${stripSourceMaps(css)}\n` +
      `/* datavoyager@${voyagerVersion} (BSD-3-Clause) */\n` +
      `${stripSourceMaps(voyager)}\n`
    );
  }

  mkdirSync(VOYAGER, { recursive: true });
  const patches = new Map();
  for (const [name, old, replacement] of PATCHES) {
    if (!(name in dirOf)) fail(`a patch for an unknown package, ${name}`);
    patches.set(name, [...(patches.get(name) || []), [old, replacement]]);
  }
  // (The header still names vendor.py, so the output stays as it was)
  const parts = ["/* Vega Voyager and its dependencies, vendored by scripts/vendor.py */\n"];
  const versions = {};
  for (const [name, , file] of SCRIPTS) {
    const pkg = manifest(name);
    let source = file === null ? wrapCommonJS() : readText(name, file);
    for (const [old, replacement] of patches.get(name) || []) {
      if (source.split(old).length !== 2) {
        fail(`the patch for ${name}@${pkg.version} no longer applies exactly once; review it`);
      }
      source = source.replace(old, () => replacement);
    }
    if (name === "datavoyager") parts.push(`/* --- wagtail-vega: globals for lib-voyager --- */\n${GLOBALS}`);
    parts.push(`\n/* --- ${name}@${pkg.version} (${pkg.license ?? "?"}) --- */\n;${stripSourceMaps(source)}\n`);
    versions[name] = pkg.version;
  }
  for (const [name] of COMMONJS) versions[name] = manifest(name).version;
  versions["font-awesome"] = manifest("font-awesome").version;

  const rule = "=".repeat(72);
  const licenses = Object.entries(versions).map(([name, version]) => {
    const text =
      name === "font-awesome"
        ? "Font Awesome 4.7.0 by Dave Gandy - http://fontawesome.io\n" +
          "Font: SIL OFL 1.1 (http://scripts.sil.org/OFL). " +
          "CSS: MIT License (https://opensource.org/licenses/mit-license.html)\n"
        : licenseText(name);
    return `${rule}\n${name}@${version}\n${rule}\n${text.trim()}\n`;
  });

  const outputs = {
    "voyager.js": parts.join(""),
    "voyager.css": voyagerCSS(versions.datavoyager),
    "LICENSES.txt": licenses.join("\n"),
  };
  for (const [filename, content] of Object.entries(outputs)) {
    const dest = join(VOYAGER, filename);
    writeFileSync(dest, content);
    console.log(`wrote ${relative(ROOT, dest)} (${Math.floor(Buffer.byteLength(content) / 1024)} KiB)`);
  }
  return versions;
}
