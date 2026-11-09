# Installation and quickstart

## Supported versions

| Package | Versions |
| --- | --- |
| Wagtail | 7.4 LTS and newer |
| Django | 5.2 and newer, as supported by your Wagtail version |
| Python | 3.10 and newer, as supported by your Wagtail and Django versions |

CI runs the full test suite, including browser tests, on Wagtail 7.4 (with Django 5.2 and 6.0), 8.0 and 8.1. It also runs Wagtail's nightly build, as a non-blocking job.

## Install

```console
$ pip install wagtail-vega
```

For {doc}`server-side rendering <ssr>`, install the `ssr` extra, which adds [vl-convert](https://github.com/vega/vl-convert):

```console
$ pip install "wagtail-vega[ssr]"
```

Add `wagtail_vega` to `INSTALLED_APPS`. The data source picker uses Wagtail documents, so `wagtail.documents` must be installed too. It is installed by default in new Wagtail projects.

```python
INSTALLED_APPS = [
    # ...
    "wagtail_vega",
    "wagtail.documents",
    # ...
]
```

wagtail-vega has no models of its own, so there are no migrations to run for it. It ships static files (the vendored Vega libraries, its script and stylesheet), so run `collectstatic` when you deploy, as usual.

No settings are needed to get started. When you need them, see {doc}`settings`.

## Quickstart

### 1. Add a chart block to a StreamField

```python
from wagtail.admin.panels import FieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail_vega.blocks import ChartBlock


class ArticlePage(Page):
    body = StreamField([("chart", ChartBlock())], blank=True)

    content_panels = [*Page.content_panels, FieldPanel("body")]
```

Then make and run migrations for your app:

```console
$ python manage.py makemigrations
$ python manage.py migrate
```

### 2. Render the StreamField

Render the StreamField with `{% include_block %}`, as you would any other:

```html+django
{% load wagtailcore_tags %}

{% for block in page.body %}
    {% include_block block %}
{% endfor %}
```

The chart template loads the CSS and JavaScript the first time a chart appears on a page, so pages without charts don't download Vega. To load them only once per page, it uses the `request` in the template context. Wagtail pages have `request` in their context, and `{% include_block %}` passes the context on. Writing `{{ page.body }}` also works, but doesn't pass the context, so each chart includes a small loader script instead, and the libraries only start downloading once the page has been parsed. See {doc}`frontend` for other ways to load the assets.

### 3. Make a chart

In the Wagtail admin, edit a page and add a **Chart** block.

1. Under **Data**, add a dataset. Leave its name as `source`, and paste:

   ```text
   quarter,requests
   Q1,1120
   Q2,1340
   Q3,1110
   Q4,1460
   ```

2. Paste this into **Spec**:

   ```json
   {
     "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
     "width": "container",
     "data": {"name": "source"},
     "mark": "bar",
     "encoding": {
       "x": {"field": "quarter", "type": "nominal"},
       "y": {"field": "requests", "type": "quantitative"}
     }
   }
   ```

3. Fill in **Description**, which is read to people using screen readers. Say what the chart shows, not just what kind of chart it is, e.g. "Records requests rose every quarter, from 1,120 to 1,460".

4. Preview or publish the page.

The [Vega-Lite examples gallery](https://vega.github.io/vega-lite/examples/) is a good place to find specs to adapt. Replace the example's `data` with `{"name": "source"}`.

## Next steps

- {doc}`adding-charts`: more ways to configure the block.
- {doc}`custom-data`: supply data from your own code.
- {doc}`theming`: make charts match your site.
- {doc}`security`: allow data from other hosts, and run under a strict Content Security Policy.
