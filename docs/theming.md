# Theming

A theme is a [Vega `config` object](https://vega.github.io/vega-lite/docs/config.html): fonts, colours, axes, legends, mark defaults, and so on. Themes are registered in the `WAGTAIL_VEGA` setting, and editors pick one per chart.

## Defining themes

```python
WAGTAIL_VEGA = {
    "THEMES": {
        # A full definition
        "house": {
            "label": "House style",
            "config": {
                "font": "Inter, sans-serif",
                "background": "var(--chart-bg, white)",
                "range": {"category": ["var(--brand)", "#2a9d8f", "#e9c46a"]},
            },
            "dark": {"axis": {"labelColor": "#ddd", "gridColor": "#444"}},
            "fallbacks": {"--brand": "#c0392b"},
        },
        # A plain dict is the config
        "minimal": {"view": {"stroke": None}},
        # A dotted path to a dict (or Theme) defined in Python
        "print": "myproject.charts.PRINT_THEME",
        # A theme bundled with vega-embed
        "538": "vega:fivethirtyeight",
    },
    "DEFAULT_THEME": "house",
}
```

Each value in `THEMES` can be:

A full definition
: A dict with any of these keys. Any other key is an error.

  `label`
  : The name editors see. Defaults to the theme's key.

  `config`
  : A Vega or Vega-Lite config object.

  `dark`
  : Config to merge over `config` in dark mode. See [](#dark-mode).

  `fallbacks`
  : Values for CSS custom properties, keyed by name (`{"--brand": "#c0392b"}`). See [](#css-custom-properties).

  `vega_theme`
  : The name of a theme bundled with vega-embed, used underneath `config`. See [](#built-in-themes).

A plain dict
: If a dict has none of the keys `config`, `dark`, `fallbacks` or `vega_theme`, the whole dict is used as the config.

  This means a `label` in a plain dict ends up in the config rather than naming the theme. To give a theme a label, use a full definition.

A dotted path
: The import path of a dict (either kind) or a {py:class}`~wagtail_vega.themes.Theme`, for themes that are too long for settings.

`"vega:<name>"`
: A theme bundled with vega-embed.

A misconfigured theme raises `ImproperlyConfigured` when themes are loaded, which happens when a chart is rendered or the theme choices are built.

`DEFAULT_THEME` is the name of the theme used when neither the block nor the editor picks one. It must be a key in `THEMES`. If it's `None` (the default) and no theme is picked, charts use Vega's own defaults.

## Which theme is used

A chart's theme is the first of these that's set:

1. the block's `theme` option (see [](adding-charts.md#block-options));
2. the theme the editor picked;
3. `DEFAULT_THEME`.

A name that isn't in `THEMES`, such as a theme that has since been removed, is skipped, and `DEFAULT_THEME` is used.

To pick a theme some other way, override `get_theme()` on your block. It returns a `Theme` or `None`; use `wagtail_vega.themes.get_theme(name)` to look one up:

```python
from wagtail_vega.blocks import ChartBlock
from wagtail_vega.themes import get_theme


class SectionChartBlock(ChartBlock):
    def get_theme(self, value, context=None):
        page = context.get("page") if context else None
        if page and page.get_parent().slug == "print":
            return get_theme("print")
        return super().get_theme(value, context)
```

## How configs are merged

The final config is built from these layers, each merged deeply over the previous ones:

1. the theme's `config`;
2. in dark mode, the theme's `dark` overrides;
3. the spec's own `config`.

So a spec can always override its theme, for example to change one chart's colours. Merging is deep for objects, but arrays (such as `range.category`) are replaced, not merged.

## CSS custom properties

Strings in a config can refer to CSS custom properties with `var(--name)` or `var(--name, default)`. This lets charts follow your site's design tokens:

```python
"config": {
    "background": "var(--chart-bg, white)",
    "range": {"category": ["var(--brand)", "var(--accent)", "#e9c46a"]},
}
```

```css
:root {
  --brand: #6a4c93;
  --accent: #2a9d8f;
  --chart-bg: #fff;
}
```

In the browser, each `var()` is replaced with the first of:

1. the property's value on the `<wagtail-vega-chart>` element, from its computed style;
2. the theme's `fallbacks` value for that property;
3. the default in `var(--name, default)`.

Because the value comes from the chart element, you can set different values for different parts of a page, for example with `.sidebar .wagtail-vega { --brand: … }`. Values are read each time the chart renders, including when the colour scheme changes.

When the chart is {doc}`rendered on the server <ssr>`, there's no page CSS, so `var()` is replaced with the `fallbacks` value or the `var()` default. Give every property you use one or the other, or the server-rendered SVG will have an invalid colour until JavaScript runs.

`var()` works anywhere in the spec, not just in the config: for example, a mark's `"color": "var(--accent)"`. The only exception is data (anything under `data`, `datasets` or `values`), which is left exactly as it is. The same rule applies in the browser and on the server.

Nested `var()`s, such as `var(--a, var(--b))`, aren't supported.

## Dark mode

There are two ways to support dark mode, which can be combined.

**CSS custom properties.** If the config takes its colours from custom properties, give them dark values in your CSS. When the reader's system colour scheme changes, charts render again and pick up the new values.

```css
@media (prefers-color-scheme: dark) {
  :root {
    --chart-bg: #1b1b1b;
  }
}
```

**`dark` overrides.** Values in the theme's `dark` dict are merged over `config` when the colour scheme is dark. This suits values that don't come from CSS:

```python
"house": {
    "config": {
        "background": "var(--chart-bg, white)",
        "axis": {"labelColor": "#333", "titleColor": "#333"},
    },
    "dark": {
        "axis": {"labelColor": "#ddd", "titleColor": "#ddd", "gridColor": "#444"},
        "view": {"stroke": "#444"},
    },
}
```

Vega-Lite's default background is white, so a dark theme usually needs a `background` too, either in `dark` or from a custom property.

The colour scheme is decided in the browser, for each chart:

1. If the chart is inside an element with `data-color-scheme="light"` or `data-color-scheme="dark"`, the nearest one wins.
2. Otherwise, the reader's `prefers-color-scheme` is used.

If your site has its own light/dark toggle, see [](frontend.md#colour-scheme-toggles).

Server-side rendering always uses the light config.

## Built-in themes

vega-embed bundles these themes: `carbong10`, `carbong90`, `carbong100`, `carbonwhite`, `dark`, `excel`, `fivethirtyeight`, `ggplot2`, `googlecharts`, `latimes`, `powerbi`, `quartz`, `urbaninstitute` and `vox`. Use one with `"vega:<name>"`, or as the base of your own theme with `vega_theme`:

```python
"THEMES": {
    "538": "vega:fivethirtyeight",
    "538-house": {
        "label": "FiveThirtyEight, house fonts",
        "vega_theme": "fivethirtyeight",
        "config": {"font": "Inter, sans-serif"},
    },
}
```

The built-in theme is passed to vega-embed as its `theme` option, so it's applied in the browser underneath the merged config. Server-side rendering only applies built-in themes to Vega-Lite specs.

## Styling the chart's HTML

`wagtail-vega.css` styles the chart's container, the screen-reader description, the data table and Vega's tooltips. Its rules use `:where()`, which has zero specificity, so any of your own CSS overrides them. The classes are:

| Class | Element |
| --- | --- |
| `.wagtail-vega` | The `<figure>` around everything. |
| `.wagtail-vega__chart` | The `<wagtail-vega-chart>` element. Gets `.is-rendered` once the chart is drawn, or `.has-error` if it failed. |
| `.wagtail-vega__target` | The element vega-embed draws into. |
| `.wagtail-vega__ssr` | The server-rendered SVG, before JavaScript replaces it. |
| `.wagtail-vega__noscript` | The "needs JavaScript" message. |
| `.wagtail-vega__description` | The description. Visually hidden, but read by screen readers. |
| `.wagtail-vega__data` | The `<details>` element holding the data table. |
| `.wagtail-vega__caption` | The `<figcaption>`. |

For example:

```css
.wagtail-vega {
  margin-block: 2rem;
}
.wagtail-vega__caption {
  font-size: 0.875rem;
  color: var(--muted);
}
.wagtail-vega__chart.has-error::after {
  content: "This chart couldn't be displayed.";
}
```

Tooltips use the `#vg-tooltip-element` styles from `wagtail-vega.css`, which are for a light background. For dark tooltips, override them in your CSS:

```css
@media (prefers-color-scheme: dark) {
  #vg-tooltip-element {
    background-color: rgba(32, 32, 32, 0.9);
    border-color: #555;
    color: white;
  }
}
```
