"""Custom dataset source types (#34): DatasetBlock's source_fields,
clean_source() and get_source_dataset(), the admin adapter's settings and
scripts, the system checks, and SourceRowsView."""

import datetime
import json
import logging
from decimal import Decimal

import pytest
from django import forms
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse
from wagtail import blocks
from wagtail.admin.telepath import JSContext
from wagtail.blocks.struct_block import StructBlockValidationError

from tests.testapp.models import (
    ChartPage,
    Donation,
    DonationsDatasetBlock,
    DonationsSourceChartBlock,
)
from wagtail_vega import blocks as vega_blocks
from wagtail_vega.blocks import (
    PASTE,
    SOURCE_CHOICES,
    SOURCE_FIELDS,
    BaseChartBlock,
    DatasetBlock,
    DatasetBlockAdapter,
)
from wagtail_vega.views import SourceRowsView

from .conftest import VL


@pytest.fixture
def donations(db):
    for month, total in [(1, "100.50"), (2, "20.25"), (4, "300"), (11, "5")]:
        Donation.objects.create(month=datetime.date(2026, month, 1), total=Decimal(total))


def incident_block_class(**attrs):
    """A DatasetBlock with an "incidents" source, like the issue's."""

    class IncidentDatasetBlock(DatasetBlock):
        source_fields = {**DatasetBlock.source_fields, "incidents": ("incident_filter", "group_by")}
        source_type = blocks.ChoiceBlock(
            choices=[("incidents", "Tracker incidents"), *SOURCE_CHOICES],
            default="incidents",
            widget=forms.RadioSelect,
        )
        incident_filter = blocks.CharBlock(required=False)
        group_by = blocks.MultipleChoiceBlock(
            choices=[("month", "Month"), ("state", "State")], required=False
        )

        locals().update(attrs)

    return IncidentDatasetBlock


# -- Python API ------------------------------------------------------------------


def test_built_in_sources_are_exported():
    assert [value for value, _label in SOURCE_CHOICES] == ["paste", "document", "url"]
    assert DatasetBlock.source_fields == SOURCE_FIELDS  # the old name still works
    choices = DatasetBlock().child_blocks["source_type"].field.choices
    assert [value for value, _label in choices] == ["paste", "document", "url"]


def test_custom_source_fields_are_reset_generically(vega_settings):
    block = incident_block_class()()
    value = block.to_python(
        {
            "name": "s",
            "source_type": "paste",
            "paste": "a\n1",
            "incident_filter": "?state=NY",
            "group_by": ["month"],
        }
    )
    cleaned = block.clean(value)
    # The custom source's fields are reset when another source is selected…
    assert cleaned["paste"] == "a\n1"
    assert not cleaned["incident_filter"] and not cleaned["group_by"]

    # …and the built-in sources' fields when the custom source is
    value = block.to_python(
        {"name": "s", "source_type": "incidents", "paste": "a\n1", "incident_filter": "?x=1"}
    )
    cleaned = block.clean(value)
    assert cleaned["incident_filter"] == "?x=1" and not cleaned["paste"]


def test_fields_shared_between_sources_are_kept(vega_settings):
    vega_settings["ALLOWED_DATA_HOSTS"] = ["ok.org"]

    class Block(DatasetBlock):
        # "format" belongs to URL and to the new source
        source_fields = {**DatasetBlock.source_fields, "api": ("format",)}
        source_type = blocks.ChoiceBlock(choices=[*SOURCE_CHOICES, ("api", "API")])

    block = Block()
    cleaned = block.clean(block.to_python({"name": "s", "source_type": "api", "format": "csv"}))
    assert cleaned["format"] == "csv"
    cleaned = block.clean(
        block.to_python(
            {"name": "s", "source_type": "paste", "paste": "a\n1", "format": "csv"},
        )
    )
    assert not cleaned["format"]


def test_unknown_sources_need_no_validation():
    block = incident_block_class()()
    value = block.to_python({"name": "s", "source_type": "incidents"})
    assert block.clean_source("incidents", value) == {}
    assert block.clean(value)["source_type"] == "incidents"


