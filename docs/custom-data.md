# Custom data sources

`ChartBlock` takes its data from the editor. To supply data from your own code, subclass {py:class}`~wagtail_vega.blocks.BaseChartBlock` and override {py:meth}`~wagtail_vega.blocks.BaseChartBlock.get_datasets`. To let editors choose your data for a dataset, add a [source type](#custom-source-types-for-editors).

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
URLs you return from `get_datasets()` aren't checked when the page is saved, but the browser refuses to load them unless they're on your own site or a host in `ALLOWED_DATA_HOSTS`, and a warning is logged on the `wagtail_vega.blocks` logger when the chart is rendered. Server-side rendering only fetches from allowed hosts too. Add the host to `ALLOWED_DATA_HOSTS`, and to your Content Security Policy's `connect-src` if you have one. See {doc}`security`.
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

## Adding datasets to an editor's chart

To give editors' charts extra data from code, say a lookup table, subclass `ChartBlock`, add it in `get_datasets()`, and list its name in `extra_dataset_names`. `ChartBlock` checks that a spec only loads datasets the chart has, both on save and as editors type, and this tells the check about yours:

```python
from wagtail_vega.blocks import ChartBlock


class RegionalChartBlock(ChartBlock):
    extra_dataset_names = ("regions",)

    def get_datasets(self, value, context=None):
        datasets = super().get_datasets(value, context)
        datasets["regions"] = list(Region.objects.values("code", "name", "population"))
        return datasets
```

Editors can then use `{"lookup": "region", "from": {"data": {"name": "regions"}, "key": "code", "fields": ["name"]}}` in their specs.

(custom-source-types)=

## Custom source types for editors

The options above supply data from code, with names you choose. To let **editors** pick your data for a dataset, with a name they choose, add a **source type** next to Paste / Document / URL. Editors then choose, say, **Tracker incidents** on the dataset's **Source** toggle, fill in that source's fields (a filter, how to count), and the rows are queried on the server when the page is rendered. The source works with the chart editor's preview and the check for datasets the spec loads but the chart doesn't have.

A source type takes:

1. A {py:class}`~wagtail_vega.blocks.DatasetBlock` subclass, with the source in its `source_type` choices and its fields in `source_fields`, and its rows from `get_source_dataset()`.
2. Optionally, an admin view that returns its rows for the admin, named in `source_rows_urls`. With it, editors see a summary of the rows under the source's fields ("✓ 12 rows · month (date), incidents (number)"), and the chart editor previews and builds charts from them, in Voyager and in the Simple settings. Without it, the chart editor lists the dataset but says it can't be previewed.
3. A `ChartBlock` subclass that uses your dataset block.

No JavaScript is needed.

### The dataset block

This example adds a "Tracker incidents" source: editors paste the URL of a filtered list of incidents, and choose how to count them.

```python
from django import forms
from django.core.exceptions import ValidationError
from wagtail import blocks
from wagtail_vega.blocks import PASTE, SOURCE_CHOICES, ChartBlock, DatasetBlock

from .incidents import count_incidents, parse_filter

GROUP_BY = [("month", "Month"), ("category", "Category"), ("state", "State")]


class IncidentDatasetBlock(DatasetBlock):
    # Which fields belong to which source: the form shows only the selected
    # source's fields, and saving resets the other sources' fields
    source_fields = {
        **DatasetBlock.source_fields,
        "incidents": ("incident_filter", "group_by"),
    }
    # The admin view that returns the source's rows (see below)
    source_rows_urls = {"incidents": "tracker_incident_rows"}
    # The new fields go right after the toggle, not after "format"
    field_order = ("name", "source_type", "incident_filter", "group_by")

    source_type = blocks.ChoiceBlock(
        choices=[("incidents", "Tracker incidents"), *SOURCE_CHOICES],
        default="incidents",
        widget=forms.RadioSelect,
        label="Source",
    )
    incident_filter = blocks.CharBlock(
        required=False, help_text="The URL of a filtered list of incidents."
    )
    group_by = blocks.MultipleChoiceBlock(
        choices=GROUP_BY, required=False, widget=forms.CheckboxSelectMultiple
    )

    def clean_source(self, source, value):
        if source == "incidents":
            try:
                parse_filter(value["incident_filter"])
            except ValueError as e:
                return {"incident_filter": ValidationError(str(e))}
            return {}
        return super().clean_source(source, value)

    def get_source_dataset(self, source, value):
        if source == "incidents":
            return count_incidents(parse_filter(value["incident_filter"]), value["group_by"])
        return super().get_source_dataset(source, value)


class IncidentChartBlock(ChartBlock):
    data = blocks.ListBlock(IncidentDatasetBlock(), min_num=0)
```

Use `IncidentChartBlock` in your StreamFields instead of `ChartBlock`. Specs load the dataset by the name the editor gave it, as for any other dataset.

`source_fields`
: `{source: (field name, …)}` for every source, the built-in ones included (`DatasetBlock.source_fields`). A source with no fields has `()`. A field can belong to more than one source; it's kept when any of them is selected.

`source_type`
: Redeclare it with your source in its choices. `SOURCE_CHOICES` has the built-in ones; leave out any you don't want editors to use, and remove them from `source_fields` too.

`clean_source(source, value)`
: Called when the dataset is saved, after each field's own validation, with the selected source. Return `{field name: ValidationError}`; an empty dict means all is well. The default checks the built-in sources and accepts any other, so a source without its own checks needs no code here.

`get_source_dataset(source, value)`
: The data for the selected source, in [the dataset format](#the-dataset-format): a list of rows, or a remote dataset. Call `super()` for the built-in sources. A source that nothing handles has no rows, and logs a warning. It runs whenever the chart is rendered, so cache slow queries.

`field_order`
: As for [chart blocks](adding-charts.md#field-order).

wagtail-vega checks the block when Django runs its system checks: every `source_type` choice needs a `source_fields` entry and the other way around (`wagtail_vega.E004`), every field in `source_fields` must be a field of the block (`wagtail_vega.E005`), and `source_rows_urls` may only name sources in `source_fields` (`wagtail_vega.E006`).

### The rows URL

Subclass {py:class}`~wagtail_vega.views.SourceRowsView` and implement `get_rows()`. The admin sends a GET request with the source's fields as query parameters, named after the fields, and repeated for fields with several values, such as `?incident_filter=…&group_by=month&group_by=state`. Return the rows; raise `ValidationError` to show the editor a message instead.

```python
from django.core.exceptions import ValidationError
from wagtail_vega.views import SourceRowsView

from .incidents import count_incidents, parse_filter


class IncidentRowsView(SourceRowsView):
    def get_rows(self, request):
        try:
            incident_filter = parse_filter(request.GET.get("incident_filter", ""))
        except ValueError as e:
            raise ValidationError(str(e)) from e
        return count_incidents(incident_filter, request.GET.getlist("group_by"))
```

Register it in your app's `wagtail_hooks.py`, with the URL name you put in `source_rows_urls`:

```python
from django.urls import path
from wagtail import hooks

from .views import IncidentRowsView


@hooks.register("register_admin_urls")
def register_admin_urls():
    return [
        path("incident-rows/", IncidentRowsView.as_view(), name="tracker_incident_rows"),
    ]
```

The view only answers users who can use the Wagtail admin. It responds like wagtail-vega's own document endpoint: `{"rows": [...]}`, encoded as charts encode their data (`Decimal`s become numbers, dates ISO 8601 strings), or `{"error": "…"}` with status 400. A `source_rows_urls` value is a URL name, resolved with `reverse()` when the form is built, or a path starting with `/`; it must be on your site.

The dataset's summary is fetched again, 300 ms after its fields stop changing. The chart editor fetches the rows when it opens and when it redraws a field's preview, and keeps them while the fields don't change.

The test project's `tests/testapp` has a working example: `DonationsDatasetBlock` in `models.py`, `DonationRowsView` in `views.py`, and the URL in `wagtail_hooks.py`.

### Rows from a script instead

If the browser can make a source's rows itself, register the source in a script rather than writing a view:

```js
window.wagtailVegaAdmin.registerSource("incidents", {
  // Optional: whether the dataset has any data yet (default: true)
  hasData(datasetEl) {
    const { incident_filter } = window.wagtailVegaAdmin.sources.readFields(datasetEl, ["incident_filter"]);
    return Boolean(incident_filter[0]);
  },
  // The rows, or a promise of them. Throw an Error to show its message.
  async loadRows(datasetEl, config) {
    const { incident_filter } = window.wagtailVegaAdmin.sources.readFields(datasetEl, ["incident_filter"]);
    const response = await fetch(`/api/incidents/counts/?${new URL(incident_filter).search.slice(1)}`);
    if (!response.ok) throw new Error(`Couldn't count the incidents (${response.status}).`);
    return (await response.json()).results;
  },
});
```

`datasetEl` is the dataset block's element. `wagtailVegaAdmin.sources.readFields(datasetEl, names)` returns `{name: [value, …]}` for its fields, the way the rows URL request reads them. The chart editor keeps the rows while the source's fields (from `source_fields`) don't change; if `loadRows()` depends on anything else, also give the source a `key(datasetEl)` function that returns a string that changes with it.

A source's rows URL, if it has one, is used rather than a registered script. To show a summary for a registered source, use `wagtailVegaAdmin.dataFormat.summariseRows(rows)` and `wagtailVegaAdmin.dataFormat.renderSummary(element, summary)`, which show it with the same markup and styles as the pasted data's summary. `renderSummary(element, {ok: false, message})` shows an error.

### Loading your own scripts

To load a script for your dataset block, register a subclass of `DatasetBlockAdapter` for it and list the script in `extra_js` (and any stylesheets in `extra_css`). They're loaded after wagtail-vega's admin scripts, so `window.wagtailVegaAdmin` is ready:

```python
from wagtail.admin.telepath import register
from wagtail_vega.blocks import DatasetBlockAdapter


