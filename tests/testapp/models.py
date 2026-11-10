from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from wagtail import blocks
from wagtail.admin.panels import FieldPanel
from wagtail.admin.telepath import register
from wagtail.api import APIField
from wagtail.fields import StreamField
from wagtail.models import Page

from wagtail_vega.blocks import (
    PASTE,
    SOURCE_CHOICES,
    BaseChartBlock,
    ChartBlock,
    DatasetBlock,
    DatasetBlockAdapter,
)


class Donation(models.Model):
    month = models.DateField()
    total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["month"]

    def __str__(self):
        return f"{self.month}: {self.total}"


class DonationsChartBlock(BaseChartBlock):
    """Example of a developer-defined data source: rows come from the DB."""

    def get_datasets(self, value, context=None):
        return {"donations": list(Donation.objects.values("month", "total"))}

    class Meta:
        label = "Donations chart"


# -- Custom source types for editors (see docs/custom-data.md) ---------------------

DONATION_YEARS = [("2025", "2025"), ("2026", "2026")]
DONATION_GROUPS = {
    "quarter": lambda month: f"Q{(month.month - 1) // 3 + 1}",
    "month": lambda month: month,
}


def donation_rows(year, group_by=()):
    """Donation totals for ``year``, grouped by "quarter" and/or "month" (a
    single total if neither), with Decimal totals and date months."""
    groups = [name for name in DONATION_GROUPS if name in (group_by or ())]
    totals = {}
    for donation in Donation.objects.filter(month__year=year):
        key = tuple(DONATION_GROUPS[name](donation.month) for name in groups)
        totals[key] = totals.get(key, Decimal(0)) + donation.total
    return [
        {**dict(zip(groups, key, strict=True)), "total": total} for key, total in totals.items()
    ]


def sample_rows(points):
    """Rows for the "sample" source, which tests/testapp/static/testapp/
    sample-source.js also makes in the browser."""
    return [{"x": i, "y": i * i} for i in range(1, points + 1)]


class DonationsDatasetBlock(DatasetBlock):
    """A dataset that can also come from the Donation model, chosen by the
    editor: the "donations" source, with a rows URL for the admin
    (DonationRowsView). Two more sources show the other ways the admin gets a
    source's rows: "sample" from a script that registers it
    (sample-source.js), and "totals" not at all (only on the site)."""

    source_fields = {
        **DatasetBlock.source_fields,
        "donations": ("year", "group_by"),
        "sample": ("points",),
        "totals": (),
    }
    source_rows_urls = {"donations": "testapp_donation_rows"}
    field_order = ("name", "source_type", "year", "group_by", "points")

    source_type = blocks.ChoiceBlock(
        choices=[
            *SOURCE_CHOICES,
            ("donations", "Donations"),
            ("sample", "Sample"),
            ("totals", "Yearly totals"),
        ],
        default=PASTE,
        widget=forms.RadioSelect,
        label="Source",
    )
    year = blocks.ChoiceBlock(choices=DONATION_YEARS, default="2026", required=False)
    group_by = blocks.MultipleChoiceBlock(
        choices=[("quarter", "Quarter"), ("month", "Month")],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leave both unticked for the year's total.",
    )
    points = blocks.IntegerBlock(required=False, default=5, min_value=1, max_value=50)

    def clean_source(self, source, value):
        if source == "donations" and not value["year"]:
            return {"year": ValidationError("Choose a year.")}
        if source == "sample" and not value["points"]:
            return {"points": ValidationError("Enter a number of points.")}
        return super().clean_source(source, value)

    def get_source_dataset(self, source, value):
        if source == "donations":
            return donation_rows(int(value["year"]), value["group_by"])
        if source == "sample":
            return sample_rows(value["points"])
        if source == "totals":
            years = Donation.objects.dates("month", "year")
            return [{"year": d.year, "total": donation_rows(d.year)[0]["total"]} for d in years]
        return super().get_source_dataset(source, value)


class DonationsDatasetBlockAdapter(DatasetBlockAdapter):
    extra_js = ("testapp/sample-source.js",)


register(DonationsDatasetBlockAdapter(), DonationsDatasetBlock)


class DonationsSourceChartBlock(ChartBlock):
    """A ChartBlock whose datasets can come from the Donation model."""

    data = blocks.ListBlock(
        DonationsDatasetBlock(),
        min_num=0,
        help_text="The data for this chart. Use each dataset's name in the spec.",
    )

    class Meta:
        label = "Chart with donations data"


class ChartPage(Page):
    body = StreamField(
        [
            ("chart", ChartBlock()),
            ("donations_chart", DonationsChartBlock()),
            ("donations_source_chart", DonationsSourceChartBlock()),
        ],
        blank=True,
    )

    content_panels = [*Page.content_panels, FieldPanel("body")]
    api_fields = [APIField("body")]
