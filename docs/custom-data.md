# Custom data sources

`ChartBlock` takes its data from the editor. To supply data from your own code, subclass {py:class}`~wagtail_vega.blocks.BaseChartBlock` and override {py:meth}`~wagtail_vega.blocks.BaseChartBlock.get_datasets`.

`BaseChartBlock` has a **Spec**, a **Description** and a **Caption**, but no data or theme fields. Editors write the spec, and refer to your datasets by name.

## From the database

```python
from wagtail_vega.blocks import BaseChartBlock

from .models import Donation


class DonationsChartBlock(BaseChartBlock):
    def get_datasets(self, value, context=None):
        return {"donations": list(Donation.objects.values("month", "total"))}

    class Meta:
        label = "Donations chart"
        help_text = 'Use {"data": {"name": "donations"}}. Columns: month, total.'
```

Add it to a StreamField like any other block:

```python
body = StreamField(
    [
        ("chart", ChartBlock()),
        ("donations_chart", DonationsChartBlock()),
    ]
)
```

An editor can then chart the donations with a spec such as:

```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
  "data": {"name": "donations"},
  "mark": {"type": "line", "point": true},
  "encoding": {
    "x": {"field": "month", "type": "temporal", "timeUnit": "utcyearmonth"},
    "y": {"field": "total", "type": "quantitative"}
  }
}
```

The test project's `tests/testapp/models.py` has this block, working.

The datasets are written into the page's HTML, as JSON. Only return data that every reader of the page may see.

## The dataset format

`get_datasets()` returns a dict mapping each dataset's name to either:

**Inline rows**
: A list of rows. Each row is usually a dict of column names to values. Wrap querysets in `list()`.

  The rows are serialised as JSON with Django's JSON encoder, extended so that `Decimal`s become numbers. Dates and datetimes become ISO 8601 strings, and UUIDs become strings. Anything else must be JSON-serialisable.

  If every row is a dict, the dataset is included in the fallback data table.