def test_clean_source_hook(db):
    block = DonationsDatasetBlock()
    with pytest.raises(StructBlockValidationError) as exc:
        block.clean(block.to_python({"name": "s", "source_type": "donations", "year": ""}))
    assert set(exc.value.block_errors) == {"year"}
    # The built-in sources still go through super()
    with pytest.raises(StructBlockValidationError) as exc:
        block.clean(block.to_python({"name": "s", "source_type": "paste", "paste": ""}))
    assert set(exc.value.block_errors) == {"paste"}


def test_get_source_dataset_dispatch(donations):
    block = DonationsDatasetBlock()
    value = block.to_python(
        {"name": "d", "source_type": "donations", "year": "2026", "group_by": ["quarter"]}
    )
    assert block.get_dataset(value) == [
        {"quarter": "Q1", "total": Decimal("120.75")},
        {"quarter": "Q2", "total": Decimal("300")},
        {"quarter": "Q4", "total": Decimal("5")},
    ]
    value = block.to_python({"name": "d", "source_type": "sample", "points": 3})
    assert block.get_dataset(value) == [{"x": 1, "y": 1}, {"x": 2, "y": 4}, {"x": 3, "y": 9}]
    value = block.to_python({"name": "d", "source_type": "paste", "paste": "a\n1"})
    assert block.get_dataset(value) == [{"a": 1}]


def test_unhandled_source_has_no_rows_and_warns(caplog):
    block = incident_block_class()()
    value = block.to_python({"name": "s", "source_type": "incidents", "paste": "a\n1"})
    with caplog.at_level(logging.WARNING, logger="wagtail_vega.blocks"):
        assert block.get_dataset(value) == []  # never the pasted data
    assert "IncidentDatasetBlock" in caplog.text and "'incidents'" in caplog.text


def test_dataset_block_field_order():
    assert list(DatasetBlock().child_blocks) == [
        "name",
        "source_type",
        "paste",
        "document",
        "url",
        "format",
    ]
    assert list(DonationsDatasetBlock().child_blocks)[:5] == [
        "name",
        "source_type",
        "year",
        "group_by",
        "points",
    ]
    # BaseChartBlock uses the same mixin
    assert issubclass(BaseChartBlock, vega_blocks.FieldOrderMixin)
    assert issubclass(DatasetBlock, vega_blocks.FieldOrderMixin)


# -- System checks -----------------------------------------------------------------


def check_ids(block):
    return [error.id for error in block.check()]


def test_check_passes_for_matching_sources():
    assert check_ids(DatasetBlock()) == []
    assert check_ids(DonationsDatasetBlock()) == []
    assert check_ids(incident_block_class()()) == []


def test_check_choices_without_source_fields():
    class Block(DatasetBlock):
        source_type = blocks.ChoiceBlock(choices=[*SOURCE_CHOICES, ("incidents", "Incidents")])

    errors = Block().check()
    assert [e.id for e in errors] == ["wagtail_vega.E004"]
    assert "no source_fields for 'incidents'" in errors[0].msg


def test_check_source_fields_without_choice():
    class Block(DatasetBlock):
        source_fields = {**DatasetBlock.source_fields, "incidents": ()}

    errors = Block().check()
    assert [e.id for e in errors] == ["wagtail_vega.E004"]
    assert "no source_type choice for 'incidents'" in errors[0].msg


def test_check_unknown_field_and_rows_url():
    Block = incident_block_class(
        source_fields={**DatasetBlock.source_fields, "incidents": ("incident_filter", "nope")},
        source_rows_urls={"incidents": "x", "other": "y"},
    )
    errors = Block().check()
    assert [e.id for e in errors] == ["wagtail_vega.E005", "wagtail_vega.E006"]
    assert "'nope'" in errors[0].msg and "'other'" in errors[1].msg


