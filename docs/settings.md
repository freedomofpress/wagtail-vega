# Settings

All settings go in a `WAGTAIL_VEGA` dict in your Django settings. Every key is optional.

```python
WAGTAIL_VEGA = {
    "THEMES": {
        "house": {
            "label": "House style",
            "config": {"font": "Inter, sans-serif", "range": {"category": ["var(--brand)", "#2a9d8f"]}},
            "dark": {"axis": {"labelColor": "#ddd", "gridColor": "#444"}},
            "fallbacks": {"--brand": "#c0392b"},
        },
        "538": "vega:fivethirtyeight",
    },
    "DEFAULT_THEME": "house",
    "ALLOWED_DATA_HOSTS": ["vega.github.io", "*.example.org"],
    "CSP_SAFE": True,
    "SSR": True,
    "SSR_CACHE_TIMEOUT": 60 * 60 * 24,
    "FALLBACK_TABLE": True,
    "FALLBACK_TABLE_MAX_ROWS": 100,
    "VALIDATE_SCHEMA": True,
    "EMBED_OPTIONS": {"actions": False, "renderer": "svg"},
    "VISUAL_EDITOR": "voyager",
}
```

Settings are read each time they're used, so `override_settings` works in tests. Each key you set replaces its default; dicts aren't merged with the default.

## `THEMES`

Default: `{}`

Themes editors can pick from, keyed by name. Each value is a theme definition dict, a plain Vega config dict, a dotted path to either, or `"vega:<name>"` for a theme bundled with vega-embed. See {doc}`theming`.

## `DEFAULT_THEME`

Default: `None`

The name of the theme used when neither the block nor the editor picks one. It must be a key in `THEMES`: `manage.py check` reports it if it isn't (`wagtail_vega.E002`), and rendering raises `ImproperlyConfigured`. With `None`, charts without a theme use Vega's defaults.

## `ALLOWED_DATA_HOSTS`

Default: `[]`

Hosts that specs, URL datasets and server-side rendering may load from. `"*.example.org"` matches `example.org` and its subdomains, and `"*"` matches every host. Relative URLs and your site's own hostnames (from Wagtail's sites and `WAGTAILADMIN_BASE_URL`, except `localhost` and loopback addresses) are always allowed. Checked when pages are saved, and again in the browser. See {doc}`security`.

## `CSP_SAFE`

Default: `False`

Render charts without `eval`, so they work under a Content Security Policy without `'unsafe-eval'`. Evaluates expressions with the vega-interpreter that vega-embed bundles, and uses an eval-free CSV parser. A few expression functions are unavailable in this mode. See {ref}`csp-safe`.

## `SSR`

Default: `False`

Render each chart to SVG on the server, with vl-convert. Needs the `ssr` extra. Blocks can override it with their `ssr` option. See {doc}`ssr`.

## `SSR_CACHE_TIMEOUT`

Default: `86400` (one day)

How long, in seconds, server-rendered SVGs are kept in Django's default cache. `None` keeps them until they're evicted.

## `FALLBACK_TABLE`

Default: `True`

Render a collapsible table of each chart's inline data under the chart. Blocks can override it with their `fallback_table` option. See {doc}`accessibility`.

## `FALLBACK_TABLE_MAX_ROWS`

Default: `100`

The most rows to show in each fallback table.

## `VALIDATE_SCHEMA`

Default: `True`

Validate specs against the bundled Vega and Vega-Lite JSON schemas when pages are saved. With `False`, specs still need a recognised `$schema`, and the URL allowlist is still checked.

## `EMBED_OPTIONS`

Default: `{"actions": False, "renderer": "svg"}`

Options for [vega-embed](https://github.com/vega/vega-embed#options), merged over the default. Blocks can add to them with their `embed_options` option. wagtail-vega always sets `defaultStyle` and `loader`, adds `disableDefaultStyle` to tooltip options, and sets `theme`, `ast` and `expr` when needed. See [](frontend.md#vega-embed-options).

## `VISUAL_EDITOR`

Default: `"voyager"`

The mode the chart editor's **Visual** tab opens in: `"voyager"` for [Vega Voyager](https://github.com/vega/voyager), or `"simple"` for wagtail-vega's own settings, which work with the keyboard and screen readers. Editors can switch between them, and their browser remembers the mode they chose last, which wins over this setting. On narrow screens, the editor opens in Simple. `manage.py check` reports other values (`wagtail_vega.E003`), which mean `"voyager"`. See {ref}`chart-editor`.
