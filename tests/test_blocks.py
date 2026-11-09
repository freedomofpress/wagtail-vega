import datetime
import json
import re
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import RequestFactory
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.documents.models import Document
from wagtail.models import Page

from tests.testapp.models import ChartPage, Donation, DonationsChartBlock
from wagtail_vega.blocks import BaseChartBlock, ChartBlock, SpecBlock
from wagtail_vega.templatetags.wagtail_vega import wagtail_vega_assets


def payload(html):
    match = re.search(
        r'<script id="[^"]+-payload" type="application/json">(.*?)</script>', html, re.S
    )
    return json.loads(match.group(1))


def chart_value(block, spec, data=(), **extra):
    return block.to_python(
        {
            "spec": spec,
            "data": [{"name": n, "source": [{"type": t, "value": v}]} for n, t, v in data],
            "description": extra.get("description", ""),
            "caption": extra.get("caption", ""),
            "theme": extra.get("theme", ""),
        }
    )


# -- SpecBlock --------------------------------------------------------------


def test_spec_block_form_round_trip(vl_bar):
    block = SpecBlock()
    state = block.get_form_state(vl_bar)
    assert json.loads(state) == vl_bar and "\n  " in state  # pretty printed
    assert block.value_from_datadict({"s": state}, {}, "s") == vl_bar


def test_spec_block_invalid_json_is_redisplayed():
    block = SpecBlock()
    value = block.value_from_datadict({"s": "{oops"}, {}, "s")
    assert block.get_form_state(value) == "{oops"
    with pytest.raises(ValidationError):
        block.clean(value)


def test_spec_block_validation(vega_settings, vl_bar):
    block = SpecBlock()
    assert block.clean(vl_bar) == vl_bar
    with pytest.raises(ValidationError, match="schema"):
        block.clean({"mark": "bar"})
    with pytest.raises(ValidationError, match="JSON object"):
        block.clean([1])
    vl_bar["mark"] = "barr"
    with pytest.raises(ValidationError, match="mark"):
        block.clean(vl_bar)


def test_spec_block_url_allowlist(vega_settings, vl_bar):
    vl_bar["data"] = {"url": "https://evil.org/x.csv"}
    with pytest.raises(ValidationError, match="evil.org"):
        SpecBlock().clean(vl_bar)
    vega_settings["ALLOWED_DATA_HOSTS"] = ["evil.org"]
    assert SpecBlock().clean(vl_bar)


def test_schema_validation_can_be_disabled(vega_settings, vl_bar):
    vega_settings["VALIDATE_SCHEMA"] = False
    vl_bar["mark"] = "barr"
    assert SpecBlock().clean(vl_bar)


# -- ChartBlock data sources -------------------------------------------------


def test_csv_and_json_sources(vl_bar):
    block = ChartBlock()
    value = chart_value(
        block,
        vl_bar,
        [
            ("source", "csv", "a,b\nx,1\ny,2"),
            ("more", "json", [{"a": "z", "b": 3}]),
        ],
    )
    assert block.get_datasets(value) == {
        "source": [{"a": "x", "b": 1}, {"a": "y", "b": 2}],
        "more": [{"a": "z", "b": 3}],
    }
    assert block.clean(value)


@pytest.mark.django_db
def test_document_source(vl_bar):
    doc = Document.objects.create(title="d", file=ContentFile(b"a,b\nx,1\n", name="d.csv"))
    block = ChartBlock()
    value = chart_value(block, vl_bar, [("source", "document", doc.pk)])
    assert block.get_datasets(value) == {"source": [{"a": "x", "b": 1}]}

    bad = Document.objects.create(title="p", file=ContentFile(b"x", name="p.pdf"))
    with pytest.raises(ValidationError):
        block.clean(chart_value(block, vl_bar, [("source", "document", bad.pk)]))


def test_url_source(vega_settings, vl_bar):
    vega_settings["ALLOWED_DATA_HOSTS"] = ["ok.org"]
    block = ChartBlock()
    value = chart_value(
        block, vl_bar, [("source", "url", {"url": "https://ok.org/d.csv", "format": "csv"})]
    )
    assert block.clean(value)
    spec = block.get_spec(value)
    assert spec["data"] == {"url": "https://ok.org/d.csv", "format": {"type": "csv"}}

    bad = chart_value(
        block, vl_bar, [("source", "url", {"url": "https://evil.org/d.csv", "format": ""})]
    )
    with pytest.raises(StructBlockValidationError):
        block.clean(bad)


def test_duplicate_dataset_names(vl_bar):
    block = ChartBlock()
    value = chart_value(block, vl_bar, [("source", "csv", "a\n1"), ("source", "csv", "a\n2")])
    with pytest.raises(StructBlockValidationError) as exc:
        block.clean(value)
    assert "unique" in str(exc.value.non_block_errors)


def test_invalid_dataset_name(vl_bar):
    block = ChartBlock()
    value = chart_value(block, vl_bar, [("bad name", "csv", "a\n1")])
    with pytest.raises(StructBlockValidationError):
        block.clean(value)


# -- Theming ----------------------------------------------------------------