def test_checks_run_for_stream_fields(monkeypatch):
    """Wagtail runs block checks for every StreamField, nested blocks too."""
    monkeypatch.setattr(DonationsDatasetBlock, "source_fields", DatasetBlock.source_fields)
    errors = ChartPage.check()
    assert "wagtail_vega.E004" in [e.id for e in errors]


# -- The admin form ----------------------------------------------------------------


def script_paths(media):
    """The media's scripts as paths (Django 6 wraps them in Script objects)."""
    return [str(getattr(script, "path", script)) for script in media._js]


def adapter_meta(block):
    ctx = JSContext()
    packed = ctx.pack(block)
    meta = packed["_args"][2]
    return meta["wagtailVega"], ctx


def test_adapter_meta_has_source_fields_and_rows_urls():
    settings, _ctx = adapter_meta(DonationsDatasetBlock())
    assert settings["sourceFields"] == {
        "paste": ["paste"],
        "document": ["document"],
        "url": ["url", "format"],
        "donations": ["year", "group_by"],
        "sample": ["points"],
        "totals": [],
    }
    assert settings["rowsUrls"] == {"donations": reverse("testapp_donation_rows")}
    assert settings["rowsUrls"]["donations"].startswith("/admin/")

    settings, _ctx = adapter_meta(DatasetBlock())
    assert settings == {
        "sourceFields": {k: list(v) for k, v in SOURCE_FIELDS.items()},
        "rowsUrls": {},
    }


def test_rows_urls_can_be_paths():
    Block = incident_block_class(source_rows_urls={"incidents": "/tracker/rows/"})
    settings, _ctx = adapter_meta(Block())
    assert settings["rowsUrls"] == {"incidents": "/tracker/rows/"}


def test_adapter_extra_js_comes_after_dataset_block_js():
    _settings, ctx = adapter_meta(DonationsDatasetBlock())
    js = script_paths(ctx.media)
    names = ["data-format.js", "sources.js", "dataset-block.js", "testapp/sample-source.js"]
    positions = [next(i for i, p in enumerate(js) if p.endswith(n)) for n in names]
    assert positions == sorted(positions), js


def test_adapter_extra_js_order_survives_merging():
    """A page with both blocks merges both adapters' media; the subclass's
    script still loads after dataset-block.js."""
    ctx = JSContext()
    ctx.pack(DonationsSourceChartBlock())
    ctx.pack(vega_blocks.ChartBlock())
    js = script_paths(ctx.media)
    dataset_block = next(i for i, p in enumerate(js) if p.endswith("dataset-block.js"))
    sample = next(i for i, p in enumerate(js) if p.endswith("sample-source.js"))
    assert dataset_block < sample


def test_adapter_extra_css():
    class Adapter(DatasetBlockAdapter):
        extra_css = ("tracker/admin/incidents.css",)

    css = Adapter().media._css["all"]
    assert css == ["wagtail_vega/admin/dataset-block.css", "tracker/admin/incidents.css"]


def test_builder_loads_sources_js():
    from wagtail_vega.widgets import CodeEditor

    js = script_paths(CodeEditor(mode="spec", builder=True).media)
    assert js.index(next(p for p in js if p.endswith("sources.js"))) < js.index(
        next(p for p in js if p.endswith("chart-builder.js"))
    )


# -- SourceRowsView ----------------------------------------------------------------


@pytest.fixture
def rows_url():
    return reverse("testapp_donation_rows")


def test_rows_view_returns_encoded_rows(admin_client, rows_url, donations):
    response = admin_client.get(rows_url, {"year": "2026", "group_by": ["quarter", "month"]})
    assert response.status_code == 200
    rows = response.json()["rows"]
    # Dates as ISO 8601 strings, Decimals as numbers
    assert rows[0] == {"quarter": "Q1", "month": "2026-01-01", "total": 100.5}
    assert len(rows) == 4
    assert admin_client.get(rows_url, {"year": "2026"}).json() == {"rows": [{"total": 425.75}]}


