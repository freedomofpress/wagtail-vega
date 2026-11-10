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
   :members: field_order, get_spec_source, get_datasets, get_theme, get_embed_options, get_spec, use_ssr, use_fallback_table, build_chart, check_remote_datasets, get_api_representation, get_context
   :undoc-members:

   Fields: ``spec``, ``description`` and ``caption``. See :doc:`custom-data`.

.. autoclass:: wagtail_vega.blocks.Chart
   :members:
   :undoc-members:

.. autoclass:: wagtail_vega.blocks.DatasetBlock
   :members: source_fields, source_rows_urls, get_source, clean_source, get_dataset, get_source_dataset, check

   Fields: ``name``, ``source_type`` (``"paste"``, ``"document"`` or
   ``"url"``), ``paste``, ``document``, ``url`` and ``format``. See
   :ref:`custom-source-types` for adding sources.

.. autodata:: wagtail_vega.blocks.SOURCE_CHOICES
   :no-value:

.. autodata:: wagtail_vega.blocks.SOURCE_FIELDS
   :no-value:

.. autoclass:: wagtail_vega.blocks.DatasetBlockAdapter
   :members: extra_js, extra_css

.. autoclass:: wagtail_vega.blocks.FieldOrderMixin

.. autoclass:: wagtail_vega.blocks.SpecBlock

.. autoclass:: wagtail_vega.blocks.JSONBlock

.. autoclass:: wagtail_vega.blocks.PastedDataBlock
```

## Widgets

```{eval-rst}
.. autoclass:: wagtail_vega.widgets.CodeEditor
```

The code editor is registered with Wagtail's telepath, so it works in StreamField blocks, including blocks added after the page loads, and also in ordinary forms. To use it in your own block, give a `FieldBlock` a form field with this widget, as `PastedDataBlock` does.

Scripts that change a code field, such as a button that generates a spec, should change the `<textarea>`, which stays in the form and is what's submitted, and then fire an `input` event:

```js
const textarea = fieldWrapper.querySelector("textarea");
textarea.value = JSON.stringify(spec, null, 2);
textarea.dispatchEvent(new Event("input", { bubbles: true }));
```

The editor follows, as one change that can be undone. The editor also fires `input` on the textarea for every change made in it. The full contract is in the comment at the top of `static/wagtail_vega/admin/code-editor.js`.

## Admin views

```{eval-rst}
.. autofunction:: wagtail_vega.views.validate_spec

.. autofunction:: wagtail_vega.views.document_rows

.. autofunction:: wagtail_vega.views.voyager

.. autoclass:: wagtail_vega.views.SourceRowsView
   :members: get_rows
```

## Admin scripts

The admin scripts expose these on `window.wagtailVegaAdmin`, for the scripts of custom dataset sources (see {ref}`custom-source-types`). Anything else on it is internal.

`registerSource(name, {loadRows, hasData?, key?})`
: Lets the chart editor load a custom source's rows in the browser. `loadRows(datasetEl, config)` returns the rows, or a promise of them, or throws an `Error` whose message is shown. `hasData(datasetEl)` says whether the dataset has any data yet (default: true). `key(datasetEl)` returns a string that changes when the rows would, if they depend on more than the source's fields.

`sources.readFields(datasetEl, names)`
: `{name: [value, …]}` for the dataset's fields: checked checkboxes and radio buttons, selected options, and the values of other inputs and textareas. Rows URL requests read fields this way.

`dataFormat.summariseRows(rows)`
: A summary of rows, `{ok, message, warning}`, such as `{ok: true, message: "12 rows · month (date), incidents (number)", warning: ""}`.

`dataFormat.renderSummary(element, summary)`
: Shows a summary from `summariseRows()` (or `{ok: false, message}`, for an error) in `element`, with the same markup and styles as the pasted data's summary. `null` hides it.

`DatasetBlockDefinition`
: The dataset block's telepath definition, to extend.

## Themes

```{eval-rst}
.. automodule:: wagtail_vega.themes
   :members: Theme, build_theme, get_themes, get_theme, theme_choices, resolve_css_vars
```

## Specs

```{eval-rst}
.. automodule:: wagtail_vega.spec
   :members: SpecError, spec_kind, inject_datasets, remote_data, is_remote, deep_merge, iter_urls, iter_url_paths, normalize_url, host_allowed, disallowed_urls, disallowed_url_paths
```

## Validation

```{eval-rst}
.. automodule:: wagtail_vega.validation
   :members: spec_problems, SpecProblem, schema_problems, validate_spec
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
   :members: get_setting, get_allowed_hosts, site_hosts
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
