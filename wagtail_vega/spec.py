"""Pure functions for inspecting and transforming Vega / Vega-Lite specs."""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

VEGA = "vega"
VEGA_LITE = "vega-lite"

# A dataset is either inline rows or a remote reference: {"url": ..., "format": {...}}
Dataset = list | dict


class SpecError(ValueError):
    """The spec has no ``$schema``, or one that isn't Vega or Vega-Lite."""


def spec_kind(spec: Mapping[str, Any]) -> str:
    """Return ``"vega"`` or ``"vega-lite"`` based on the spec's ``$schema``."""
    schema = spec.get("$schema")
    if not isinstance(schema, str):
        raise SpecError(
            'The spec needs a "$schema", e.g. "https://vega.github.io/schema/vega-lite/v6.json".'
        )
    path = urlsplit(schema).path
    if "/vega-lite/" in path:
        return VEGA_LITE
    if "/vega/" in path:
        return VEGA
    raise SpecError(f'Unrecognised "$schema": {schema}')


def deep_merge(*dicts: Mapping[str, Any] | None) -> dict[str, Any]:
    """Recursively merge dicts; later arguments win."""
    out: dict[str, Any] = {}
    for d in dicts:
        if not d:
            continue
        for key, value in d.items():
            if isinstance(value, Mapping) and isinstance(out.get(key), dict):
                out[key] = deep_merge(out[key], value)
            else:
                out[key] = copy.deepcopy(value)
    return out


def _walk(node: Any) -> Iterator[tuple[str | None, Any, Any]]:
    """Yield ``(key, value, parent)`` for every value in a JSON tree."""
    stack: list[tuple[str | None, Any, Any]] = [(None, node, None)]
    while stack:
        key, value, parent = stack.pop()
        yield key, value, parent
        if isinstance(value, dict):
            stack.extend((k, v, value) for k, v in value.items())
        elif isinstance(value, list):
            stack.extend((None, v, value) for v in value)


FORMAT_EXTENSIONS = {".csv": "csv", ".tsv": "tsv", ".json": "json"}


def remote_data(url: str, fmt: str | None = None) -> dict[str, Any]:
    """A remote dataset: ``{"url": url, "format": {"type": fmt}}``. Return
    these from ``BaseChartBlock.get_datasets()`` to have the browser load the
    data.

    If ``fmt`` isn't given, it's inferred from the URL's extension (``.csv``,
    ``.tsv``, ``.json``). Vega, unlike Vega-Lite, would otherwise read every
    URL as JSON. With no known extension, the format is left unset.
    """
    if not fmt:
        suffix = PurePosixPath(urlsplit(url).path).suffix.lower()
        fmt = FORMAT_EXTENSIONS.get(suffix)
    ref: dict[str, Any] = {"url": url}
    if fmt:
        ref["format"] = {"type": fmt}
    return ref


def is_remote(dataset: Dataset) -> bool:
    """Whether a dataset is a remote reference (a dict with a ``url``)
    rather than inline rows."""
    return isinstance(dataset, dict) and "url" in dataset


def inject_datasets(spec: Mapping[str, Any], datasets: Mapping[str, Dataset]) -> dict:
    """Return a copy of ``spec`` with named datasets filled in.

    Vega-Lite: inline rows go into the top-level ``datasets``; remote datasets
    replace every ``{"name": <name>}`` data reference.

    Vega: the matching entry of the top-level ``data`` array gets ``values``
    (or ``url``/``format``), keeping its transforms. Unreferenced datasets
    are appended so that signals/expressions can still use them.
    """
    spec = copy.deepcopy(dict(spec))
    if not datasets:
        return spec

    if spec_kind(spec) == VEGA_LITE:
        inline = {k: v for k, v in datasets.items() if not is_remote(v)}
        remote = {k: v for k, v in datasets.items() if is_remote(v)}
        if inline:
            spec["datasets"] = {**spec.get("datasets", {}), **copy.deepcopy(inline)}
        if remote:
            for key, value, _parent in _walk(spec):
                if key == "data" and isinstance(value, dict):
                    name = value.get("name")
                    if name in remote and set(value) <= {"name", "format"}:
                        value.pop("name")
                        value.update(copy.deepcopy(remote[name]))
        return spec

    entries = spec.setdefault("data", [])
    by_name = {e.get("name"): e for e in entries if isinstance(e, dict)}
    for name, dataset in datasets.items():
        entry = by_name.get(name)
        if entry is None:
            entry = {"name": name}
            entries.append(entry)
        for k in ("values", "url", "source"):
            entry.pop(k, None)
        if is_remote(dataset):
            entry.update(copy.deepcopy(dataset))
        else:
            entry["values"] = copy.deepcopy(dataset)
    return spec


