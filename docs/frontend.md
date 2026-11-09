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

If there's no `request` in the context (for example, with `{{ page.body }}`), the tag can't remember. Each chart then outputs the stylesheet and a small loader script, `wagtail-vega-loader.js`. The first copy of the loader to run loads the libraries; the others do nothing. Prefer `{% include_block %}`, which passes the context on: the libraries then start downloading while the page is still being parsed, rather than after it.

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

  Each table in `tables` has `name`, `columns`, `rows` (lists of values), `truncated` and `total`. It also has `head` (`{"name", "numeric"}` for each column) and `cells` (rows of `{"value", "numeric"}`), for templates that treat columns of numbers differently; the default template right-aligns them.

`value`, `self`
: The block's value, as for any block.

It also has the context the block was rendered in, such as `page` and `request`.

The template outputs:

```html
<figure class="wagtail-vega" id="wagtail-vega-1a2b3c4d" aria-describedby="wagtail-vega-1a2b3c4d-description">
    <script id="wagtail-vega-1a2b3c4d-payload" type="application/json">{"spec": ...}</script>
    <wagtail-vega-chart class="wagtail-vega__chart" data-payload="wagtail-vega-1a2b3c4d-payload"
                        data-error-message="Sorry, this chart couldn't be displayed. ...">
        <!-- the server-rendered SVG, or a <noscript> message -->
    </wagtail-vega-chart>
    <p class="wagtail-vega__description" id="wagtail-vega-1a2b3c4d-description">...</p>
    <details class="wagtail-vega__data">
        <summary>Chart data</summary>
        <div class="wagtail-vega__table"><table>...</table></div>
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

The element reads the payload when it's added to the page, so put `{{ chart.payload_script }}` **before** the element, as the default template does. Then the payload is in the document however and whenever the element is upgraded.

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

While it renders, the server-rendered SVG or `<noscript>` message stays in place, and the element has `aria-busy="true"`. Once the chart is drawn and its data has loaded, it replaces them, and the element gets the `is-rendered` class.

Until then, `wagtail-vega.css` gives the element a minimum height, so the text below doesn't move down when the chart appears. It's 20rem by default; set `--wagtail-vega-loading-height` to suit your charts, or to `0` to turn it off. There's no minimum height when JavaScript is off, or when a server-rendered SVG is showing.

If rendering fails, the element gets the `has-error` class, logs the error to the console, and fires `wagtail-vega:error`. Unless a server-rendered SVG is still showing, it also adds a `<p class="wagtail-vega__error">` with the text of its `data-error-message` attribute, so readers know something is missing: "Sorry, this chart couldn't be displayed.", followed by "Its data is under “Chart data” below." when there's a data table. The message is removed if the chart later renders. That covers an invalid spec, and also data that fails to load or parse (a missing file, or CSV read as JSON). If the spec was invalid, the element keeps its previous content. If only the data failed, the chart's axes and frame are drawn without data.

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

`wagtail-vega:error`
: Fired on the `<wagtail-vega-chart>` element when rendering fails or the chart's data doesn't load, and bubbles. Its `detail.error` is the `Error`:

  ```js
  document.addEventListener("wagtail-vega:error", (event) => {
    reportError(`Chart ${event.target.id} failed: ${event.detail.error.message}`);
  });
  ```

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

- `defaultStyle: false`, and `disableDefaultStyle: true` in the tooltip options, so vega-embed and vega-tooltip don't add `<style>` elements. Their styles ship in `wagtail-vega.css` instead, including the actions menu's. Other [vega-tooltip options](https://github.com/vega/vega-tooltip/blob/main/docs/APIs.md#options) given as a dict are kept, and `"tooltip": False` turns tooltips off. Unless you set the tooltip `theme`, it follows the chart's colour scheme (`"light"` or `"dark"`).
- `loader`, to the restricted data loader (see {doc}`security`).
- `theme`, when the chart's theme uses a built-in vega-embed theme.
- `ast` and `expr`, in CSP-safe mode.

The options are merged in this order, each over the last: the defaults (`{"actions": False, "renderer": "svg"}`), the `EMBED_OPTIONS` setting, and the block's `embed_options`.

:::{warning}
vega-embed's actions menu (`"actions": True`) includes **Open in Vega Editor**, which sends the chart's spec, data included, to the Vega Editor at vega.github.io. If charts may hold unpublished data, leave actions off, or pick the ones you want: `"actions": {"export": True, "source": False, "compiled": False, "editor": False}`.
:::

## The Wagtail API

Chart blocks implement `get_api_representation()`, so [Wagtail's API](https://docs.wagtail.org/en/stable/advanced_topics/api/) returns something a headless frontend can render, rather than the editor's raw input:

```json
{
  "kind": "vega-lite",
  "spec": {"$schema": "…", "datasets": {"source": [{"quarter": "Q1", "requests": 5}]}, "config": {"font": "…"}},
  "darkConfig": {"font": "…", "axis": {"labelColor": "#ddd"}},
  "embed": {"actions": false, "renderer": "svg", "defaultStyle": false, "tooltip": {"disableDefaultStyle": true}},
  "fallbacks": {"--brand": "#c0392b"},
  "allowedHosts": ["vega.github.io"],
  "cspSafe": false,
  "description": "Requests per quarter",
  "caption": "Source: FOIA logs"
}
```

That's the same payload `<wagtail-vega-chart>` reads, plus the description and caption. Render it with vega-embed: use `darkConfig` as the spec's `config` in dark mode, resolve any `var(--…)` strings (or replace them with `fallbacks`), and keep data loading to `allowedHosts`, as `wagtail-vega.js` does.
