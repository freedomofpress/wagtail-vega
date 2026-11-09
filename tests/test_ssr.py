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