def test_theme_merge_order(vega_settings, vl_bar):
    vega_settings.update(
        THEMES={
            "house": {
                "config": {"font": "Inter", "axis": {"grid": False, "labelColor": "#333"}},
                "dark": {"axis": {"labelColor": "#eee"}, "background": "#000"},
            },
            "alt": {"font": "Alt"},
        },
        DEFAULT_THEME="house",
    )
    vl_bar["config"] = {"axis": {"grid": True}}
    block = ChartBlock()
    value = chart_value(block, vl_bar)
    chart = block.build_chart(value)
    # spec config wins over the theme; theme fills in the rest
    assert chart.spec["config"] == {"font": "Inter", "axis": {"grid": True, "labelColor": "#333"}}
    assert chart.dark_config == {
        "font": "Inter",
        "background": "#000",
        "axis": {"grid": True, "labelColor": "#eee"},
    }
    # editor's choice beats the default
    assert (
        block.build_chart(chart_value(block, vl_bar, theme="alt")).spec["config"]["font"] == "Alt"
    )


def test_meta_theme_beats_editor_choice(vega_settings, vl_bar):
    vega_settings.update(THEMES={"a": {"font": "A"}, "b": {"font": "B"}})

    class Fixed(ChartBlock):
        class Meta:
            theme = "b"

    block = Fixed()
    assert block.build_chart(chart_value(block, vl_bar, theme="a")).spec["config"]["font"] == "B"


def test_builtin_theme_goes_to_embed_options(vega_settings, vl_bar):
    vega_settings.update(THEMES={"dark": "vega:dark"}, DEFAULT_THEME="dark")
    block = ChartBlock()
    chart = block.build_chart(chart_value(block, vl_bar))
    assert chart.embed_options["theme"] == "dark"
    assert chart.embed_options["defaultStyle"] is False


# -- Subclassing -------------------------------------------------------------


@pytest.mark.django_db
def test_database_backed_subclass(vega_settings, vl_bar):
    Donation.objects.create(month=datetime.date(2026, 1, 1), total=Decimal("12.50"))
    vl_bar["data"] = {"name": "donations"}
    block = DonationsChartBlock()
    value = block.to_python({"spec": vl_bar, "description": "", "caption": ""})
    html = block.render(value)
    data = payload(html)["spec"]["datasets"]["donations"]
    # dates serialise as ISO strings, Decimals as numbers
    assert data == [{"month": "2026-01-01", "total": 12.5}]


def test_subclass_can_supply_spec(vega_settings, vl_bar):
    class Templated(BaseChartBlock):
        def get_spec_source(self, value):
            return vl_bar

        def get_datasets(self, value, context=None):
            return {"source": [{"a": "x", "b": 1}]}

    block = Templated()
    chart = block.build_chart(block.to_python({"spec": None}))
    assert chart.spec["mark"] == "bar"


# -- Rendering ---------------------------------------------------------------


def test_render(vega_settings, vl_bar):
    block = ChartBlock()
    value = chart_value(
        block,
        vl_bar,
        [("source", "csv", "a,b\n</script><script>alert(1)//,1")],
        description="Bars & things",
        caption="Source: us",
    )
    request = RequestFactory().get("/")
    html = block.render(value, context={"request": request})
    assert '<figure class="wagtail-vega"' in html
    assert 'aria-describedby="wagtail-vega-' in html
    assert '-description">Bars &amp; things</p>' in html
    assert 'role="img"' not in html  # would hide interactive controls
    assert '<figcaption class="wagtail-vega__caption">Source: us</figcaption>' in html
    assert "</script><script>alert" not in html  # json_script escapes
    assert payload(html)["spec"]["datasets"]["source"][0]["a"].startswith("</script>")
    assert "vega-embed.min.js" in html
    assert '<th scope="col">a</th>' in html  # fallback table
    assert "<noscript>" in html

    # assets are only emitted once per request
    html2 = block.render(value, context={"request": request})
    assert "vega-embed.min.js" not in html2


def test_assets_tag_csp_safe(vega_settings):
    vega_settings["CSP_SAFE"] = True
    html = wagtail_vega_assets({})
    assert "vega-interpreter.js" in html
    assert (
        html.index("vega.min.js")
        < html.index("vega-interpreter.js")
        < html.index("wagtail-vega.js")
    )


def test_fallback_table_truncation_and_disable(vega_settings, vl_bar):
    vega_settings["FALLBACK_TABLE_MAX_ROWS"] = 2
    block = ChartBlock()
    value = chart_value(block, vl_bar, [("source", "csv", "a\n1\n2\n3")])
    chart = block.build_chart(value)
    assert chart.tables[0]["rows"] == [[1], [2]] and chart.tables[0]["truncated"]
    vega_settings["FALLBACK_TABLE"] = False
    assert block.build_chart(value).tables == []


# -- StreamField round trip --------------------------------------------------


@pytest.mark.django_db
def test_streamfield_round_trip(vl_bar):
    root = Page.objects.get(depth=1)
    page = ChartPage(
        title="Charts",
        slug="charts",
        body=[
            (
                "chart",
                {
                    "spec": vl_bar,
                    "data": [{"name": "source", "source": [("csv", "a,b\nx,1")]}],
                    "description": "",
                    "caption": "",
                    "theme": "",
                },
            ),
        ],
    )
    root.add_child(instance=page)
    page = ChartPage.objects.get(pk=page.pk)
    block = page.body[0]
    assert block.value["spec"] == vl_bar
    assert block.block.get_datasets(block.value) == {"source": [{"a": "x", "b": 1}]}
    assert "wagtail-vega-chart" in str(block)
