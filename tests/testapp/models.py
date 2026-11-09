from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page

from wagtail_vega.blocks import BaseChartBlock, ChartBlock


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


class ChartPage(Page):
    body = StreamField(
        [("chart", ChartBlock()), ("donations_chart", DonationsChartBlock())],
        blank=True,
    )

    content_panels = [*Page.content_panels, FieldPanel("body")]
