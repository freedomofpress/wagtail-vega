import pytest

from wagtail_vega import ssr
from wagtail_vega.blocks import ChartBlock

pytestmark = pytest.mark.skipif(not ssr.is_available(), reason="vl-convert not installed")


def test_render_svg_with_css_var_fallbacks(vega_settings, vl_bar):
    vega_settings.update(
        SSR=True,
        THEMES={
            "t": {
                "config": {"mark": {"color": "var(--brand)"}},
                "fallbacks": {"--brand": "#abcdef"},
            }
        },
        DEFAULT_THEME="t",
    )
    block = ChartBlock()
    value = block.to_python(
        {
            "spec": vl_bar,
            "data": [{"name": "source", "source_type": "paste", "paste": "a,b\nx,1"}],
        }
    )
    html = block.render(value)
    assert '<div class="wagtail-vega__ssr"><svg' in html
    assert "#abcdef" in html
    assert "<noscript>" not in html
    # the client still gets the unresolved var() so page CSS can apply
    assert "var(--brand)" in html


def test_ssr_blocks_unlisted_hosts(vega_settings, vl_bar):
    vl_bar["data"] = {"url": "https://example.com/data.csv"}
    assert ssr.allowed_base_urls(vl_bar) == []
    vega_settings["ALLOWED_DATA_HOSTS"] = ["example.com"]
    assert ssr.allowed_base_urls(vl_bar) == ["https://example.com/"]


def test_ssr_failure_returns_none(vega_settings):
    assert ssr.render_svg({"$schema": "x", "mark": 5}, "vega-lite") is None


def test_ssr_serialises_decimals_as_numbers(monkeypatch):
    from decimal import Decimal

    seen = {}
    monkeypatch.setattr(
        ssr.vl_convert,
        "vegalite_to_svg",
        lambda spec, **kw: seen.setdefault("spec", spec) and "<svg/>",
    )
    ssr.render_svg({"datasets": {"s": [{"v": Decimal("1.5")}]}, "unique": 42}, "vega-lite")
    assert seen["spec"]["datasets"]["s"][0]["v"] == 1.5


def test_ssr_skips_relative_urls(vl_bar, caplog):
    vl_bar["data"] = {"url": "/media/data.csv"}
    assert ssr.render_svg(vl_bar, "vega-lite") is None
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_ssr_base_urls_normalised(vega_settings, vl_bar):
    vega_settings["ALLOWED_DATA_HOSTS"] = ["ok.org"]
    vl_bar["data"] = {"url": "/\\evil.example/x.csv"}
    assert ssr.allowed_base_urls(vl_bar) == []


def test_builtin_theme_applies_to_vega_and_vega_lite(vega_settings, vl_bar, vg_bar):
    """vl-convert only takes named themes for Vega-Lite; we merge the config
    ourselves so Vega specs match the browser too (#21)."""
    dark = ssr.builtin_theme("dark")
    assert dark["background"] == "#333"
    for spec, kind in ((vl_bar, "vega-lite"), (vg_bar, "vega")):
        spec = {**spec, "data": spec["data"]}
        if kind == "vega-lite":
            spec["datasets"] = {"source": [{"a": "x", "b": 1}]}
        svg = ssr.render_svg(spec, kind, vega_theme="dark")
        assert svg and "#333" in svg, kind


def test_spec_config_wins_over_builtin_theme(vega_settings, vl_bar):
    vl_bar["datasets"] = {"source": [{"a": "x", "b": 1}]}
    vl_bar["config"] = {"background": "#123456"}
    svg = ssr.render_svg(vl_bar, "vega-lite", vega_theme="dark")
    assert "#123456" in svg and "#333" not in svg


def test_unknown_builtin_theme_is_logged(caplog):
    assert ssr.builtin_theme("nope") is None
    assert "unknown built-in theme 'nope'" in caplog.text
