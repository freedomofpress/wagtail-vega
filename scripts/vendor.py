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


def main() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    tars = {name: download(name, v) for name, v in PACKAGES.items()}

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

    (STATIC / "VERSIONS.json").write_text(json.dumps(PACKAGES, indent=2) + "\n")


if __name__ == "__main__":
    main()
