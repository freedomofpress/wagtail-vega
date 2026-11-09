# Server-side rendering

With server-side rendering (SSR), each chart is also rendered to SVG on the server, with [vl-convert](https://github.com/vega/vl-convert), and included in the page. Readers see the chart before JavaScript loads, or without JavaScript at all. When the JavaScript has loaded, it replaces the SVG with the interactive chart.

## Setup

Install the `ssr` extra:

```console
$ pip install "wagtail-vega[ssr]"
```

Then turn it on for every chart:

```python
WAGTAIL_VEGA = {"SSR": True}
```

Or for one kind of block, with its `ssr` option:

```python
("chart", ChartBlock(ssr=True))
```

`ssr=False` turns it off for a block when the setting is on.

If SSR is on but vl-convert isn't installed, a warning is logged and charts are rendered in the browser only.

## How it works

When a chart is rendered:

1. The final spec, with data and the light theme config, is built as usual.
2. `var(--name)` strings are replaced with the theme's `fallbacks` value or the `var()` default, because there's no page CSS on the server (see [](theming.md#css-custom-properties)).
3. vl-convert renders it to SVG. The SVG is put in a `<div class="wagtail-vega__ssr">` inside the `<wagtail-vega-chart>` element, instead of the `<noscript>` message.

The SVG is cached in Django's default cache for `SSR_CACHE_TIMEOUT` seconds (one day by default). The cache key is a hash of the spec, including its inline data, so the SVG is rendered again whenever the spec or data change. Use a cache that's shared between processes, such as Redis or Memcached, so each chart is only rendered once.

If rendering fails, the error is logged to the `wagtail_vega.ssr` logger, and the chart is rendered in the browser only.

## Loading data

During SSR, vl-convert may only fetch from the literal, absolute URLs in the spec that are on allowed hosts (see {doc}`security`). URL data is fetched by the server while the page is being rendered, and the result is cached with the SVG, so it may be up to `SSR_CACHE_TIMEOUT` old. The browser fetches fresh data when it renders the interactive chart.

Specs that use relative URLs, such as `/media/data.csv`, aren't server-rendered. vl-convert has no base URL to resolve them against, and fetching your own site in the middle of a request could deadlock a single-threaded server. These charts get the `<noscript>` message instead.

## Limitations

- Only the light config is used, since the server doesn't know the reader's colour scheme.
- Charts with `"width": "container"` are rendered at a default width until JavaScript takes over.
- The SVG isn't interactive: no tooltips, selections or bound inputs until JavaScript runs.
- Rendering a chart for the first time adds to the response time. Later requests use the cache.
- Text is measured with the fonts available to vl-convert on the server, so labels can be placed slightly differently from the browser.

Built-in (`vega:`) themes are applied on the server too, for Vega and Vega-Lite specs alike: their config comes from vl-convert, which uses the same [vega-themes](https://github.com/vega/vega-themes) as vega-embed. vl-convert may bundle slightly different Vega and Vega-Lite versions from the ones the browser gets, so small rendering differences are possible. wagtail-vega supports vl-convert 1.x.
