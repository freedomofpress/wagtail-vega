# The editor experience

This page describes what editors see when they work with a `ChartBlock`, so you can explain it to them, or write your own editor guide. For the rules behind each field, see {doc}`adding-charts`.

## Adding a chart

Editors add a **Chart** block from the StreamField's block menu. Its fields are shown in this order:

1. **Data**: a list of datasets. Each has a **Name**, which defaults to `source`, and a **Source** toggle.
2. **Spec**: the Vega or Vega-Lite spec, in a [code editor](#code-editor) that underlines problems as you type.
3. **Description**: a short description of the chart, for people using screen readers. It isn't shown on the page.
4. **Caption**: shown under the chart.
5. **Theme**: a dropdown of the site's themes. The blank option is labelled with the default theme, e.g. "Site default (House style)".

For common charts, the quickest way is:

1. Copy the data from a spreadsheet and paste it into the dataset.
2. Choose **Build chart** above the spec, and make the chart with the [chart builder](#chart-builder).
3. Preview the page.

For anything the builder doesn't make, a typical workflow is:

1. Find a chart in the [Vega-Lite examples](https://vega.github.io/vega-lite/examples/) that looks like the one you want.
2. Paste its spec into **Spec**, and replace its `data` with `{"name": "source"}`.
3. Copy the data from a spreadsheet and paste it into the dataset.
4. Preview the page, then adjust the spec.

Chart blocks work in Wagtail's live preview, so editors can see the chart as they edit.

## Adding data

The **Source** toggle has three options. Only the inputs for the selected option are shown.

Paste
: Paste CSV, JSON or cells copied from a spreadsheet. The first row must be the column names. A summary under the box shows how the data was read, for example:

  `Tab-separated (e.g. copied from a spreadsheet) · 6 rows · quarter (text), requests (number)`

  It warns about rows with the wrong number of values and about invalid JSON, before the page is saved. The [code editor](#code-editor) also marks them in place.

Document
: Choose a `.csv`, `.tsv` or `.json` file from the document library. This suits data that's updated separately, or shared between charts.

URL
: Enter a path on the site, such as `/media/data.csv`, or a full URL on a host the site allows. Pick the format, or leave it to be detected from the URL.

Editors can add more than one dataset, as long as each has a different name, and refer to each by name in the spec.

## Validation

When the page is saved, editors see an error if:

- the spec isn't valid JSON (the text they entered is kept, so they can fix it);
- the spec has no `$schema`, or doesn't match the Vega or Vega-Lite schema. The message points at the problem, e.g. `encoding.x.type: 'nominl' is not valid…`;
- the spec loads data from a host that isn't allowed;
- a dataset has no data for its selected source, or its data can't be read;
- a dataset name is invalid, or used twice in the same chart;
- a document isn't a `.csv`, `.tsv` or `.json` file;
- a URL isn't allowed.

The code editor shows the spec and pasted data problems as editors type, so most of these can be fixed before saving.

## Developer-defined charts

Blocks based on {py:class}`~wagtail_vega.blocks.BaseChartBlock` (see {doc}`custom-data`) show only **Spec**, **Description** and **Caption**, plus any fields you add. Tell editors which dataset names the block provides, and what columns they have, for example in the block's `help_text`.

## Code editor

The **Spec** field, the **Paste** field and any other `JSONBlock` are edited in a code editor ([CodeMirror 6](https://codemirror.net/)). It has line numbers, bracket matching, folding of objects and arrays, search (Ctrl+F, or Cmd+F on a Mac) and undo, and follows the admin's light or dark theme.

Problems are underlined where they are, with a marker in the gutter. Hovering over the underline shows the message:

JSON syntax errors
: Shown as you type, at the character where the JSON stops making sense, e.g. a trailing comma or a missing quote.

Spec errors
: Shortly after the editor stops typing, the spec is checked on the server with the same checks as saving: the Vega or Vega-Lite schema, and the data host allowlist. The problem is underlined at the part of the spec it's about. For example, in `"type": "nominl"` the value `"nominl"` is underlined, and a `url` on a host that isn't allowed is underlined too. The first problem, with its line number, is also shown under the editor.

Errors from saving
: If a page can't be saved because of the spec, the errors are shown above the field as usual, and each one is also underlined in the spec, at the path its message starts with (e.g. `encoding.x.type`).

Pasted data
: Lines don't wrap, so columns line up, and tabs are shown as arrows, so a spreadsheet paste is easy to check. JSON data is highlighted. Rows with the wrong number of values are marked on their line, and JSON errors where they are.

### Keyboard

The editor doesn't capture the Tab key: Tab and Shift+Tab move to the next and previous field, as in any other field. To indent, use Ctrl+] (Cmd+] on a Mac); to outdent, Ctrl+[ (Cmd+[).

| Key | Action |
| --- | --- |
| F8 | Go to the next problem |
| Ctrl+Shift+M (Cmd+Shift+M) | List all the problems in a panel |
| Ctrl+F (Cmd+F) | Search and replace |
| Ctrl+Z / Ctrl+Shift+Z | Undo / redo |

Screen readers announce the field's label and help text, and the first problem under the editor is a live region.

## Chart builder

Above the spec's code editor is a **Build chart** button. It opens the chart builder in a lightbox, with the chart's data. Editors pick a chart type and the fields to show with ordinary form controls, see a preview as they go, and choose **Use this chart** to put the chart's spec in the field. No JSON is needed, and everything works with the keyboard.

Data
: The builder gets the data from the form as it is now, whether or not the page has been saved. Pasted data is read exactly as it will be for the chart, documents are read on the server, and URL datasets are fetched by the browser, from allowed hosts only. If the chart has several datasets, a **Dataset** menu picks one. Datasets with no data yet are left out.

Suggested charts
: A list of starting points that suit the data's columns, such as "Bars: requests by quarter", "Grouped bars: requests by quarter and agency" or "Line: temperature over time". A new chart starts from the first suggestion.

Chart
: The **Chart type** (bar, line, area, point, circle, square, tick, arc for pies and donuts, rectangle for heatmaps, and rule). For bars and areas that share a position, whether they're stacked, stacked to 100%, side by side (grouped bars), centred (streamgraphs) or overlapping. Lines and areas can show a point for each value, arcs can be a donut, and any chart can show values in a tooltip.

Encodings
: For each of **X axis**, **Y axis**, **Colour**, **Size** (points), **Slice size** (arcs), **Columns** and **Rows** (a small chart for each value): the **Field**, or **Count of rows**; its **Type** (number, category, ordered category, or date or time), guessed from the data with the same rules as the summary under pasted data; how to **Combine rows** (sum, mean, median, minimum, maximum, count or count of distinct values); **Bins** for numbers; a **Time unit** for dates; the **Sort** order; and the axis, legend or heading title. **Swap X and Y** turns a chart on its side.

Title and size
: The chart's title, and its width: the width of the page (the default), automatic or fixed. Charts split into rows or columns can't fill the page width, so choosing a row or column field sets the width to automatic. The height can be set in pixels.

Preview
: The preview is drawn with the same libraries as the site, in the chart's theme (the one chosen in the **Theme** field, or the site default). If the theme has dark mode settings, a **Colours** menu shows the chart in light or dark mode. Your site's stylesheet isn't loaded in the admin, so CSS custom properties in the theme (`var(--brand)`) use the theme's `fallbacks`. The spec is shown under the preview as it's built.

Using the chart
: **Use this chart** writes a Vega-Lite v6 spec that loads the dataset by name (`"data": {"name": "source"}`, never a copy of the data), after checking it with the same checks as saving. If the field already has a spec, the lightbox asks before replacing it. The change goes into the code editor as one edit, so Ctrl+Z (Cmd+Z) undoes it. Dates without times, such as `2024-01-31`, are grouped with UTC time units (`utcyearmonth`), so that they fall in the right month in every time zone.

Cancelling
: **Cancel**, the close button and Esc close the lightbox without changing the field. Focus goes back to the **Build chart** button.

### Opening an existing chart

If the field already holds a chart, the builder opens it, so editors can change it rather than start again:

- A single-view Vega-Lite chart opens with its chart type, fields and settings. **Anything the builder doesn't edit is kept as it is**: for example `config`, `transform`, `params`, a mark's `cornerRadius`, an axis `format`, a legend's position, or a `tooltip` channel. The builder lists these under **From the current spec**. A setting the builder can show but not in that form, such as a custom sort order, shows as **Custom** in its menu, and is kept until the editor picks something else. Choosing **Use this chart** without changing anything leaves the spec exactly as it was.
- Settings kept for a field belong to that field: if the editor changes the X axis to another field, the old field's axis settings are removed, and the builder lists them under **Your changes remove these parts of the spec**. Changing back brings them back. Settings for a mark type work the same way.
- Anything else, such as a Vega spec, layers, concatenated or repeated views, a mark type the builder doesn't offer, or data loaded from a URL in the spec, can't be opened. The builder says why, and offers to **Start a new chart** from the data instead. The spec in the field is only replaced if the editor then chooses **Use this chart** and confirms.

### Keyboard and screen readers

The builder is a modal dialog: focus moves into it when it opens, Tab and Shift+Tab move through its controls in order, and Esc closes it. Every control is a labelled native form control (menus, checkboxes, text and number fields, and buttons), and each encoding is a labelled group. Status messages, such as "Opened the field's chart.", are announced, and problems that stop a chart being used are announced as alerts. The preview is an SVG with Vega-Lite's own description of the chart.

The button is disabled, with a note, on charts whose data comes from code ({py:class}`~wagtail_vega.blocks.BaseChartBlock` subclasses without a `data` field), because there's no data in the form to build from. Developers can leave the button out with `SpecBlock(builder=False)`.

:::{admonition} Limitations
The builder makes one view at a time: a single mark with its encodings and facets. Layers, concatenated views, selections and transforms are written in the spec by hand (and kept when the chart is opened again). A theme set in a block's `Meta.theme` isn't shown in the preview, which uses the **Theme** field or the site default. The whole dataset is loaded for the preview, so very large datasets can make it slow.
:::

For what the builder needs from the admin, see {ref}`builder-security`.