class IncidentDatasetBlockAdapter(DatasetBlockAdapter):
    extra_js = ("tracker/admin/incident-source.js",)


register(IncidentDatasetBlockAdapter(), IncidentDatasetBlock)
```

:::{warning}
Don't add your script with `super().media + forms.Media(js=[...])`. Django's `Media` merge only keeps the relative order of scripts that are in both lists, so your script may load before wagtail-vega's and find nothing to use. `extra_js` builds one ordered list.
:::

The form's behaviour is the `window.wagtailVegaAdmin.DatasetBlockDefinition` telepath class. To change it, extend it, register it under a constructor name of your own, and set the adapter's `js_constructor` to that name:

```js
class IncidentDatasetBlockDefinition extends window.wagtailVegaAdmin.DatasetBlockDefinition {
  render(placeholder, prefix, initialState, initialError) {
    const block = super.render(placeholder, prefix, initialState, initialError);
    // …
    return block;
  }
}
window.telepath.register("tracker.IncidentDatasetBlock", IncidentDatasetBlockDefinition);
```

```python
class IncidentDatasetBlockAdapter(DatasetBlockAdapter):
    js_constructor = "tracker.IncidentDatasetBlock"
    extra_js = ("tracker/admin/incident-dataset-block.js",)
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
| `get_embed_options(value, context=None, theme=None)` | vega-embed options | The defaults, then the `EMBED_OPTIONS` setting, then `Meta.embed_options`, each merged over the last, plus the theme's built-in vega-embed theme. |
| `use_ssr(value)` | `bool` | `Meta.ssr`, else the `SSR` setting. |
| `use_fallback_table(value)` | `bool` | `Meta.fallback_table`, else the `FALLBACK_TABLE` setting. |
| `build_chart(value, context=None)` | A {py:class}`~wagtail_vega.blocks.Chart` | Calls the hooks above. |

`get_spec()` is called twice when the theme has dark-mode overrides: once for the light spec and once, with `dark=True`, for the dark config. `get_datasets()` is only called once.

The default `get_spec()` deep-copies the spec before changing it, so `get_spec_source()` can return a shared dict, like `DONATIONS_SPEC` above.

`get_embed_options()` always sets `defaultStyle: False`, and `disableDefaultStyle: True` in the tooltip options, so that vega-embed doesn't inject styles. See {doc}`security`.

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
