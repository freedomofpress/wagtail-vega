# API reference

This reference is generated from the code's docstrings. The guides explain how the pieces fit together: see {doc}`custom-data` for the `BaseChartBlock` hooks and {doc}`theming` for themes.

## Blocks

```{eval-rst}
.. automodule:: wagtail_vega.blocks
   :no-members:

.. autoclass:: wagtail_vega.blocks.ChartBlock
   :members: get_datasets

   Fields: ``data``, ``spec``, ``description``, ``caption`` and ``theme``.
   See :doc:`adding-charts`.

.. autoclass:: wagtail_vega.blocks.BaseChartBlock
   :members: field_order, get_spec_source, get_datasets, get_theme, get_embed_options, get_spec, use_ssr, use_fallback_table, build_chart, get_context
   :undoc-members:

   Fields: ``spec``, ``description`` and ``caption``. See :doc:`custom-data`.

.. autoclass:: wagtail_vega.blocks.Chart
   :members:
   :undoc-members:

.. autoclass:: wagtail_vega.blocks.DatasetBlock
   :members: get_dataset
   :undoc-members:

   Fields: ``name``, ``source_type`` (``"paste"``, ``"document"`` or
   ``"url"``), ``paste``, ``document``, ``url`` and ``format``.

.. autoclass:: wagtail_vega.blocks.SpecBlock

.. autoclass:: wagtail_vega.blocks.JSONBlock
```

## Themes

```{eval-rst}
.. automodule:: wagtail_vega.themes
   :members: Theme, build_theme, get_themes, get_theme, theme_choices, resolve_css_vars
```

## Specs

```{eval-rst}
.. automodule:: wagtail_vega.spec
   :members: SpecError, spec_kind, inject_datasets, remote_data, is_remote, deep_merge, iter_urls, host_allowed, disallowed_urls
```

## Validation

```{eval-rst}
.. automodule:: wagtail_vega.validation
   :members: validate_spec
```

## Data parsing

```{eval-rst}
.. automodule:: wagtail_vega.data
   :members: parse_text, detect_format, parse_delimited, parse_json, parse_bytes, document_rows
```

## Server-side rendering

```{eval-rst}
.. automodule:: wagtail_vega.ssr
   :members: is_available, render_svg, allowed_base_urls
```

## Settings

```{eval-rst}
.. automodule:: wagtail_vega.conf
   :members: get_setting
```

## Template tags

```{eval-rst}
.. automodule:: wagtail_vega.templatetags.wagtail_vega
   :no-members:

.. function:: {% wagtail_vega_assets %}

   Output the chart CSS and scripts, once per request.

   Load it with ``{% load wagtail_vega %}``. Chart blocks call it themselves,
   so the libraries are only loaded on pages that contain a chart. All
   scripts are external and deferred, with no inline JS, so a strict
   Content-Security-Policy works. See :doc:`frontend`.
```

## JSON encoding

```{eval-rst}
.. automodule:: wagtail_vega.encoders
   :members: VegaJSONEncoder
```
