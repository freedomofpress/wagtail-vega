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
}
# vega-embed bundles vega-interpreter (the CSP-safe expression evaluator) and
# uses it whenever charts are embedded with ast: true, so it isn't vendored
# separately.

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


_tars: dict[tuple[str, str], tarfile.TarFile] = {}


def tarball(name: str, version: str) -> tarfile.TarFile:
    if (name, version) not in _tars:
        _tars[name, version] = download(name, version)
    return _tars[name, version]


def strip_source_maps(source: str) -> str:
    # The maps aren't vendored; a dangling reference also breaks
    # ManifestStaticFilesStorage
    source = re.sub(r"^\s*//# sourceMappingURL=\S*\s*$", "", source, flags=re.M)
    return re.sub(r"/\*# sourceMappingURL=[^*]*\*/", "", source)


def main() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    tars = {name: tarball(name, v) for name, v in PACKAGES.items()}

    for name, member, dest in FILES:
        content = read(tars[name], member)
        if dest.suffix == ".js":
            # The .map files aren't vendored (see strip_source_maps)
            content = strip_source_maps(content.decode()).encode()
        dest.write_bytes(content)
        print(f"wrote {dest.relative_to(ROOT)}")

    for name in PACKAGES:
        lic = read(tars[name], "package/LICENSE")
        (STATIC / f"{name}.LICENSE").write_bytes(lic)

    (STATIC / "VERSIONS.json").write_text(json.dumps(PACKAGES, indent=2) + "\n")


if __name__ == "__main__":
    main()
