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
from wagtail_vega.blocks import BaseChartBlock, ChartBlock, DatasetBlock, SpecBlock
from wagtail_vega.templatetags.wagtail_vega import wagtail_vega_assets


def payload(html):
    match = re.search(
        r'<script id="[^"]+-payload" type="application/json">(.*?)</script>', html, re.S
    )
    return json.loads(match.group(1))


def dataset(name, kind, value):
    """Shorthand for a DatasetBlock value: kind is csv/json (pasted),
    document (a pk) or url (a {"url", "format"} dict)."""
    if kind in ("csv", "json"):
        text = value if isinstance(value, str) else json.dumps(value)
        return {"name": name, "source_type": "paste", "paste": text}
    if kind == "document":
        return {"name": name, "source_type": "document", "document": value}
    return {"name": name, "source_type": "url", **value}


def chart_value(block, spec, data=(), **extra):
    return block.to_python(
        {
            "spec": spec,
            "data": [dataset(*d) for d in data],
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
    """CSP-safe mode needs no extra script: vega-embed bundles vega-interpreter."""
    vega_settings["CSP_SAFE"] = True
    html = wagtail_vega_assets({"request": RequestFactory().get("/")})
    assert "vega-interpreter" not in html
    assert (
        html.index("vega.min.js") < html.index("vega-embed.min.js") < html.index("wagtail-vega.js")
    )


def test_assets_tag_without_request_uses_loader(vega_settings):
    html = wagtail_vega_assets({})
    assert "wagtail-vega.css" in html
    assert 'src="/static/wagtail_vega/wagtail-vega-loader.js"' in html
    attr = html.split('data-scripts="', 1)[1].split('"', 1)[0]
    assert json.loads(attr.replace("&quot;", '"')) == [
        "/static/wagtail_vega/vendor/vega.min.js",
        "/static/wagtail_vega/vendor/vega-lite.min.js",
        "/static/wagtail_vega/vendor/vega-embed.min.js",
        "/static/wagtail_vega/wagtail-vega.js",
    ]
    assert '<script src="/static/wagtail_vega/vendor/' not in html
    # Same output every time: the loader de-duplicates in the browser
    assert wagtail_vega_assets({}) == html


def test_payload_precedes_element(vega_settings, vl_bar):
    block = ChartBlock()
    html = block.render(chart_value(block, vl_bar, [("source", "csv", "a,b\nx,1")]))
    assert html.index('type="application/json"') < html.index("<wagtail-vega-chart")


def test_template_strings_are_translatable(vega_settings, vl_bar):
    from unittest import mock

    vega_settings["FALLBACK_TABLE_MAX_ROWS"] = 1
    block = ChartBlock()
    value = chart_value(block, vl_bar, [("source", "csv", "a\n1\n2")])
    html = block.render(value)
    assert "Chart data" in html and "Showing 1 of 2 rows." in html
    assert "This chart needs JavaScript to display." in html

    # {% translate %} goes through gettext_lazy, {% blocktranslate count %}
    # through ngettext: fake a catalogue that marks every translated string.
    with (
        mock.patch("django.template.base.gettext_lazy", side_effect=lambda s: "~" + s),
        mock.patch(
            "django.utils.translation.ngettext",
            side_effect=lambda s, p, n: "~" + (s if n == 1 else p),
        ),
    ):
        html = block.render(value)
    assert "~Chart data" in html
    assert "~This chart needs JavaScript to display." in html
    assert "~Showing 1 of 2 rows." in html
    assert 'data-error-message="~Sorry, this chart couldn' in html


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
                    "data": [{"name": "source", "source_type": "paste", "paste": "a,b\nx,1"}],
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


# -- DatasetBlock --------------------------------------------------------------


def test_pasted_tsv_and_json(vl_bar):
    block = ChartBlock()
    value = chart_value(
        block, vl_bar, [("source", "csv", "a\tb\nx\t1,000"), ("more", "json", [{"a": "z"}])]
    )
    assert block.get_datasets(value) == {"source": [{"a": "x", "b": 1000}], "more": [{"a": "z"}]}


@pytest.mark.parametrize(
    "data,field",
    [
        ({"source_type": "paste", "paste": ""}, "paste"),
        ({"source_type": "paste", "paste": "header_only"}, "paste"),
        ({"source_type": "paste", "paste": '{"not": "rows"}'}, "paste"),
        ({"source_type": "paste", "paste": "[oops"}, "paste"),
        ({"source_type": "document", "document": None}, "document"),
        ({"source_type": "url", "url": ""}, "url"),
    ],
)
def test_dataset_requires_input_for_selected_source(data, field):
    block = DatasetBlock()
    with pytest.raises(StructBlockValidationError) as exc:
        block.clean(block.to_python({"name": "source", **data}))
    assert set(exc.value.block_errors) == {field}


def test_dataset_clears_inputs_for_other_sources(vega_settings):
    vega_settings["ALLOWED_DATA_HOSTS"] = ["ok.org"]
    block = DatasetBlock()
    value = block.to_python(
        {
            "name": "s",
            "source_type": "url",
            "paste": "a\n1",
            "url": "https://ok.org/x.csv",
            "format": "csv",
        }
    )
    cleaned = block.clean(value)
    assert not cleaned["paste"] and cleaned["url"] == "https://ok.org/x.csv"


def test_chart_block_field_order():
    assert list(ChartBlock().child_blocks) == ["data", "spec", "description", "caption", "theme"]

    class Reordered(BaseChartBlock):
        field_order = ("caption", "nope")

    assert list(Reordered().child_blocks) == ["caption", "spec", "description"]

    class Sub(ChartBlock):  # subclasses inherit the order
        pass

    assert list(Sub().child_blocks)[0] == "data"


def test_dataset_block_admin_adapter():
    from wagtail.admin.telepath import JSContext

    ctx = JSContext()
    ctx.pack(DatasetBlock())
    assert "wagtail_vega/admin/dataset-block.js" in str(ctx.media)
    assert "wagtail_vega/admin/dataset-block.css" in str(ctx.media)


@pytest.mark.parametrize(
    "url,ok",
    [
        ("/media/data.csv", True),
        ("https://ok.org/d.csv", True),
        ("http://ok.org/d.csv", True),
        ("//evil.org/d.csv", False),
        ("javascript:alert(1)", False),
        ("ftp://ok.org/d.csv", False),
        ("data.csv", False),
    ],
)
def test_dataset_url_accepts_relative_paths(vega_settings, url, ok):
    vega_settings["ALLOWED_DATA_HOSTS"] = ["ok.org"]
    block = DatasetBlock()
    value = block.to_python({"name": "s", "source_type": "url", "url": url})
    if ok:
        assert block.clean(value)["url"] == url
    else:
        with pytest.raises(StructBlockValidationError):
            block.clean(value)


# -- Editor experience --------------------------------------------------------


def test_empty_spec_field_is_empty_not_null():
    """A new chart's spec editor starts empty (showing its placeholder), not
    with the JSON text "null"."""
    block = SpecBlock()
    assert not block.get_form_state(None)  # was "null"
    assert not block.get_form_state(block.get_default())
    assert block.field.prepare_value(None) == ""


def test_spec_and_paste_editors_have_example_placeholders(vl_bar):
    from django.utils.html import escape

    from wagtail_vega.blocks import PASTE_PLACEHOLDER, SPEC_PLACEHOLDER

    html = SpecBlock().field.widget.render("spec", None)
    assert f'placeholder="{escape(SPEC_PLACEHOLDER)}"' in html
    # The example is a valid spec that loads a dataset called "source"
    example = json.loads(str(SPEC_PLACEHOLDER).split("\n", 2)[2])
    assert SpecBlock().clean(example) == example
    assert example["data"] == {"name": "source"}
    assert "placeholder" not in SpecBlock(placeholder="").field.widget.attrs

    paste = DatasetBlock().child_blocks["paste"]
    assert paste.label == "Pasted data"
    assert f'placeholder="{escape(PASTE_PLACEHOLDER)}"' in paste.field.widget.render("p", "")


def test_spec_must_only_load_the_charts_datasets(vl_bar):
    block = ChartBlock()
    assert block.clean(chart_value(block, vl_bar, [("source", "csv", "a\n1")]))

    with pytest.raises(StructBlockValidationError) as exc:
        block.clean(chart_value(block, vl_bar))
    [message] = exc.value.block_errors["spec"].messages
    # Prefixed with the path, so the code editor underlines the name
    assert message == 'data.name: This chart has no dataset called "source". Add one under Data.'

    with pytest.raises(StructBlockValidationError) as exc:
        block.clean(chart_value(block, vl_bar, [("sales", "csv", "a\n1"), ("x", "csv", "a\n1")]))
    assert exc.value.block_errors["spec"].messages == [
        'data.name: This chart has no dataset called "source". Use one of its datasets '
        "(sales, x), or add one under Data."
    ]

    # Data in the spec itself is fine
    vl_bar["data"] = {"values": [{"a": "x", "b": 1}]}
    assert block.clean(chart_value(block, vl_bar))


def test_chart_block_admin_adapter():
    from wagtail.admin.telepath import JSContext

    ctx = JSContext()
    packed = ctx.pack(ChartBlock())
    assert "wagtail_vega/admin/chart-block.js" in str(ctx.media)
    assert packed["_type"] == "wagtail_vega.blocks.ChartBlock"
    meta = packed["_args"][2]
    assert set(meta["wagtailVega"]["missingDataset"]) == {"none", "some"}
    assert meta["description"]
    # Subclasses, including ones with data from code, get it too
    assert JSContext().pack(DonationsChartBlock())["_type"] == "wagtail_vega.blocks.ChartBlock"


# -- Reader experience --------------------------------------------------------


def test_fallback_table_marks_numeric_columns(vega_settings, vl_bar):
    block = ChartBlock()
    rows = [{"a": "x", "b": 1, "c": True}, {"a": "y", "c": False}]
    value = chart_value(block, vl_bar, [("source", "json", rows)])
    [table] = block.build_chart(value).tables
    assert [c["numeric"] for c in table["head"]] == [False, True, False]
    assert table["cells"][0][1] == {"value": 1, "numeric": True}
    assert table["rows"] == [["x", 1, True], ["y", None, False]]  # unchanged

    html = block.render(value)
    assert '<th scope="col" class="is-numeric">b</th>' in html
    assert '<td class="is-numeric">1</td>' in html
    assert '<th scope="col">a</th>' in html
    assert '<div class="wagtail-vega__table">' in html


def test_messages_for_readers(vega_settings, vl_bar):
    block = ChartBlock()
    value = chart_value(block, vl_bar, [("source", "csv", "a\n1")])
    html = block.render(value)
    assert "This chart needs JavaScript to display. Its data is under “Chart data” below." in html
    assert (
        'data-error-message="Sorry, this chart couldn&#x27;t be displayed. Its data is under '
        '“Chart data” below."' in html
    )

    vega_settings["FALLBACK_TABLE"] = False
    html = block.render(value)
    assert "This chart needs JavaScript to display.</p>" in html
    assert 'data-error-message="Sorry, this chart couldn&#x27;t be displayed."' in html


@pytest.mark.parametrize(
    "url", ["/\\evil.example/x.csv", " //evil.example/x.csv", "/\t/evil.example/x"]
)
def test_dataset_url_rejects_urls_browsers_resolve_elsewhere(vega_settings, url):
    vega_settings["ALLOWED_DATA_HOSTS"] = ["ok.org"]
    block = DatasetBlock()
    with pytest.raises(StructBlockValidationError):
        block.clean(block.to_python({"name": "s", "source_type": "url", "url": url}))


# -- The site's own hosts (#5) --------------------------------------------------


@pytest.fixture
def own_site(db, settings):
    from wagtail.models import Site

    settings.WAGTAILADMIN_BASE_URL = "https://admin.example.org"
    site = Site.objects.get(is_default_site=True)
    site.hostname = "www.example.org"
    site.save()
    Site.objects.create(hostname="localhost", port=8001, root_page=site.root_page)
    return site


def test_site_hosts(own_site):
    from wagtail_vega.conf import get_allowed_hosts, site_hosts

    assert site_hosts() == ["admin.example.org", "www.example.org"]  # no localhost
    assert set(get_allowed_hosts()) >= {"admin.example.org", "www.example.org"}


def test_own_site_absolute_urls_are_allowed(own_site, vega_settings, vl_bar):
    vl_bar["data"] = {"url": "https://www.example.org/media/data.csv"}
    assert SpecBlock().clean(vl_bar)
    vl_bar["data"] = {"url": "http://localhost/data.csv"}
    with pytest.raises(ValidationError, match="localhost"):
        SpecBlock().clean(vl_bar)
    block = DatasetBlock()
    url = "https://admin.example.org/media/d.csv"
    assert block.clean(block.to_python({"name": "s", "source_type": "url", "url": url}))


def test_own_site_hosts_reach_the_browser(own_site, vega_settings, vl_bar):
    block = ChartBlock()
    chart = block.build_chart(chart_value(block, vl_bar))
    assert "www.example.org" in chart.payload["allowedHosts"]


def test_blocked_urls_from_code_are_logged(vega_settings, vl_bar, caplog):
    from wagtail_vega.spec import remote_data

    class FromAPI(BaseChartBlock):
        def get_datasets(self, value, context=None):
            return {
                "source": remote_data("https://api.elsewhere.example/rows.csv"),
                "local": remote_data("/media/rows.csv"),
            }

    block = FromAPI()
    block.build_chart(block.to_python({"spec": vl_bar}))
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "FromAPI.get_datasets()" in warnings[0] and "api.elsewhere.example" in warnings[0]


# -- Embed options (#2) ---------------------------------------------------------


def test_embed_options_merge_over_defaults(vega_settings, vl_bar):
    vega_settings["EMBED_OPTIONS"] = {"renderer": "canvas"}
    block = ChartBlock()
    options = block.build_chart(chart_value(block, vl_bar)).embed_options
    assert options["renderer"] == "canvas"
    assert options["actions"] is False  # default kept
    assert options["defaultStyle"] is False
    assert options["tooltip"] == {"disableDefaultStyle": True}


def test_tooltip_options_are_kept(vega_settings, vl_bar):
    class Custom(ChartBlock):
        class Meta:
            embed_options = {"tooltip": {"offsetX": 20, "theme": "custom"}, "actions": True}

    block = Custom()
    options = block.build_chart(chart_value(block, vl_bar)).embed_options
    assert options["tooltip"] == {"offsetX": 20, "theme": "custom", "disableDefaultStyle": True}
    assert options["actions"] is True


def test_tooltips_can_be_turned_off(vega_settings, vl_bar):
    vega_settings["EMBED_OPTIONS"] = {"tooltip": False}
    block = ChartBlock()
    assert block.build_chart(chart_value(block, vl_bar)).embed_options["tooltip"] is False


def test_subclasses_can_add_dataset_names(vl_bar):
    """A ChartBlock subclass that adds datasets from code declares their names,
    so specs loading them pass validation, on save and in the editor."""
    from wagtail.admin.telepath import JSContext

    class WithLookup(ChartBlock):
        extra_dataset_names = ("regions",)

        def get_datasets(self, value, context=None):
            return {**super().get_datasets(value, context), "regions": [{"id": 1}]}

    spec = {
        **vl_bar,
        "transform": [{"lookup": "a", "from": {"data": {"name": "regions"}, "key": "id"}}],
    }
    block = WithLookup()
    assert block.clean(chart_value(block, spec, [("source", "csv", "a\n1")]))
    with pytest.raises(StructBlockValidationError):
        ChartBlock().clean(chart_value(ChartBlock(), spec, [("source", "csv", "a\n1")]))
    meta = JSContext().pack(block)["_args"][2]
    assert meta["wagtailVega"]["extraDatasetNames"] == ["regions"]


def test_dark_fallbacks_reach_the_page_and_api(vega_settings, vl_bar):
    vega_settings.update(
        THEMES={
            "t": {
                "config": {"font": "A"},
                "fallbacks": {"--x": "#fff"},
                "dark_fallbacks": {"--x": "#000"},
            }
        },
        DEFAULT_THEME="t",
    )
    block = ChartBlock()
    value = chart_value(block, vl_bar, [("source", "csv", "a\n1")])
    payload = block.build_chart(value).payload
    assert payload["fallbacks"] == {"--x": "#fff"}
    assert payload["darkFallbacks"] == {"--x": "#000"}
    assert block.get_api_representation(value)["darkFallbacks"] == {"--x": "#000"}
