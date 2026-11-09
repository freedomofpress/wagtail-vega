"""Demo charts shared by the sandbox seed command and the browser tests."""

import datetime
import json
from decimal import Decimal

from wagtail.models import Locale, Page, Site

from tests.testapp.models import ChartPage, Donation

VL = "https://vega.github.io/schema/vega-lite/v6.json"
VG = "https://vega.github.io/schema/vega/v6.json"

BAR = {
    "$schema": VL,
    "title": "Requests by quarter",
    "width": "container",
    "data": {"name": "source"},
    "mark": {"type": "bar", "tooltip": True},
    "encoding": {
        "x": {"field": "quarter", "type": "nominal", "title": None},
        "y": {"field": "requests", "type": "quantitative"},
        "color": {"field": "agency", "type": "nominal"},
        "xOffset": {"field": "agency"},
    },
}
# Tab-separated, as copied from a spreadsheet
CSV = """quarter\tagency\trequests
Q1\tFBI\t1,120
Q1\tDHS\t980
Q2\tFBI\t1,340
Q2\tDHS\t1,095
Q3\tFBI\t1,110
Q3\tDHS\t1,230
"""

VEGA_SPEC = {
    "$schema": VG,
    "width": 400,
    "height": 200,
    "padding": 5,
    "signals": [
        {
            "name": "threshold",
            "value": 30,
            "bind": {"input": "range", "min": 0, "max": 90, "step": 1},
        }
    ],
    "data": [
        {"name": "source"},
        {
            "name": "visible",
            "source": "source",
            "transform": [{"type": "filter", "expr": "datum.amount >= threshold"}],
        },
    ],
    "scales": [
        {
            "name": "x",
            "type": "band",
            "domain": {"data": "source", "field": "category"},
            "range": "width",
            "padding": 0.1,
        },
        {
            "name": "y",
            "domain": {"data": "source", "field": "amount"},
            "nice": True,
            "range": "height",
        },
    ],
    "axes": [{"orient": "bottom", "scale": "x"}, {"orient": "left", "scale": "y"}],
    "marks": [
        {
            "type": "rect",
            "from": {"data": "visible"},
            "encode": {
                "update": {
                    "x": {"scale": "x", "field": "category"},
                    "width": {"scale": "x", "band": 1},
                    "y": {"scale": "y", "field": "amount"},
                    "y2": {"scale": "y", "value": 0},
                    "fill": {"value": "steelblue"},
                }
            },
        }
    ],
}

DONATIONS = {
    "$schema": VL,
    "title": "Donations (from the database)",
    "width": "container",
    "data": {"name": "donations"},
    "mark": {"type": "line", "point": True},
    "encoding": {
        "x": {"field": "month", "type": "temporal", "timeUnit": "utcyearmonth"},
        "y": {"field": "total", "type": "quantitative"},
    },
}

REMOTE = {
    "$schema": VL,
    "title": "Weather (CSV from a URL)",
    "width": "container",
    "data": {"name": "weather"},
    "mark": "bar",
    "encoding": {
        "x": {"field": "date", "timeUnit": "month", "type": "ordinal"},
        "y": {"aggregate": "count", "type": "quantitative"},
        "color": {"field": "weather", "type": "nominal"},
    },
}

SEATTLE_WEATHER = "https://vega.github.io/vega-datasets/data/seattle-weather.csv"


def demo_body(weather_url=SEATTLE_WEATHER):
    """StreamField content with four charts: pasted TSV (Vega-Lite), pasted
    JSON (raw Vega with an expression), a database-backed subclass, and a
    URL dataset."""
    amounts = [
        {"category": c, "amount": a}
        for c, a in zip("ABCDEFGH", [28, 55, 43, 91, 81, 53, 19, 87], strict=True)
    ]
    return [
        (
            "chart",
            {
                "spec": BAR,
                "theme": "",
                "data": [{"name": "source", "source_type": "paste", "paste": CSV}],
                "description": "Grouped bar chart of records requests per quarter.",
                "caption": "Source: example data",
            },
        ),
        (
            "chart",
            {
                "spec": VEGA_SPEC,
                "theme": "538",
                "data": [
                    {
                        "name": "source",
                        "source_type": "paste",
                        "paste": json.dumps(amounts, indent=2),
                    }
                ],
                "description": "A Vega bar chart with a threshold slider.",
                "caption": "A raw Vega spec using the vega:fivethirtyeight theme",
            },
        ),
        (
            "donations_chart",
            {
                "spec": DONATIONS,
                "description": "Monthly donations in 2026.",
                "caption": "Data from the Donation model",
            },
        ),
        (
            "chart",
            {
                "spec": REMOTE,
                "theme": "",
                "data": [
                    {
                        "name": "weather",
                        "source_type": "url",
                        "url": weather_url,
                        "format": "csv",
                    }
                ],
                "description": "Weather by month.",
                "caption": "Data loaded from a URL",
            },
        ),
    ]


def create_donations():
    for i, total in enumerate([120, 180, 90, 240, 310, 280]):
        Donation.objects.get_or_create(
            month=datetime.date(2026, i + 1, 1),
            defaults={"total": Decimal(total) + Decimal("0.50")},
        )


def ensure_site():
    """Recreate the locale, root page and default site that Wagtail's
    migrations create, for tests that flush the database between runs."""
    Locale.objects.get_or_create(language_code="en")
    root = Page.objects.filter(depth=1).first()
    if root is None:
        root = Page.add_root(instance=Page(title="Root", slug="root"))
    site = Site.objects.filter(is_default_site=True).first()
    if site is None:
        site = Site.objects.create(hostname="localhost", root_page=root, is_default_site=True)
    return site


def create_demo_page(weather_url=SEATTLE_WEATHER, make_site_root=True):
    create_donations()
    site = ensure_site()
    parent = Page.objects.get(depth=1) if make_site_root else site.root_page
    page = ChartPage(title="Chart examples", slug="charts", body=demo_body(weather_url))
    parent.add_child(instance=page)
    page.save_revision().publish()
    if make_site_root:
        site.root_page = page
        site.save()
    return page
