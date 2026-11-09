# Adding charts to models

## `ChartBlock`

{py:class}`~wagtail_vega.blocks.ChartBlock` is the block for editors. Add it to any StreamField:

```python
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail_vega.blocks import ChartBlock


class ArticlePage(Page):
    body = StreamField(
        [
            # ... your other blocks
            ("chart", ChartBlock()),
        ],
        blank=True,
    )
```

It can also go inside a `StructBlock`, `ListBlock` or nested `StreamBlock`, like any other block.

`ChartBlock` has these fields, in this order:

| Field | Block | |
| --- | --- | --- |
| `data` | `ListBlock(DatasetBlock())` | Named datasets that the spec can refer to. Can be empty. |
| `spec` | `SpecBlock` | The Vega or Vega-Lite spec, as JSON. Required. |
| `description` | `TextBlock` | Optional. Read to people using screen readers; not shown. |
| `caption` | `CharBlock` | Optional. Shown under the chart, as the figure's `<figcaption>`. |
| `theme` | `ChoiceBlock` | Optional. One of the themes in `WAGTAIL_VEGA["THEMES"]`. Blank means the site default. |

The theme choices are read from settings when the form is built, so adding or removing a theme doesn't need a migration.

## Block options

Chart blocks take these options, as well as the usual block options such as `label`, `icon`, `template`, `group` and `help_text`:

`theme`
: The name of a theme to always use. It overrides the editor's choice and `DEFAULT_THEME`. Default: `None`.

`ssr`
: Whether to {doc}`render an SVG on the server <ssr>`. Default: `None`, which uses the `SSR` setting.

`fallback_table`
: Whether to render a table of the chart's data. Default: `None`, which uses the `FALLBACK_TABLE` setting.

`embed_options`
: Extra [vega-embed options](https://github.com/vega/vega-embed#options), merged over the `EMBED_OPTIONS` setting. Default: `None`.

Pass them as keyword arguments:

```python
body = StreamField(
    [
        ("chart", ChartBlock()),
        ("print_chart", ChartBlock(label="Print chart", theme="print", ssr=True)),
    ]
)
```

Or set them on a subclass's `Meta`:

```python
class PrintChartBlock(ChartBlock):
    class Meta:
        label = "Print chart"
        theme = "print"
        ssr = True
        fallback_table = False
        embed_options = {"padding": 16}
```

`theme="print"` must be the name of a theme in `WAGTAIL_VEGA["THEMES"]`. If it isn't, the default theme is used.

When a block has a fixed `theme`, the editor's theme picker has no effect. Remove the field from a subclass with `theme = None` to hide it:

```python
class PrintChartBlock(ChartBlock):
    theme = None  # removes the theme picker

    class Meta:
        theme = "print"
```

## Field order

`ChartBlock` shows the data first, then the spec. To change the order in a subclass, set the `field_order` class attribute to a tuple of field names. Fields you leave out follow in the order they were declared:

```python
class SpecFirstChartBlock(ChartBlock):
    field_order = ("spec", "data")
    # Fields: spec, data, description, caption, theme
```

`field_order` only orders fields declared on the class and its parents. Subclasses inherit it.

## Specs

The spec field holds a Vega or Vega-Lite spec as JSON, stored as native JSON in the StreamField. When the page is saved, the spec is checked:

- It must be a JSON object with a `$schema`, such as `https://vega.github.io/schema/vega-lite/v6.json` or `https://vega.github.io/schema/vega/v6.json`. The `$schema` decides whether it's Vega or Vega-Lite.
- It's validated against the JSON schema for Vega 6 or Vega-Lite 6, which ship with wagtail-vega. Errors point at the problem, e.g. `encoding.x.type: 'nominl' is not valid…`. Up to five errors are shown. Set `VALIDATE_SCHEMA` to `False` to turn this off; the `$schema` is still required.
- Every literal `url` in the spec must be relative or on an allowed host (see {doc}`security`).

If the JSON can't be parsed, the editor's text is shown again with the error, so nothing is lost.

## Datasets

Each item in the `data` list is a {py:class}`~wagtail_vega.blocks.DatasetBlock`, with a **name** and a **source**. Editors pick a source with a Paste / Document / URL toggle, and only the inputs for that source are shown. When the page is saved, inputs for the other sources are cleared.

Names must start with a letter or underscore and contain only letters, numbers, hyphens and underscores. They must be unique within a chart. The default name is `source`.

Every dataset the spec loads by name must be one of the chart's datasets, or the block doesn't validate. That covers each `"data": {"name": ...}` in a Vega-Lite spec, at any depth (layers, lookups), except names in the spec's own `datasets`, and each entry of a Vega spec's `data` that has only a `name` (and maybe a `format`). The check is in `ChartBlock.clean()`, against the names in `data`; if a subclass adds datasets in `get_datasets()`, override `clean()` too. Pages saved before this check keep rendering, and the check applies the next time they're saved.

### Paste

Pasted data can be CSV, JSON, or cells copied from Excel, Google Sheets or Numbers, which copy as tab-separated text.

- **JSON** is used if the text starts with `[` or `{`. It must be an array of rows, or an object with a `values` array.
- Otherwise, the first line is the header row, and the delimiter is whichever of tab, comma or semicolon is most common in it. Ties go to tab, then comma.

A live summary under the box shows what was read, e.g. `Tab-separated · 6 rows · quarter (text), requests (number)`. It warns about ragged rows or invalid JSON.

Cells in delimited text are converted like this:

- Numbers, including ones with thousands separators like `1,234`, become numbers.
- `true` and `false` (in any case) become booleans.
- Blank cells become `null`.
- Values with leading zeros, like ZIP codes and IDs (`02134`), stay as text.
- Dates stay as text. Vega-Lite parses them for `temporal` fields.

JSON values are used as they are.

:::{note}
Vega parses dates like `2026-01-01` as midnight UTC. Use UTC time units, such as `"timeUnit": "utcyearmonth"`, or the axis may show the previous month for readers west of UTC.
:::

### Document

A `.csv`, `.tsv` or `.json` file from the Wagtail document library. The file needs a header row, and is parsed on the server with the same rules as pasted text. The parsed rows are cached in Django's cache, keyed on the document's file hash, so they are only parsed again when the file changes.

The rows are written into the page, so anyone who can see the page can read the data, whatever the document's collection permissions are.

### URL

A URL that the browser loads the data from, or the server when server-side rendering is on. It can be:

- a path on your site, such as `/media/data.csv`;
- an `http` or `https` URL on a host in `ALLOWED_DATA_HOSTS`.

The **Format** choice sets the data format (CSV, TSV or JSON). If it's left as **Detect from the URL**, the format comes from the URL's file extension (`.csv`, `.tsv` or `.json`). This matters for raw Vega specs, which otherwise read every URL as JSON. For URLs without one of those extensions, such as an API endpoint, choose the format.

URL data isn't included in the fallback data table.

## Rendering outside a page

Chart blocks render like other blocks:

```python
html = block.render(value, context={"request": request})
```

Without a `request` in the context, each chart outputs a small loader script instead of the library scripts, and the loader makes sure the libraries load only once per page. In a Wagtail page template, `{% include_block %}` passes the page's context, including `request`, on to the block.

In the Wagtail API, chart blocks appear as the final spec plus everything needed to render it, not the editor's raw input. See [](frontend.md#the-wagtail-api).
