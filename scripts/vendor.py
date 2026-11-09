#!/usr/bin/env python3
"""Vendor the pinned Vega JavaScript builds and JSON schemas into the package.

Run from the repository root after changing a version below:

    python scripts/vendor.py

Each tarball is fetched from the npm registry and checked against the
registry's published ``dist.integrity`` hash. No downloaded code is executed.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "wagtail_vega" / "static" / "wagtail_vega" / "vendor"
SCHEMAS = ROOT / "wagtail_vega" / "schemas"

PACKAGES = {
    "vega": "6.4.0",
    "vega-lite": "6.5.0",
    "vega-embed": "7.3.0",
    "vega-interpreter": "2.3.2",
}

# (package, path inside tarball, destination)
FILES = [
    ("vega", "package/build/vega.min.js", STATIC / "vega.min.js"),
    ("vega-lite", "package/build/vega-lite.min.js", STATIC / "vega-lite.min.js"),
    ("vega-embed", "package/build/vega-embed.min.js", STATIC / "vega-embed.min.js"),
    ("vega", "package/build/vega-schema.json", SCHEMAS / "vega.json"),
    ("vega-lite", "package/build/vega-lite-schema.json", SCHEMAS / "vega-lite.json"),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "wagtail-vega-vendor"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read()


def download(name: str, version: str) -> tarfile.TarFile:
    meta = json.loads(fetch(f"https://registry.npmjs.org/{name}/{version}"))
    data = fetch(meta["dist"]["tarball"])
    algo, expected = meta["dist"]["integrity"].split("-", 1)
    actual = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if actual != expected:
        sys.exit(f"Integrity mismatch for {name}@{version}")
    return tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")


def read(tar: tarfile.TarFile, member: str) -> bytes:
    f = tar.extractfile(member)
    if f is None:
        sys.exit(f"{member} missing")
    return f.read()


def wrap_interpreter(source: str) -> str:
    """vega-interpreter only ships as an ES module importing vega-util.

    vega-util is re-exported on the global ``vega`` object by the UMD build,
    so rewrite the module into a classic script exposing
    ``window.vegaInterpreter.expressionInterpreter``.
    """
    imports = re.findall(r"^import \{([^}]*)\} from 'vega-util';\n", source, re.M)
    if len(imports) != 1:
        sys.exit("Unexpected vega-interpreter imports; update wrap_interpreter()")
    body = re.sub(r"^import .*;\n", "", source, flags=re.M)
    export = re.search(r"^export \{ (\w+) as expressionInterpreter \};\n", body, re.M)
    if not export:
        sys.exit("Unexpected vega-interpreter exports; update wrap_interpreter()")
    body = body.replace(export.group(0), "")
    body = re.sub(r"^//# sourceMappingURL=.*\n?", "", body, flags=re.M)
    return (
        f"/* vega-interpreter@{PACKAGES['vega-interpreter']} (BSD-3-Clause), "
        "wrapped by wagtail-vega */\n"
        "(function (global) {\n"
        f"const {{{imports[0]}}} = global.vega;\n"
        f"{body}\n"
        f"global.vegaInterpreter = {{ expressionInterpreter: {export.group(1)} }};\n"
        "})(globalThis);\n"
    )


# --------------------------------------------------------------------------
# Vega Voyager (the admin's visual chart builder)
#
# Voyager's last release (2018) builds against React 15, vega 4 and
# vega-lite 2, and its library build expects those as globals. It only ever
# runs in a sandboxed iframe in the admin (see wagtail_vega/views.py), so
# these old copies never meet the vega 6 used for charts.
# --------------------------------------------------------------------------

VOYAGER = STATIC / "voyager"

# (package, version, path inside the tarball), in load order
VOYAGER_SCRIPTS = [
    ("react", "15.7.0", "dist/react.min.js"),
    ("react-dom", "15.7.0", "dist/react-dom.min.js"),
    ("prop-types", "15.8.1", "prop-types.min.js"),
    ("redux", "3.7.2", "dist/redux.min.js"),
    ("react-redux", "5.1.2", "dist/react-redux.min.js"),
    ("redux-thunk", "2.4.2", "dist/redux-thunk.min.js"),
    ("redux-undo", "1.0.0-beta9-9-6", "dist/redux-undo.js"),
    ("react-dnd", "2.6.0", "dist/ReactDnD.min.js"),
    ("react-dnd-html5-backend", "2.6.0", "dist/ReactDnDHTML5Backend.min.js"),
    ("tether", "1.4.7", "dist/js/tether.min.js"),
    ("react-tether", "0.5.7", "dist/react-tether.min.js"),
    ("moment", "2.30.1", "min/moment.min.js"),
    ("vega", "4.0.0", "build/vega.min.js"),
    ("vega-lite", "2.4.0", "build/vega-lite.min.js"),
    ("vega-tooltip", "0.4.4", "build/vega-tooltip.min.js"),
    ("lodash", "4.17.21", "lodash.min.js"),
    # react-css-modules only ships CommonJS: see wrap_commonjs()
    ("react-css-modules", "4.7.11", None),
    ("datavoyager", "2.0.0-alpha.24", "build/lib-voyager.js"),
]
# CommonJS packages bundled into react-css-modules' wrapper
VOYAGER_COMMONJS = {
    "react-css-modules": ("4.7.11", "dist/"),
    "object-unfreeze": ("1.1.0", "dist/objectUnfreeze.js"),
    "hoist-non-react-statics": ("2.5.5", "dist/hoist-non-react-statics.cjs.js"),
}
FONT_AWESOME = "4.7.0"
LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "license", "LICENCE")

# lib-voyager's UMD wrapper reads its dependencies from these globals
# (window["react-dom"] etc.); the libraries above define React, ReactDOM...
VOYAGER_GLOBALS = """
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
    // Voyager's TypeScript reads default imports as `module.default`
    if (!("default" in m)) m.default = m;
    w[name] = m;
  });
  // A webpack-only side-effect import (Voyager's icon font, loaded here
  // through font-awesome.css instead)
  w["font-awesome-sass-loader"] = {};
})(window);
"""

# (package, exact text, replacement): small fixes to the published builds.
# Each must match exactly once, so a version bump that changes them fails.
VOYAGER_PATCHES = [
    # react-tether's dist build left prop-types out, as a stub that throws
    (
        "react-tether",
        "n(!function(){var e=new Error('Cannot find module \"prop-types\"');"
        'throw e.code="MODULE_NOT_FOUND",e}())',
        "window.PropTypes",
    ),
    # Voyager was published with redux-logger switched on, which logs every
    # state change to the console
    (
        "datavoyager",
        "f=window.__REDUX_DEVTOOLS_EXTENSION_COMPOSE__||i.compose,p.push(d),",
        "",
    ),
]


_tars: dict[tuple[str, str], tarfile.TarFile] = {}


def tarball(name: str, version: str) -> tarfile.TarFile:
    if (name, version) not in _tars:
        _tars[name, version] = download(name, version)
    return _tars[name, version]


# Packages whose npm tarball has no license file: where the text lives
NO_LICENSE_FILE = {
    "vega-tooltip": "https://github.com/vega/vega-tooltip/blob/v0.4.4/LICENSE",
}


def license_text(name: str, version: str) -> str:
    tar = tarball(name, version)
    for candidate in LICENSE_FILES:
        try:
            return read(tar, f"package/{candidate}").decode()
        except KeyError:
            continue
    if name in NO_LICENSE_FILE:
        spdx = json.loads(read(tar, "package/package.json"))["license"]
        return f"{spdx} (per package.json; the npm tarball has no license file).\n" + (
            f"Copyright (c) the vega-tooltip authors. See {NO_LICENSE_FILE[name]}"
        )
    sys.exit(f"No license file in {name}@{version}")


def strip_source_maps(source: str) -> str:
    # The maps aren't vendored; a dangling reference also breaks
    # ManifestStaticFilesStorage
    source = re.sub(r"^\s*//# sourceMappingURL=\S*\s*$", "", source, flags=re.M)
    return re.sub(r"/\*# sourceMappingURL=[^*]*\*/", "", source)


def wrap_commonjs() -> str:
    """Bundle react-css-modules (CommonJS only) and its two small
    dependencies into a classic script defining ``window.ReactCSSModules``.

    ``require("react")`` and ``require("lodash/<fn>")`` resolve to the React
    and lodash globals loaded before it.
    """
    modules = {}
    for name, (version, path) in VOYAGER_COMMONJS.items():
        tar = tarball(name, version)
        if path.endswith("/"):
            for member in tar.getmembers():
                rel = member.name.removeprefix(f"package/{path}")
                if member.isfile() and rel != member.name and rel.endswith(".js"):
                    modules["./" + rel[:-3]] = read(tar, member.name).decode()
        else:
            modules[name] = read(tar, f"package/{path}").decode()
    if "./index" not in modules:
        sys.exit("react-css-modules: dist/index.js missing")
    for key, source in modules.items():
        for dep in re.findall(r"require\(['\"]([^'\"]+)['\"]\)", source):
            dep = dep.removesuffix(".js")
            if dep == "react" or dep.startswith("lodash/") or dep in modules:
                continue
            sys.exit(f"react-css-modules: {key} requires unknown module {dep!r}")
    defs = "\n".join(
        f"defs[{json.dumps(key)}] = function (module, exports, require) {{\n"
        f"{strip_source_maps(source)}\n}};"
        for key, source in modules.items()
    )
    return (
        "(function (root) {\n"
        "var defs = {}, cache = {};\n"
        f"{defs}\n"
        "function req(id) {\n"
        '  if (id === "react") return root.React;\n'
        '  if (id.indexOf("lodash/") === 0) return root._[id.slice(7)];\n'
        '  id = id.replace(/\\.js$/, "");\n'
        "  if (!cache[id]) {\n"
        "    var module = (cache[id] = { exports: {} });\n"
        "    defs[id](module, module.exports, req);\n"
        "  }\n"
        "  return cache[id].exports;\n"
        "}\n"
        'root.ReactCSSModules = req("./index");\n'
        "})(window);\n"
    )


def voyager_css() -> str:
    """Font Awesome (Voyager's icons) followed by Voyager's own styles.

    The font is inlined as a data: URI because the Voyager page runs in a
    sandboxed iframe with an opaque origin, where loading a font file from
    the static server would need CORS headers.
    """
    fa = tarball("font-awesome", FONT_AWESOME)
    css = read(fa, "package/css/font-awesome.min.css").decode()
    woff2 = base64.b64encode(read(fa, "package/fonts/fontawesome-webfont.woff2")).decode()
    face = re.search(r"@font-face\{[^}]*\}", css)
    if not face:
        sys.exit("font-awesome: @font-face not found")
    css = css.replace(
        face.group(0),
        "@font-face{font-family:'FontAwesome';"
        f"src:url(data:font/woff2;base64,{woff2}) format('woff2');"
        "font-weight:normal;font-style:normal}",
    )
    voyager = read(
        tarball("datavoyager", VOYAGER_SCRIPTS[-1][1]), "package/build/style.css"
    ).decode()
    if "url(" in voyager:
        sys.exit("datavoyager: style.css now references files; vendor them")
    return (
        f"/* font-awesome@{FONT_AWESOME} (CSS: MIT, font: OFL-1.1) */\n"
        f"{strip_source_maps(css)}\n"
        f"/* datavoyager@{VOYAGER_SCRIPTS[-1][1]} (BSD-3-Clause) */\n"
        f"{strip_source_maps(voyager)}\n"
    )


def vendor_voyager() -> dict[str, str]:
    VOYAGER.mkdir(parents=True, exist_ok=True)
    patches = {name: [] for name, _, _ in VOYAGER_PATCHES}
    for name, old, new in VOYAGER_PATCHES:
        patches[name].append((old, new))

    parts = ["/* Vega Voyager and its dependencies, vendored by scripts/vendor.py */\n"]
    licenses = []
    versions = {}
    for name, version, path in VOYAGER_SCRIPTS:
        tar = tarball(name, version)
        lic = json.loads(read(tar, "package/package.json")).get("license", "?")
        if path is None:
            source = wrap_commonjs()
        else:
            source = read(tar, f"package/{path}").decode()
        for old, new in patches.pop(name, []):
            if source.count(old) != 1:
                sys.exit(f"Patch for {name}@{version} no longer applies; review it")
            source = source.replace(old, new)
        if name == "datavoyager":
            parts.append(f"/* --- wagtail-vega: globals for lib-voyager --- */\n{VOYAGER_GLOBALS}")
        parts.append(f"\n/* --- {name}@{version} ({lic}) --- */\n;{strip_source_maps(source)}\n")
        versions[name] = version
    for name, (version, _path) in VOYAGER_COMMONJS.items():
        versions[name] = version
    versions["font-awesome"] = FONT_AWESOME
    if patches:
        sys.exit(f"Patches for unknown packages: {sorted(patches)}")

    for name, version in versions.items():
        if name == "font-awesome":
            text = (
                "Font Awesome 4.7.0 by Dave Gandy - http://fontawesome.io\n"
                "Font: SIL OFL 1.1 (http://scripts.sil.org/OFL). "
                "CSS: MIT License (https://opensource.org/licenses/mit-license.html)\n"
            )
        else:
            text = license_text(name, version)
        licenses.append(f"{'=' * 72}\n{name}@{version}\n{'=' * 72}\n{text.strip()}\n")

    outputs = {
        "voyager.js": "".join(parts),
        "voyager.css": voyager_css(),
        "LICENSES.txt": "\n".join(licenses),
    }
    for filename, content in outputs.items():
        dest = VOYAGER / filename
        dest.write_text(content)
        print(f"wrote {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KiB)")
    return versions


def main() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    tars = {name: tarball(name, v) for name, v in PACKAGES.items()}

    for name, member, dest in FILES:
        dest.write_bytes(read(tars[name], member))
        print(f"wrote {dest.relative_to(ROOT)}")

    interp = read(tars["vega-interpreter"], "package/build/vega-interpreter.js")
    dest = STATIC / "vega-interpreter.js"
    dest.write_text(wrap_interpreter(interp.decode()))
    print(f"wrote {dest.relative_to(ROOT)}")

    for name in PACKAGES:
        lic = read(tars[name], "package/LICENSE")
        (STATIC / f"{name}.LICENSE").write_bytes(lic)

    voyager = vendor_voyager()
    versions = {**PACKAGES, "voyager": voyager}
    (STATIC / "VERSIONS.json").write_text(json.dumps(versions, indent=2) + "\n")


if __name__ == "__main__":
    main()
