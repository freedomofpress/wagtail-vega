# Frontend integration

## Loading the assets

Charts need a stylesheet and some scripts:

- `wagtail_vega/wagtail-vega.css`;
- the vendored `vega.min.js`, `vega-lite.min.js` and `vega-embed.min.js`;
- `vega-interpreter.js`, in {ref}`CSP-safe mode <csp-safe>`;
- `wagtail_vega/wagtail-vega.js`.

The `{% wagtail_vega_assets %}` tag outputs them, as a `<link>` and `<script defer>` tags:

```html
<link rel="stylesheet" href="/static/wagtail_vega/wagtail-vega.css">
<script src="/static/wagtail_vega/vendor/vega.min.js" defer></script>
<script src="/static/wagtail_vega/vendor/vega-lite.min.js" defer></script>
<script src="/static/wagtail_vega/vendor/vega-embed.min.js" defer></script>
<script src="/static/wagtail_vega/wagtail-vega.js" defer></script>
```

The chart template calls the tag before each chart. The tag remembers, on the `request` in the template context, that it has run, and outputs nothing after the first time. So by default:

- pages without charts don't load Vega;
- pages with charts load it once, just before the first chart.

If there's no `request` in the context, the tag can't remember, and the assets are output with every chart. Browsers only download them once, but it's untidy, so render blocks with `{% include_block %}`, which passes the context on.

To load the assets in the `<head>` instead, call the tag in your base template. Charts later in the page then don't output them again:

```html+django
{% load wagtail_vega %}
<head>
    ...
    {% wagtail_vega_assets %}
</head>
```

This loads Vega on every page that uses the template, whether or not it has a chart.

:::{note}
If you cache parts of a page with `{% cache %}`, a cached chart doesn't run the tag, so the assets may be missing from the page. Call the tag outside the cached fragment, such as in the `<head>`.
:::

## The chart template

Blocks render with `wagtail_vega/chart.html`. Its context has:

