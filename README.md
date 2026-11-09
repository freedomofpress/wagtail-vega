# wagtail-vega

[Vega](https://vega.github.io/vega/) and [Vega-Lite](https://vega.github.io/vega-lite/) chart blocks for Wagtail StreamFields.

- **Editors** paste a Vega or Vega-Lite spec and attach data: pasted CSV, JSON or spreadsheet cells, a document, or a URL. They can create new kinds of chart without changing any code.
- **Developers** subclass the block to supply data from anywhere, e.g. the database.
- **Themes** are Vega `config` objects. They can have dark-mode variants and can pull colours from your site's CSS custom properties.
- **Privacy and security:** the Vega libraries are vendored, so there are no CDN requests. Data hosts are allowlisted, and a CSP-safe mode works without `unsafe-eval`, inline scripts or inline styles.
- **Accessibility:**
  - each chart has a description for screen readers;
  - each chart has a collapsible data table;
  - optional server-rendered SVG means charts show without JavaScript.

## Install

```sh
pip install wagtail-vega          # or wagtail-vega[ssr] for server-side rendering
```

```python
INSTALLED_APPS = [..., "wagtail_vega", "wagtail.documents", ...]
```

```python
from wagtail.fields import StreamField
from wagtail_vega.blocks import ChartBlock

class ArticlePage(Page):
    body = StreamField([..., ("chart", ChartBlock())])
```

The block's template loads the JS and CSS the first time a chart appears on a page, so pages without charts don't download Vega. Your templates need `request` in the context, which is the default for Wagtail pages. Otherwise the assets are emitted once per chart.

## Writing specs

Specs refer to data **by name**, and the editor attaches a dataset with the same name:

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

- **Vega-Lite:** inline datasets are added to the top-level `datasets`. URL datasets replace every `{"name": ...}` reference.
- **Vega:** the matching entry in the `data` array gets the `values` or `url`; its `transform`s are kept.
- Inline `values` in a spec still work for quick one-off charts.
- Specs are checked against the bundled JSON schemas when the page is saved. Errors point at the problem, e.g. `encoding.x.type: 'nominl' is not valid…`.
## Adding data

Each dataset has a **Paste / Document / URL** toggle, and only the inputs for the selected source are shown.

- **Paste** accepts CSV, JSON, or cells copied straight from Excel, Google Sheets or Numbers (which copy as tab-separated text). The format is detected automatically: tab, comma or semicolon, whichever is most common in the header row. A live summary under the box shows what was read, e.g. `Tab-separated · 6 rows · quarter (text), requests (number)`, and warns about ragged rows or invalid JSON.
- **Document** takes a `.csv`, `.tsv` or `.json` file from the Wagtail document library.
- **URL** points at a file on an allowed host. It is fetched by the browser, or by the server when SSR is on.

**Value types:** numbers (including `1,234`), `true`/`false` and blank cells (as `null`) are converted. Values with leading zeros, like ZIP codes, stay as text, and so do dates.

- **Time zones:** Vega parses `2026-01-01` as UTC midnight. Use `utcyearmonth` etc. in `timeUnit`, or the axis may show the previous month.

## Custom data sources

Subclass `BaseChartBlock` and override `get_datasets()`. It returns `{name: rows}`, or `{name: {"url": ..., "format": {"type": "csv"}}}` for a remote dataset:

```python
from wagtail_vega.blocks import BaseChartBlock

class DonationsChartBlock(BaseChartBlock):
    def get_datasets(self, value, context=None):
        return {"donations": list(Donation.objects.values("month", "total"))}
```

Dates are serialised as ISO strings and Decimals as numbers.

These hooks are also available:

| Hook | Purpose |
| --- | --- |
| `get_spec_source(value)` | The spec before data and theming are applied. Override it to ship a fixed spec from code. |
| `get_datasets(value, context)` | Named datasets. |
| `get_theme(value, context)` | Picks a `Theme`. |
| `get_embed_options(value, context, theme)` | vega-embed options. |
| `get_spec(value, context, datasets, theme, dark)` | The final spec. |
| `build_chart(value, context)` | The `Chart` object passed to the template. |

`Meta` options: `theme`, `ssr`, `fallback_table`, `embed_options`, plus the usual `template`, `icon` and `label`. Set the `field_order` class attribute (a tuple of field names) to change the order of fields in the editor. `ChartBlock` subclasses `BaseChartBlock` and adds the `data` and `theme` fields, with data shown first.

## Themes

```python
WAGTAIL_VEGA = {
    "THEMES": {
        "house": {
            "label": "House style",
            "config": {                      # any Vega config
                "font": "Inter, sans-serif",
                "background": "var(--chart-bg, white)",
                "range": {"category": ["var(--brand)", "#2a9d8f", "#e9c46a"]},
            },
            "dark": {"axis": {"labelColor": "#ddd", "gridColor": "#444"}},  # merged on top in dark mode
            "fallbacks": {"--brand": "#c0392b"},                            # for SSR / missing CSS vars
        },
        "minimal": {"view": {"stroke": None}},       # a plain dict is treated as the config
        "print": "myproject.charts.PRINT_THEME",     # a dotted path
        "538": "vega:fivethirtyeight",               # a theme bundled with vega-embed
    },
    "DEFAULT_THEME": "house",
}
```

- **Precedence:** the theme config is applied first, then the dark overrides (in dark mode), then the spec's own `config`, which wins. A block's `Meta.theme` beats the editor's choice, which beats `DEFAULT_THEME`.
- **CSS variables:** `var(--token)` strings are resolved in the browser from the chart element's computed style. On the server they come from `fallbacks`, or from the `var(--x, default)` default.
- **Colour scheme:** the nearest `[data-color-scheme="light|dark"]` ancestor decides, otherwise `prefers-color-scheme`. If your site has its own light/dark toggle, re-render charts after it changes with `document.dispatchEvent(new Event("wagtail-vega:refresh"))`.
- **Styling:** `wagtail-vega.css` uses zero-specificity `:where()` selectors, so your own CSS overrides it easily.

## Settings

| Setting | Default | |
| --- | --- | --- |
| `THEMES`, `DEFAULT_THEME` | `{}`, `None` | See [Themes](#themes). |
| `ALLOWED_DATA_HOSTS` | `[]` | Hosts that specs and URL datasets may load from (`"*.example.org"` also matches subdomains). Relative URLs are always allowed. Checked on save and again in the browser by a restricted loader. |
| `CSP_SAFE` | `False` | Uses `vega-interpreter` and an eval-free CSV parser, so charts work with `script-src 'self'` and no `unsafe-eval`. A few expression functions are unavailable in this mode. |
| `SSR` | `False` | Server-render an SVG with vl-convert (needs the `ssr` extra). Results are cached in the Django cache. |
| `SSR_CACHE_TIMEOUT` | 1 day | |
| `FALLBACK_TABLE`, `FALLBACK_TABLE_MAX_ROWS` | `True`, `100` | A `<details>` table of the inline data. |
| `VALIDATE_SCHEMA` | `True` | |
| `EMBED_OPTIONS` | `{"actions": False, "renderer": "svg"}` | Default vega-embed options. |

No styles are injected at runtime: tooltip styles ship in `wagtail-vega.css`, so a strict `style-src 'self'` also works.

## Known limitations

- **SSR:**
  - only the light config is used;
  - `"width": "container"` charts render at a default width until JS takes over;
  - built-in (`vega:`) themes apply to Vega-Lite specs only.
- **Spec editing:** the admin uses a plain textarea for specs. Live preview works through Wagtail's page preview.

## Development

```sh
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_sandbox
.venv/bin/python manage.py runserver          # http://localhost:8000, admin/admin
WAGTAIL_VEGA_CSP_SAFE=1 WAGTAIL_VEGA_SSR=1 .venv/bin/python manage.py runserver  # strict CSP + SSR
WAGTAIL_VEGA_SANDBOX_AUTOLOGIN=1 .venv/bin/python manage.py runserver  # skip login (for headless screenshots)
```

To update the vendored JS and schemas, edit the versions in `scripts/vendor.py` and run it. Each tarball is checked against npm's integrity hash.

## Roadmap

- A code editor with live preview in the admin.
- A visual (Voyager-style) chart builder.
- Developer-defined chart templates that expose only some options to editors.
- Reusable dataset snippets.
- A JSON endpoint for large datasets.