**A remote dataset**
: A dict with a `url` and, optionally, a `format`:

  ```python
  {"url": "https://data.example.org/rates.csv", "format": {"type": "csv"}}
  ```

  The browser fetches the URL; any dict with a `url` key is treated this way. The `format` is a [Vega-Lite format](https://vega.github.io/vega-lite/docs/data.html#format) or [Vega format](https://vega.github.io/vega/docs/data/#format) object. `wagtail_vega.spec.remote_data(url, fmt)` builds one:

  ```python
  from wagtail_vega.spec import remote_data

  remote_data("https://data.example.org/rates.csv", "csv")
  # {"url": "https://data.example.org/rates.csv", "format": {"type": "csv"}}

  remote_data("https://data.example.org/rates.csv")  # format from the extension
  # {"url": "https://data.example.org/rates.csv", "format": {"type": "csv"}}
  ```

  Remote datasets aren't in the fallback data table.

:::{important}
URLs you return from `get_datasets()` aren't checked when the page is saved, but the browser refuses to load them unless they're same-origin or on a host in `ALLOWED_DATA_HOSTS`. Server-side rendering only fetches from allowed hosts too. Add the host to `ALLOWED_DATA_HOSTS`, and to your Content Security Policy's `connect-src` if you have one. See {doc}`security`.
:::

For how each dataset ends up in the spec, see {doc}`overview`.

## From an API

Fetch the data on the server and cache it, so pages don't wait for the API on every request:

```python
import json
from urllib.request import urlopen

from django.core.cache import cache
from wagtail_vega.blocks import BaseChartBlock

RATES_URL = "https://api.example.org/rates.json"


class ExchangeRateChartBlock(BaseChartBlock):
    def get_datasets(self, value, context=None):
        rows = cache.get("exchange-rates")
        if rows is None:
            with urlopen(RATES_URL, timeout=5) as response:
                rows = json.load(response)["rates"]
            cache.set("exchange-rates", rows, 60 * 60)
        return {"rates": rows}
```

An exception raised here stops the page from rendering, so handle errors if the API might fail: for example, return `{"rates": []}` and log the error.

Or let the browser fetch it, if the API allows cross-origin requests:

```python
from wagtail_vega.blocks import BaseChartBlock
from wagtail_vega.spec import remote_data


class ExchangeRateChartBlock(BaseChartBlock):
    def get_datasets(self, value, context=None):
        return {"rates": remote_data("https://api.example.org/rates.csv", "csv")}
```

```python
WAGTAIL_VEGA = {"ALLOWED_DATA_HOSTS": ["api.example.org"]}
```

## Depending on the page or request

The `context` argument is the template context the block is rendered in. For a Wagtail page, it includes `page` and `request`. It's `None` when the block is rendered without a context, for example with `block.render(value)`, so check for that.

This block charts the donations for the campaign the page belongs to:

```python
from wagtail_vega.blocks import BaseChartBlock

from .models import Donation


class CampaignDonationsChartBlock(BaseChartBlock):
    def get_datasets(self, value, context=None):
        page = context.get("page") if context else None
        donations = Donation.objects.filter(campaign=getattr(page, "campaign", None))
        return {"donations": list(donations.values("month", "total"))}
```

And this one uses a query string parameter, such as `?region=west`:

```python
class RegionalChartBlock(BaseChartBlock):
    def get_datasets(self, value, context=None):
        request = context.get("request") if context else None
        region = request.GET.get("region", "all") if request else "all"
        rows = Sale.objects.all()
        if region != "all":
            rows = rows.filter(region=region)
        return {"sales": list(rows.values("month", "region", "amount"))}
```

:::{warning}
If you cache whole pages, for example with a CDN or Wagtail's frontend cache, a chart that depends on the request will be cached for everyone. Vary the cache, or load the data from the browser instead.
:::

## Adding fields for editors

Add child blocks to let editors configure the data, and read them from `value`:

```python
from wagtail import blocks
from wagtail_vega.blocks import BaseChartBlock


class DonationsChartBlock(BaseChartBlock):
    year = blocks.IntegerBlock(min_value=2000)

    field_order = ("year", "spec")

    def get_datasets(self, value, context=None):
        donations = Donation.objects.filter(month__year=value["year"])
        return {"donations": list(donations.values("month", "total"))}
```

To also let editors add their own datasets, subclass `ChartBlock` instead, and combine yours with theirs:

```python
from wagtail_vega.blocks import ChartBlock


class DonationsChartBlock(ChartBlock):
    def get_datasets(self, value, context=None):
        return {
            **super().get_datasets(value, context),
            "donations": list(Donation.objects.values("month", "total")),
        }
```

## A chart defined in code

To ship a fixed chart, override {py:meth}`~wagtail_vega.blocks.BaseChartBlock.get_spec_source` and remove the spec field with `spec = None`:

```python
from wagtail_vega.blocks import BaseChartBlock

DONATIONS_SPEC = {
    "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
    "width": "container",
    "data": {"name": "donations"},
    "mark": "bar",
    "encoding": {
        "x": {"field": "month", "type": "temporal", "timeUnit": "utcyearmonth"},
        "y": {"field": "total", "type": "quantitative"},
    },
}


class DonationsByMonthBlock(BaseChartBlock):
    spec = None  # editors don't see a spec field

    def get_spec_source(self, value):
        return DONATIONS_SPEC

    def get_datasets(self, value, context=None):
        return {"donations": list(Donation.objects.values("month", "total"))}
```

Editors then only fill in the description and caption. A spec returned from `get_spec_source()` isn't validated, so check it yourself, e.g. in a test that renders the block.

## Hooks

`BaseChartBlock` builds a chart by calling these methods. Override any of them. `build_chart()` calls them in this order:

| Method | Returns | Default |
| --- | --- | --- |
| `get_theme(value, context=None)` | A {py:class}`~wagtail_vega.themes.Theme`, or `None` | The block's `Meta.theme`, else the editor's choice, else `DEFAULT_THEME`. |
| `get_datasets(value, context=None)` | `{name: dataset}` | `{}`. `ChartBlock` returns the editor's datasets. |
| `get_spec(value, context=None, datasets=None, theme=None, dark=False)` | The final spec | Calls `get_spec_source()`, injects `datasets` and merges in the theme config. Builds the dark config when `dark` is true. |
| `get_spec_source(value)` | The spec as written | `value["spec"]`. Called by `get_spec()`. |
| `get_embed_options(value, context=None, theme=None)` | vega-embed options | The `EMBED_OPTIONS` setting, then `Meta.embed_options`, plus the theme's built-in vega-embed theme. |
| `use_ssr(value)` | `bool` | `Meta.ssr`, else the `SSR` setting. |
| `use_fallback_table(value)` | `bool` | `Meta.fallback_table`, else the `FALLBACK_TABLE` setting. |
| `build_chart(value, context=None)` | A {py:class}`~wagtail_vega.blocks.Chart` | Calls the hooks above. |

`get_spec()` is called twice when the theme has dark-mode overrides: once for the light spec and once, with `dark=True`, for the dark config. `get_datasets()` is only called once.

The default `get_spec()` deep-copies the spec before changing it, so `get_spec_source()` can return a shared dict, like `DONATIONS_SPEC` above.

`get_embed_options()` always sets `defaultStyle: False` and `tooltip: {"disableDefaultStyle": True}`, so that vega-embed doesn't inject styles. See {doc}`security`.

The template gets the `Chart` as `chart` in its context. To add to it, override `get_context()`:

```python
class DonationsChartBlock(BaseChartBlock):
    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context)
        context["source_url"] = "/donate/"
        return context
```

## Options

`BaseChartBlock` subclasses take the same [block options](adding-charts.md#block-options) and [field order](adding-charts.md#field-order) as `ChartBlock`:

```python
class DonationsChartBlock(BaseChartBlock):
    field_order = ("spec", "caption", "description")

    class Meta:
        label = "Donations chart"
        icon = "wagtail-vega-chart"
        template = "myapp/blocks/donations_chart.html"
        theme = "house"
        ssr = True
        fallback_table = True
        embed_options = {"padding": 16}
```

The default icon is `wagtail-vega-chart`, which wagtail-vega registers. The default template is `wagtail_vega/chart.html`; see {doc}`frontend` before replacing it.