`chart`
: A {py:class}`~wagtail_vega.blocks.Chart`, with `id`, `kind` (`"vega"` or `"vega-lite"`), `spec`, `embed_options`, `description`, `caption`, `dark_config`, `fallbacks`, `svg` (the server-rendered SVG, or `None`), `tables`, and `payload_script` (the payload's `<script>` tag).

`value`, `self`
: The block's value, as for any block.

It also has the context the block was rendered in, such as `page` and `request`.

The template outputs:

```html
<figure class="wagtail-vega" id="wagtail-vega-1a2b3c4d" aria-describedby="wagtail-vega-1a2b3c4d-description">
    <wagtail-vega-chart class="wagtail-vega__chart" data-payload="wagtail-vega-1a2b3c4d-payload">
        <!-- the server-rendered SVG, or a <noscript> message -->
    </wagtail-vega-chart>
    <script id="wagtail-vega-1a2b3c4d-payload" type="application/json">{"spec": ...}</script>
    <p class="wagtail-vega__description" id="wagtail-vega-1a2b3c4d-description">...</p>
    <details class="wagtail-vega__data">
        <summary>Chart data</summary>
        <table>...</table>
    </details>
    <figcaption class="wagtail-vega__caption">...</figcaption>
</figure>
```

The `id` is random, and different each time the page is rendered.

### Overriding the template

To change the markup for every chart, put your own `wagtail_vega/chart.html` in a template directory that comes before wagtail-vega's. For one block, set its `template` option:

```python
class DonationsChartBlock(BaseChartBlock):
    class Meta:
        template = "myapp/blocks/donations_chart.html"
```

Start from a copy of `wagtail_vega/chart.html`, and keep:

- `{% load wagtail_vega %}{% wagtail_vega_assets %}`, unless you load the assets elsewhere;
- a `<wagtail-vega-chart>` element with `data-payload="{{ chart.payload_id }}"`;
- `{{ chart.payload_script }}`.

The element reads the payload when it's added to the page, so the payload script must be in the document by then. The default template puts the script after the element, which works because the scripts are deferred: the element isn't defined until the whole page has been parsed. If you load `wagtail-vega.js` without `defer`, or insert charts into a page that has already loaded it, put `{{ chart.payload_script }}` before the element.

The default template has no `{% block %}`s, so copy it rather than extending it. For example, this template adds a link under the chart, and leaves out the data table:

```html+django
{% load wagtail_vega %}{% wagtail_vega_assets %}
<figure class="wagtail-vega" id="{{ chart.id }}"{% if chart.description %} aria-describedby="{{ chart.id }}-description"{% endif %}>
    {{ chart.payload_script }}
    <wagtail-vega-chart class="wagtail-vega__chart" data-payload="{{ chart.payload_id }}">
        {% if chart.svg %}<div class="wagtail-vega__ssr">{{ chart.svg|safe }}</div>{% endif %}
    </wagtail-vega-chart>
    {% if chart.description %}<p class="wagtail-vega__description" id="{{ chart.id }}-description">{{ chart.description }}</p>{% endif %}
    {% if chart.caption %}<figcaption class="wagtail-vega__caption">{{ chart.caption }}</figcaption>{% endif %}
    <p><a href="{{ download_url }}">Download the data</a></p>
</figure>
```

`download_url` would come from the block's `get_context()` (see [](custom-data.md#hooks)).

## The `<wagtail-vega-chart>` element

`wagtail-vega.js` defines the `<wagtail-vega-chart>` custom element. When one is added to the page, it reads its payload and renders the chart. It renders again when the colour scheme changes or when asked to refresh. When it's removed from the page, it frees the Vega view.

While it renders, the server-rendered SVG or `<noscript>` message stays in place. Once the chart is drawn, it replaces them, and the element gets the `is-rendered` class. If rendering fails, the element gets the `has-error` class, keeps its previous content, and logs the error to the console.

The element has:

`refresh()`
: Renders the chart again, with the current colour scheme and CSS custom properties. Returns a promise.

`view`
: The current [Vega View](https://vega.github.io/vega/docs/api/view/), once the chart has rendered. Use it to read data or signals, or add event listeners.

`colorScheme`
: `"light"` or `"dark"`: the scheme the chart uses.

### Events

`wagtail-vega:rendered`
: Fired on the `<wagtail-vega-chart>` element each time a chart is drawn, and bubbles. Its `detail` is the [vega-embed result](https://github.com/vega/vega-embed#api-reference): `view`, `spec`, `vgSpec`, `embedOptions` and `finalize()`.

  ```js
  document.addEventListener("wagtail-vega:rendered", (event) => {
    const chart = event.target;
    const view = event.detail.view;
    view.addEventListener("click", (_event, item) => {
      if (item?.datum) console.log(chart.id, item.datum);
    });
  });
  ```

  The listener runs again for each render, including after a colour-scheme change, with a new view.

`wagtail-vega:refresh`
: Dispatch this on `document` to render every chart on the page again:

  ```js
  document.dispatchEvent(new Event("wagtail-vega:refresh"));
  ```

There's no event for errors. Check for the `has-error` class.

### Colour-scheme toggles

By default, charts follow the reader's `prefers-color-scheme`, and render again when it changes.

If your site has its own light/dark toggle, set `data-color-scheme="light"` or `data-color-scheme="dark"` on an element that contains the charts, such as `<html>`. Any other value, such as `"auto"`, means "use `prefers-color-scheme`". Charts don't watch the attribute, so dispatch `wagtail-vega:refresh` after changing it:

```js
function setColorScheme(scheme) {
  // scheme is "light", "dark" or "auto"
  document.documentElement.dataset.colorScheme = scheme;
  document.dispatchEvent(new Event("wagtail-vega:refresh"));
}
```

Only the nearest element with a `data-color-scheme` attribute counts, so one part of a page can force a scheme for the charts inside it.

### Charts added after the page loads

Charts work in content added to the page later, for example with htmx, Turbo or `fetch()`, as long as `wagtail-vega.js` has loaded and the payload script is in the document when the element is added (see [](#overriding-the-template)). If the first chart arrives this way, make sure the scripts load too: either load them on every page, or make sure the scripts in the inserted HTML run.

## vega-embed options

The `EMBED_OPTIONS` setting and the block's `embed_options` option are passed to [vega-embed](https://github.com/vega/vega-embed#options). wagtail-vega always sets some options itself:

- `defaultStyle: false` and `tooltip: {"disableDefaultStyle": true}`, so vega-embed doesn't add `<style>` elements. Tooltip styles ship in `wagtail-vega.css` instead. As a result, vega-tooltip options can't be set through `embed_options`.
- `loader`, to the restricted data loader (see {doc}`security`).
- `theme`, when the chart's theme uses a built-in vega-embed theme.
- `ast` and `expr`, in CSP-safe mode.

:::{warning}
`EMBED_OPTIONS` replaces the default, `{"actions": False, "renderer": "svg"}`, rather than adding to it. If you set it, include `"actions": False` unless you want vega-embed's actions menu. The menu's styles are part of vega-embed's default style, which wagtail-vega turns off, so it appears unstyled unless you style it yourself.
:::
