# How it works

## Specs and named datasets

A chart has two parts:

- a **spec**: a Vega or Vega-Lite JSON specification, which says how to draw the chart;
- zero or more **datasets**, each with a name, which provide the data.

They are kept apart so the same spec can be used with different data, and so the data can come from places other than the spec: pasted by an editor, from a Wagtail document, from a URL, or from your own Python code.

The spec refers to each dataset **by name**:

```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
  "data": {"name": "source"},
  "mark": "bar",
  "encoding": {
    "x": {"field": "quarter", "type": "nominal"},
    "y": {"field": "requests", "type": "quantitative"}
  }
}
```

When the chart is rendered, wagtail-vega fills in each dataset where the spec refers to its name:

Vega-Lite
: Inline rows go into the spec's top-level [`datasets`](https://vega.github.io/vega-lite/docs/data.html#datasets). Remote datasets (`{"url": ..., "format": ...}`) replace every `{"name": ...}` data reference with that name.

Vega
: The entry with the same name in the spec's `data` array gets the rows as `values`, or the `url` and `format` of a remote dataset. Its `transform`s are kept, and any `values`, `url` or `source` already on that entry are removed. A dataset that the spec doesn't mention is added to the end of `data`, so signals and expressions can still use it.

A spec can still contain its own inline `values`, which is handy for one-off charts.

Every spec needs a `$schema`. It decides whether the spec is treated as Vega or Vega-Lite: wagtail-vega looks for `/vega-lite/` or `/vega/` in its URL path.

## The rendering pipeline

Rendering is split between the server and the browser.

**On the server**, when a page is rendered, {py:meth}`BaseChartBlock.build_chart() <wagtail_vega.blocks.BaseChartBlock.build_chart>` does this:

1. `get_theme()` picks a {doc}`theme <theming>`.
2. `get_datasets()` returns the named datasets. In `ChartBlock`, these are the editor's datasets. In your own subclass they can come from anywhere (see {doc}`custom-data`).
3. `get_spec()` takes the spec from `get_spec_source()`, injects the datasets and merges the theme's `config` under the spec's own `config`. If the theme has dark-mode overrides, a second, dark `config` is also built.
4. `get_embed_options()` builds the [vega-embed](https://github.com/vega/vega-embed) options.
5. If {doc}`server-side rendering <ssr>` is on, the spec is rendered to SVG with vl-convert.
6. If the fallback table is on, a table of each inline dataset is built.

The result is a {py:class}`~wagtail_vega.blocks.Chart` object, which the block's template, `wagtail_vega/chart.html`, renders as:

- a `<figure>` containing a `<wagtail-vega-chart>` custom element;
- the chart's payload (the spec, dark config, embed options and security settings), as a `<script type="application/json">` tag that isn't executed;
- the description, data table and caption.

The template also loads the CSS and JavaScript, once per page, the first time a chart appears on it.

**In the browser**, `wagtail-vega.js` defines the `<wagtail-vega-chart>` element. For each chart, it:

1. reads the payload;
2. picks the light or dark config, using the page's colour scheme;
3. resolves `var(--token)` strings in the config from the page's CSS custom properties;
4. renders the chart with vega-embed, using a data loader that refuses hosts that aren't allowlisted;
5. replaces the server-rendered SVG (or the `<noscript>` message), and fires a `wagtail-vega:rendered` event.

See {doc}`frontend` for the details.

## What's in the box

`wagtail_vega.blocks.ChartBlock`
: The block editors use. It has a spec, a list of datasets, a description, a caption and a theme picker.

`wagtail_vega.blocks.BaseChartBlock`
: The base class for your own chart blocks. It has a spec, a description and a caption, and hooks you can override.

`WAGTAIL_VEGA` setting
: Themes, the data host allowlist, CSP-safe mode, server-side rendering and more. See {doc}`settings`.

`{% wagtail_vega_assets %}`
: The template tag that outputs the CSS and scripts. Chart blocks call it themselves.

Vendored libraries
: Vega 6, Vega-Lite 6, vega-embed 7 and vega-interpreter, served from your static files. The exact versions are in `wagtail_vega/static/wagtail_vega/vendor/VERSIONS.json`.
