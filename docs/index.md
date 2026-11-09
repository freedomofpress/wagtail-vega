# wagtail-vega

[Vega](https://vega.github.io/vega/) and [Vega-Lite](https://vega.github.io/vega-lite/) chart blocks for Wagtail StreamFields.

wagtail-vega gives editors a chart block. They paste a Vega or Vega-Lite spec and attach data, so they can make new kinds of chart without code changes. Developers can subclass the block to supply data from the database, an API or anything else Python can reach.

- **Themes** are Vega `config` objects. They can have dark-mode variants and can take colours from your site's CSS custom properties.
- **No third-party requests:** the Vega libraries are vendored and served from your static files.
- **Security:** data hosts are allowlisted, and a CSP-safe mode works without `unsafe-eval`, inline scripts or inline styles.
- **Accessibility:** charts have a screen-reader description and a collapsible data table. With optional server-side rendering, charts show without JavaScript.

```python
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail_vega.blocks import ChartBlock


class ArticlePage(Page):
    body = StreamField([("chart", ChartBlock())])
```

New to wagtail-vega? Start with {doc}`overview`, then {doc}`installation`.

## Contents

Getting started
: {doc}`overview` · {doc}`installation`

Guides
: {doc}`adding-charts` · {doc}`editor-experience` · {doc}`custom-data` · {doc}`theming` · {doc}`frontend` · {doc}`security` · {doc}`ssr` · {doc}`accessibility`

Reference
: {doc}`settings` · {doc}`api` · {doc}`changelog`

Project
: {doc}`contributing`

```{toctree}
:caption: Getting started
:maxdepth: 2
:hidden:

overview
installation
```

```{toctree}
:caption: Guides
:maxdepth: 2
:hidden:

adding-charts
editor-experience
custom-data
theming
frontend
security
ssr
accessibility
```

```{toctree}
:caption: Reference
:maxdepth: 2
:hidden:

settings
api
changelog
```

```{toctree}
:caption: Project
:maxdepth: 2
:hidden:

contributing
GitHub repository <https://github.com/freedomofpress/wagtail-vega>
```
