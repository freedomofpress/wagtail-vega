import pytest

from wagtail_vega.spec import (
    SpecError,
    dataset_references,
    deep_merge,
    disallowed_urls,
    host_allowed,
    inject_datasets,
    remote_data,
    spec_kind,
)

from .conftest import VG, VL


def test_spec_kind():
    assert spec_kind({"$schema": VL}) == "vega-lite"
    assert spec_kind({"$schema": VG}) == "vega"
    with pytest.raises(SpecError):
        spec_kind({})
    with pytest.raises(SpecError):
        spec_kind({"$schema": "https://example.com/schema.json"})


def test_inject_vega_lite_inline(vl_bar):
    out = inject_datasets(vl_bar, {"source": [{"a": "x", "b": 1}]})
    assert out["datasets"] == {"source": [{"a": "x", "b": 1}]}
    assert out["data"] == {"name": "source"}
    assert "datasets" not in vl_bar  # input not mutated


def test_inject_vega_lite_keeps_existing_datasets(vl_bar):
    vl_bar["datasets"] = {"other": [1]}
    out = inject_datasets(vl_bar, {"source": []})
    assert out["datasets"] == {"other": [1], "source": []}


def test_inject_vega_lite_remote_rewrites_nested_refs(vl_bar):
    spec = {
        "$schema": VL,
        "layer": [vl_bar, {**vl_bar, "data": {"name": "source", "format": {"parse": {}}}}],
        "transform": [{"lookup": "a", "from": {"data": {"name": "source"}, "key": "a"}}],
    }
    out = inject_datasets(spec, {"source": remote_data("https://x.org/d.csv", "csv")})
    assert out["layer"][0]["data"] == {"url": "https://x.org/d.csv", "format": {"type": "csv"}}
    # remote format wins over the spec's format when both are given
    assert out["layer"][1]["data"]["url"] == "https://x.org/d.csv"
    assert out["transform"][0]["from"]["data"]["url"] == "https://x.org/d.csv"
    assert "datasets" not in out


def test_inject_vega(vg_bar):
    out = inject_datasets(vg_bar, {"source": [{"a": "y", "b": 2}], "extra": [1]})
    data = {d["name"]: d for d in out["data"]}
    assert data["source"]["values"] == [{"a": "y", "b": 2}]
    assert data["filtered"]["transform"]  # untouched
    assert data["extra"] == {"name": "extra", "values": [1]}


def test_inject_vega_remote_keeps_transforms(vg_bar):
    vg_bar["data"][0]["transform"] = [{"type": "filter", "expr": "true"}]
    out = inject_datasets(vg_bar, {"source": remote_data("/data.json", "json")})
    src = out["data"][0]
    assert src["url"] == "/data.json" and "values" not in src
    assert src["transform"]


def test_deep_merge():
    assert deep_merge({"a": {"b": 1, "c": 2}}, None, {"a": {"c": 3}, "d": 4}) == {
        "a": {"b": 1, "c": 3},
        "d": 4,
    }


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("/media/data.csv", True),
        ("data.csv", True),
        ("https://data.example.org/x.csv", True),
        ("https://example.org/x.csv", True),
        ("https://evil.org/x.csv", False),
        ("https://example.org.evil.org/x.csv", False),
        ("//evil.org/x.csv", False),
        ("javascript:alert(1)", False),
        ("data:text/csv,a", False),
        ("ftp://example.org/x", False),
    ],
)
def test_host_allowed(url, allowed):
    assert host_allowed(url, ["*.example.org"]) is allowed


def test_disallowed_urls_walks_whole_spec(vl_bar):
    vl_bar["layer"] = [
        {"data": {"url": "https://evil.org/a.json"}},
        {"mark": {"type": "image"}, "encoding": {"url": {"value": "https://ok.org/i.png"}}},
    ]
    vl_bar["data"] = {"url": "https://ok.org/d.csv"}
    assert disallowed_urls(vl_bar, ["ok.org"]) == ["https://evil.org/a.json"]


@pytest.mark.parametrize(
    "url,fmt,expected",
    [
        ("https://x.org/d.csv", None, {"type": "csv"}),
        ("/media/d.TSV?v=2", None, {"type": "tsv"}),
        ("https://x.org/api/rows.json#frag", None, {"type": "json"}),
        ("https://x.org/api/rows", None, None),
        ("https://x.org/d.csv", "json", {"type": "json"}),
    ],
)
def test_remote_data_infers_format(url, fmt, expected):
    ref = remote_data(url, fmt)
    assert ref["url"] == url
    assert ref.get("format") == expected


# Must match datasetReferences in chart-block.js (tests/js/chart-block.test.mjs)
def test_dataset_references_vega_lite(vl_bar):
    assert dataset_references(vl_bar) == [(("data", "name"), "source")]
    spec = {
        "$schema": VL,
        "datasets": {"own": [{"a": 1}]},
        "layer": [
            {"data": {"name": "source", "format": {"type": "csv"}}, "mark": "bar"},
            {"data": {"name": "own"}, "mark": "rule"},
            {"data": {"url": "x.csv"}, "mark": "point"},
            {
                "mark": "line",
                "transform": [{"lookup": "id", "from": {"data": {"name": "extra"}, "key": "id"}}],
                # Inline rows are data, not spec
                "data": {"values": [{"data": {"name": "nope"}}]},
            },
        ],
    }
    assert dataset_references(spec) == [
        (("layer", 0, "data", "name"), "source"),
        (("layer", 3, "transform", 0, "from", "data", "name"), "extra"),
    ]


def test_dataset_references_vega(vg_bar):
    # "source" has values and "filtered" a source: neither comes from outside
    assert dataset_references(vg_bar) == []
    vg_bar["data"][0] = {"name": "source"}
    vg_bar["data"].append({"name": "seq", "transform": [{"type": "sequence", "start": 0}]})
    assert dataset_references(vg_bar) == [(("data", 0, "name"), "source")]


@pytest.mark.parametrize("spec", [None, [], {}, {"data": {"name": "x"}}, {"$schema": "x"}])
def test_dataset_references_without_a_known_schema(spec):
    assert dataset_references(spec) == []