def test_rows_view_errors(admin_client, rows_url, donations):
    response = admin_client.get(rows_url, {"year": "2025"})
    assert response.status_code == 400
    assert response.json() == {"error": "There are no donations in 2025."}
    response = admin_client.get(rows_url, {"year": "2026", "group_by": "colour"})
    assert response.status_code == 400 and response.json() == {"error": "Can't group by colour."}


def test_rows_view_is_admin_only(client, rows_url, django_user_model, donations):
    response = client.get(rows_url, {"year": "2026"})
    assert response.status_code == 302  # to the login page
    user = django_user_model.objects.create_user("reader", password="pw")
    client.force_login(user)
    response = client.get(rows_url, {"year": "2026"})
    assert response.status_code in (302, 403)
    assert b"rows" not in response.content


def test_rows_view_is_get_only(admin_client, rows_url):
    assert admin_client.post(rows_url, {"year": "2026"}).status_code == 405


def test_source_rows_view_directly(admin_user):
    class View(SourceRowsView):
        def get_rows(self, request):
            if request.GET.get("fail"):
                raise ValidationError(["Bad filter.", "Try again."])
            return iter([{"d": datetime.date(2026, 5, 1), "n": Decimal("1.5")}])

    request = RequestFactory().get("/rows/")
    request.user = admin_user
    response = View.as_view()(request)
    assert json.loads(response.content) == {"rows": [{"d": "2026-05-01", "n": 1.5}]}
    request = RequestFactory().get("/rows/", {"fail": "1"})
    request.user = admin_user
    response = View.as_view()(request)
    assert response.status_code == 400
    assert json.loads(response.content) == {"error": "Bad filter. Try again."}

    request = RequestFactory().get("/rows/")
    request.user = admin_user
    with pytest.raises(NotImplementedError):
        SourceRowsView.as_view()(request)


# -- On the site -------------------------------------------------------------------


def custom_chart_value(block, **dataset):
    return block.to_python(
        {
            "spec": {
                "$schema": VL,
                "data": {"name": "donations"},
                "mark": "bar",
                "encoding": {
                    "x": {"field": "quarter", "type": "nominal"},
                    "y": {"field": "total", "type": "quantitative"},
                },
            },
            "data": [{"name": "donations", **dataset}],
            "description": "",
            "caption": "",
            "theme": "",
        }
    )


def test_custom_source_rows_reach_the_chart(donations, vega_settings):
    block = DonationsSourceChartBlock()
    value = custom_chart_value(
        block, source_type="donations", year="2026", group_by=["quarter"], paste="x\n1"
    )
    value = block.clean(value)  # as when saved
    html = block.render(value)
    match = html.split('type="application/json">', 1)[1].split("</script>", 1)[0]
    payload = json.loads(match)
    assert payload["spec"]["datasets"]["donations"] == [
        {"quarter": "Q1", "total": 120.75},
        {"quarter": "Q2", "total": 300.0},
        {"quarter": "Q4", "total": 5.0},
    ]
    assert "Q4" in html  # the fallback table


def test_custom_source_in_the_api(client, donations):
    from wagtail.models import Site

    home = Site.objects.get(is_default_site=True).root_page
    page = home.add_child(
        instance=ChartPage(
            title="Custom source",
            slug="custom-source",
            body=[
                (
                    "donations_source_chart",
                    {
                        "spec": {
                            "$schema": VL,
                            "data": {"name": "donations"},
                            "mark": "bar",
                            "encoding": {"y": {"field": "total", "type": "quantitative"}},
                        },
                        "data": [{"name": "donations", "source_type": "donations", "year": "2026"}],
                        "description": "",
                        "caption": "",
                        "theme": "",
                    },
                )
            ],
        )
    )
    response = client.get(f"/api/v2/pages/{page.pk}/")
    chart = response.json()["body"][0]["value"]
    assert chart["spec"]["datasets"]["donations"] == [{"total": 425.75}]


def test_default_source_is_paste():
    block = DatasetBlock()
    assert block.get_source({"source_type": ""}) == PASTE
    assert block.get_source({"source_type": "url"}) == "url"