JSONPath = tuple[str | int, ...]

# A data entry with only these keys gets its data from outside the spec
EXTERNAL_DATA_KEYS = {"name", "format"}


def dataset_references(spec: Any) -> list[tuple[JSONPath, str]]:
    """``(path, name)`` for each dataset the spec expects to be given by name,
    in document order. ``path`` leads to the ``name`` value.

    Vega-Lite: every ``"data": {"name": ...}``, at any depth (layers, lookups),
    except names defined in the spec's own top-level ``datasets``.

    Vega: entries of the top-level ``data`` array that have only a ``name``
    (and maybe a ``format``), with no ``values``, ``url``, ``source`` or
    transforms of their own.

    Specs without a recognisable ``$schema`` have none.
    """
    if not isinstance(spec, Mapping):
        return []
    try:
        kind = spec_kind(spec)
    except SpecError:
        return []

    def external(entry: Any) -> bool:
        return (
            isinstance(entry, Mapping)
            and isinstance(entry.get("name"), str)
            and set(entry) <= EXTERNAL_DATA_KEYS
        )

    if kind == VEGA:
        entries = spec.get("data")
        if not isinstance(entries, list):
            return []
        return [(("data", i, "name"), e["name"]) for i, e in enumerate(entries) if external(e)]

    own = spec.get("datasets")
    own = set(own) if isinstance(own, Mapping) else set()
    found: list[tuple[JSONPath, str]] = []

    def walk(node: Any, path: JSONPath) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key in ("datasets", "values"):
                    continue  # inline data, not spec
                if key == "data" and external(value):
                    if value["name"] not in own:
                        found.append(((*path, key, "name"), value["name"]))
                else:
                    walk(value, (*path, key))
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, (*path, i))

    walk(spec, ())
    return found


def iter_url_paths(spec: Any, path: JSONPath = ()) -> Iterator[tuple[JSONPath, str]]:
    """Yield ``(path, url)`` for every literal ``url`` string in the spec (data
    sources, images), in document order. ``path`` is the keys and indices
    leading to the URL, e.g. ``("data", "url")``."""
    if isinstance(spec, dict):
        for key, value in spec.items():
            if key == "url" and isinstance(value, str):
                yield (*path, key), value
            else:
                yield from iter_url_paths(value, (*path, key))
    elif isinstance(spec, list):
        for i, value in enumerate(spec):
            yield from iter_url_paths(value, (*path, i))


def iter_urls(spec: Any) -> Iterator[str]:
    """Yield every literal ``url`` string in the spec (data sources, images)."""
    for _path, url in iter_url_paths(spec):
        yield url


# C0 control characters and space, which browsers strip from both ends of a URL
_URL_STRIP = "".join(chr(c) for c in range(0x21))


def normalize_url(url: str) -> str:
    """Normalise a URL the way browsers do before resolving it (WHATWG URL
    parsing), so the server checks the URL the browser will actually fetch:
    leading and trailing control characters and spaces are stripped, tabs and
    newlines are removed, and backslashes count as slashes (on an http(s)
    page, ``/\\evil.example/x`` means ``//evil.example/x``)."""
    url = url.strip(_URL_STRIP)
    url = url.replace("\t", "").replace("\n", "").replace("\r", "")
    return url.replace("\\", "/")


def host_allowed(url: str, allowed_hosts: list[str]) -> bool:
    """Relative URLs are same-origin and always allowed; absolute URLs must be
    http(s) and on the allowlist (``"*.example.com"`` also matches subdomains).
    URLs are normalised first (see :func:`normalize_url`)."""
    parts = urlsplit(normalize_url(url))
    if not parts.scheme and not parts.netloc:
        return True
    # "//host/x" is fetched with the page's scheme, http(s)
    if parts.scheme not in ("", "http", "https") or not parts.hostname:
        return False
    host = parts.hostname.lower()
    for pattern in allowed_hosts:
        pattern = pattern.lower()
        if pattern == "*" or pattern == host:
            return True
        if pattern.startswith("*.") and (host == pattern[2:] or host.endswith(pattern[1:])):
            return True
    return False


def disallowed_urls(spec: Any, allowed_hosts: list[str]) -> list[str]:
    """The literal URLs in ``spec`` that :func:`host_allowed` rejects."""
    return [url for _path, url in disallowed_url_paths(spec, allowed_hosts)]


def disallowed_url_paths(spec: Any, allowed_hosts: list[str]) -> list[tuple[JSONPath, str]]:
    """Like :func:`disallowed_urls`, with the path to each URL."""
    return [(p, u) for p, u in iter_url_paths(spec) if not host_allowed(u, allowed_hosts)]
