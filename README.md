# wagtail-vega

[Vega](https://vega.github.io/vega/) and [Vega-Lite](https://vega.github.io/vega-lite/) chart blocks for Wagtail StreamFields.

- **Editors** paste a Vega or Vega-Lite spec and attach data: pasted CSV, JSON or spreadsheet cells, a document, or a URL. They can create new kinds of chart without changing any code, in a code editor that underlines errors in the spec and data as they type, or build a chart visually with Vega Voyager.
- **Developers** subclass the block to supply data from anywhere, e.g. the database.
- **Themes** are Vega `config` objects. They can have dark-mode variants and can pull colours from your site's CSS custom properties.
- **Privacy and security:** the Vega libraries are vendored, so there are no CDN requests. Data hosts are allowlisted, and a CSP-safe mode works without `unsafe-eval`, inline scripts or inline styles.
- **Accessibility:** each chart has a description for screen readers and a collapsible data table. Optional server-rendered SVG means charts show without JavaScript.

Supports Wagtail 7.4 LTS and newer, Django 5.2 and newer, and Python 3.10 and newer.

**Documentation: <https://wagtail-vega.readthedocs.io/>** (source in [`docs/`](docs/))

## Install

```sh
pip install wagtail-vega          # or wagtail-vega[ssr] for server-side rendering
```

```python
INSTALLED_APPS = [..., "wagtail_vega", "wagtail.documents", ...]
```

## Quickstart

```python
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail_vega.blocks import ChartBlock

class ArticlePage(Page):
    body = StreamField([..., ("chart", ChartBlock())])
```

Render the StreamField with `{% include_block %}` as usual. The block loads Vega's JS and CSS the first time a chart appears on a page.

In the admin, add a dataset named `source` with some pasted CSV, and a spec that refers to it by name:

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

To supply data from code, subclass `BaseChartBlock`:

```python
from wagtail_vega.blocks import BaseChartBlock

class DonationsChartBlock(BaseChartBlock):
    def get_datasets(self, value, context=None):
        return {"donations": list(Donation.objects.values("month", "total"))}
```

See the documentation for [custom data sources](https://wagtail-vega.readthedocs.io/en/latest/custom-data.html), [theming](https://wagtail-vega.readthedocs.io/en/latest/theming.html), [security and CSP](https://wagtail-vega.readthedocs.io/en/latest/security.html), [server-side rendering](https://wagtail-vega.readthedocs.io/en/latest/ssr.html) and [all settings](https://wagtail-vega.readthedocs.io/en/latest/settings.html).

## Development

```sh
python -m venv .venv && .venv/bin/pip install -e ".[dev,docs]"
.venv/bin/python -m playwright install chromium   # or pass --browser-channel chrome below
.venv/bin/pytest                                   # Python, admin and browser tests
npm test                                           # JS unit tests (node:test, no dependencies)
.venv/bin/sphinx-build -W --keep-going -b html docs docs/_build/html   # documentation
```

To run the CI matrix locally, use `tox` (e.g. `tox -e py310-wagtail74-django52 -- --browser-channel chrome`).

The sandbox site:

```sh
.venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_sandbox
.venv/bin/python manage.py runserver          # http://localhost:8000, admin/admin
WAGTAIL_VEGA_CSP_SAFE=1 WAGTAIL_VEGA_SSR=1 .venv/bin/python manage.py runserver  # strict CSP + SSR
WAGTAIL_VEGA_SANDBOX_AUTOLOGIN=1 .venv/bin/python manage.py runserver  # skip login (for headless screenshots)
```

To update the vendored Vega JS and schemas, edit the versions in `scripts/vendor.py` and run it. Each tarball is checked against npm's integrity hash. The admin code editor (CodeMirror 6) is bundled reproducibly from pinned npm packages with `npm ci && npm run build`; the output is committed, so installing the package needs no Node.

See [Testing and contributing](https://wagtail-vega.readthedocs.io/en/latest/contributing.html) for more.

## Roadmap

- Live preview next to the code editor.
- A maintained, keyboard-accessible visual chart builder to replace Voyager.
- Developer-defined chart templates that expose only some options to editors.
- Reusable dataset snippets.
- A JSON endpoint for large datasets.
