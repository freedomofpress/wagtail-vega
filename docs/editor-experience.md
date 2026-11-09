# The editor experience

This page describes what editors see when they work with a `ChartBlock`, so you can explain it to them, or write your own editor guide. For the rules behind each field, see {doc}`adding-charts`.

## Adding a chart

Editors add a **Chart** block from the StreamField's block menu. Its fields are shown in this order:

1. **Data**: a list of datasets. A new chart starts with one, named `source`, ready for pasting. Each has a **Name** and a **Source** toggle.
2. **Spec**: the chart, drawn from its Vega or Vega-Lite spec, with an **Edit chart** button that opens the [chart editor](#chart-editor). See [the spec field](#the-spec-field).
3. **Description**: what the chart shows, and what readers should take from it, for people using screen readers. It isn't shown on the page.
4. **Caption**: shown under the chart, e.g. a title, the source of the data, or notes.
5. **Theme**: a dropdown of the site's themes. The blank option is labelled with the default theme, e.g. "Site default (House style)".

When a chart block is collapsed, its header shows the spec's `title`, or else its caption or description, so editors can tell charts apart.

For common charts, the quickest way is:

1. Copy the data from a spreadsheet and paste it into the dataset.
2. Choose **Edit chart**, and pick the chart type and fields in the [chart editor](#chart-editor)'s **Visual** tab.
3. Close the editor. The field shows the chart.

For anything the settings don't make, a typical workflow is:

1. Find a chart in the [Vega-Lite examples](https://vega.github.io/vega-lite/examples/) that looks like the one you want.
2. Copy the data from a spreadsheet and paste it into the dataset.
3. Choose **Edit chart**, paste the example's spec into the **Code** tab, and replace its `data` with `{"name": "source"}`.
4. Adjust the spec, watching the preview next to it.

Chart blocks work in Wagtail's live preview, so editors can see the chart as they edit.

## Adding data

The **Source** toggle has three options. Only the inputs for the selected option are shown.

Paste
: Paste CSV, JSON or cells copied from a spreadsheet into **Pasted data**. The first row must be the column names. While it's empty, the box shows a short example. A summary under the box shows how the data was read, for example:

  `Tab-separated (e.g. copied from a spreadsheet) · 6 rows · quarter (text), requests (number)`

  It warns about rows with the wrong number of values and about invalid JSON, before the page is saved. The [code editor](#code-editor) also marks them in place.

Document
: Choose a `.csv`, `.tsv` or `.json` file from the document library. This suits data that's updated separately, or shared between charts.

URL
: Enter a path on the site, such as `/media/data.csv`, or a full URL on a host the site allows. Pick the format, or leave it to be detected from the URL.

Editors can add more than one dataset, as long as each has a different name, and refer to each by name in the spec.

Screen readers announce the toggle as a group of radio buttons named "Source", and the summary as part of the pasted data's description.

## Validation

When the page is saved, editors see an error if:

- the spec isn't valid JSON (the text they entered is kept, so they can fix it);
- the spec has no `$schema`, or doesn't match the Vega or Vega-Lite schema. The message points at the problem, e.g. `encoding.x.type: 'nominl' is not valid…`;
- the spec loads data from a host that isn't allowed;
- a dataset has no data for its selected source, or its data can't be read;
- a dataset name is invalid, or used twice in the same chart;
- the spec loads a dataset by name that the chart doesn't have, e.g. `"data": {"name": "sales"}` when the only dataset is called `source`. The message names the chart's datasets: `This chart has no dataset called "sales". Use one of its datasets (source), or add one under Data.`;
- a document isn't a `.csv`, `.tsv` or `.json` file;
- a URL isn't allowed.

The code editor shows the spec and pasted data problems as editors type, and the spec field lists the spec's, so most of these can be fixed before saving.

## Developer-defined charts

Blocks based on {py:class}`~wagtail_vega.blocks.BaseChartBlock` (see {doc}`custom-data`) show only **Spec**, **Description** and **Caption**, plus any fields you add. Tell editors which dataset names the block provides, and what columns they have, for example in the block's `help_text`.

## Code editor

The **Spec** field (in the chart editor's **Code** tab), the **Paste** field and any other `JSONBlock` are edited in a code editor ([CodeMirror 6](https://codemirror.net/)). While a spec is empty, its editor shows an example spec that loads the `source` dataset. It has line numbers, bracket matching, folding of objects and arrays, search (Ctrl+F, or Cmd+F on a Mac) and undo, and follows the admin's light or dark theme.

Problems are underlined where they are, with a marker in the gutter. Hovering over the underline shows the message:

JSON syntax errors
: Shown as you type, at the character where the JSON stops making sense, e.g. a trailing comma or a missing quote.

Spec errors
: Shortly after the editor stops typing, the spec is checked on the server with the same checks as saving: the Vega or Vega-Lite schema, and the data host allowlist. The problem is underlined at the part of the spec it's about. For example, in `"type": "nominl"` the value `"nominl"` is underlined, and a `url` on a host that isn't allowed is underlined too. The first problem, with its line number, is also shown under the editor.

Missing datasets
: In a {py:class}`~wagtail_vega.blocks.ChartBlock`, the name in each `"data": {"name": ...}` is underlined if the chart has no dataset with that name. This is checked again when a dataset is renamed, added or removed, and when the page is saved.

Errors from saving
: If a page can't be saved because of the spec, the errors are shown above the field as usual, listed in the spec field, and each one is also underlined in the spec, at the path its message starts with (e.g. `encoding.x.type`).

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

## The spec field

The **Spec** field doesn't show JSON. It shows:

- **The chart**, drawn from the spec as it is now, with the chart's data and theme, as in the [preview](#preview). It's redrawn when the spec, the data or the **Theme** changes. A field is drawn when it first scrolls into view, so long pages with many charts open quickly.
- **The spec's problems**, if any, as a list: JSON syntax errors, schema errors, data hosts that aren't allowed, datasets the chart doesn't have, and the errors from a save that failed. Each names its line in the spec, e.g. `Line 15: 'nominl' is not valid under any of the given schemas`.
- An **Edit chart** button, which opens the [chart editor](#chart-editor).

While the spec is empty, as in a new chart, a short prompt replaces the chart, and **Edit chart** is the field's main action. Once there's a spec, it becomes a secondary button.

The field's `<textarea>` is still in the form, hidden. It holds the spec that's saved, and the chart editor writes to it.

(chart-editor)=

## The chart editor

**Edit chart** opens the chart editor in a lightbox. It has two tabs, **Visual** and **Code**, and a live **Preview** next to them (below them on narrow screens). All three work on the same spec:

- A change in the **Visual** settings rewrites the spec in the **Code** tab, and redraws the preview.
- An edit in the **Code** tab updates the settings and the preview.

**Visual** is the tab shown first. No JSON is needed to make a chart there, and everything works with the keyboard.

The editor's text is translated with the rest of wagtail-vega: it comes from the server (`wagtail_vega/builder_strings.py`), in the admin user's language.

### Changes go straight into the page

There's no **Use** or **Save** step in the editor. Every change goes into the field as it's made: settings at once, and typing in the code after a short pause (or as soon as the code loses focus). So Wagtail's unsaved-changes warning and its autosave (Wagtail 7.4 and newer, see `WAGTAIL_AUTOSAVE_INTERVAL`) see the editor's changes like any other field's, with the editor still open.

Close
: **Close**, the close button and Esc close the editor. Nothing is asked and nothing is thrown away. Focus goes back to **Edit chart**, and the field's chart shows the changes.

Undo
: **Undo changes since opening** puts back the spec the editor opened with. In the **Code** tab, Ctrl+Z (Cmd+Z) undoes one edit at a time, including changes made with the settings.

Opening changes nothing
: Opening the editor, looking around and closing it never changes an existing spec. Opening it on an **empty** spec, as in a new chart, puts the first suggested chart in the page straight away, so what the editor sees is what's saved; **Undo changes since opening** empties the field again. Clearing the code by hand leaves it empty.

Invalid JSON
: While the code isn't valid JSON, the settings and the preview stay at the last valid spec, and say why. The text is still written to the field, so nothing is lost. Wagtail's autosave refuses to save a form with errors and its indicator says so ("There are validation errors, click save to highlight them."); it saves again once the spec is fixed. Saving the page with invalid JSON shows the usual error, and keeps the text.

### Visual

Data
: The settings get the data from the form as it is now, whether or not the page has been saved. Pasted data is read exactly as it will be for the chart, documents are read on the server, and URL datasets are fetched by the browser, from allowed hosts only. If the chart has several datasets, a **Dataset** menu picks one. Datasets with no data yet are left out. Datasets a developer adds in code (`ChartBlock.extra_dataset_names`) are listed but can't be chosen, because the admin has no rows for them; a chart that uses one opens with the first dataset from the form, and says so.

Suggested charts
: A list of starting points that suit the data's columns, such as "Bars: requests by quarter", "Grouped bars: requests by quarter and agency" or "Line: temperature over time". An empty spec starts from the first suggestion.

Chart
: The **Chart type** (bar, line, area, point, circle, square, tick, arc for pies and donuts, rectangle for heatmaps, and rule). For bars and areas that share a position, whether they're stacked, stacked to 100%, side by side (grouped bars), centred (streamgraphs) or overlapping. Lines and areas can show a point for each value, arcs can be a donut, and any chart can show values in a tooltip.

Encodings
: For each of **X axis**, **Y axis**, **Colour**, **Size** (points), **Slice size** (arcs), **Columns** and **Rows** (a small chart for each value): the **Field**, or **Count of rows**; its **Type** (number, category, ordered category, or date or time), guessed from the data with the same rules as the summary under pasted data; how to **Combine rows** (sum, mean, median, minimum, maximum, count or count of distinct values); **Bins** for numbers; a **Time unit** for dates; the **Sort** order; and the axis, legend or heading title. **Swap X and Y** turns a chart on its side.

Title and size
: The chart's title, and its width: the width of the page (the default), automatic or fixed. Charts split into rows or columns can't fill the page width, so choosing a row or column field sets the width to automatic. The height can be set in pixels.

The settings write a Vega-Lite v6 spec that loads the dataset by name (`"data": {"name": "source"}`, never a copy of the data). Dates without times, such as `2024-01-31`, are grouped with UTC time units (`utcyearmonth`), so that they fall in the right month in every time zone.

### Code

The **Code** tab is the field's [code editor](#code-editor), with its checks, its undo history and any errors from a failed save. The tab is marked when the code has errors. It accepts any Vega or Vega-Lite spec, including ones the settings can't show.

### Preview

The preview is drawn with the same libraries as the site, in the chart's theme (the one chosen in the **Theme** field, or the site default). If the theme has dark mode settings, a **Colours** menu shows the chart in light or dark mode; it starts in the admin's own colour scheme. Your site's stylesheet isn't loaded in the admin, so CSS custom properties in the theme (`var(--brand)`) use the theme's `fallbacks`, and its `dark_fallbacks` in dark mode. Vega specs are previewed too. Datasets with more than 5,000 rows are previewed from their first 5,000 rows, and the editor says so; the spec always loads the whole dataset.

### Opening an existing chart

If the field already holds a chart, the editor opens it, so editors can change it rather than start again:

- A single-view Vega-Lite chart opens in the settings with its chart type, fields and settings. **Anything the settings don't edit is kept as it is**: for example `config`, `transform`, `params`, a mark's `cornerRadius`, an axis `format`, a legend's position, or a `tooltip` channel. The editor lists these under **From the current spec**. A setting the editor can show but not in that form, such as a custom sort order, shows as **Custom** in its menu, and is kept until the editor picks something else.
- Settings kept for a field belong to that field: if the editor changes the X axis to another field, the old field's axis settings are removed, and the editor lists them under **Your changes remove these parts of the spec**. Changing back brings them back. Settings for a mark type work the same way.
- Anything else, such as a Vega spec, layers, concatenated or repeated views, a mark type the settings don't offer, or data loaded from a URL in the spec, can't be shown in the settings. The **Visual** tab says why, and offers to **Start a new chart** from the data instead; the **Code** tab and the preview keep working. The spec only changes if the editor edits the code or starts a new chart.

On charts whose data comes from code ({py:class}`~wagtail_vega.blocks.BaseChartBlock` subclasses without a `data` field), the settings aren't available, because there's no data in the form to build from: the spec is edited in the **Code** tab. Developers can leave the chart editor out, and show the code editor inline, with `SpecBlock(builder=False)`.

### Keyboard and screen readers

The editor is a modal dialog: focus moves into it when it opens, Tab and Shift+Tab move through its controls in order, and Esc closes it. The **Visual** and **Code** tabs are a tab list: the arrow keys, Home and End move between them. Every setting is a labelled native form control (menus, checkboxes, text and number fields, and buttons), and each encoding is a labelled group. Status messages, such as "Swapped the X and Y axes.", are announced. The preview is an SVG with Vega-Lite's own description of the chart.

:::{admonition} Limitations
The settings make one view at a time: a single mark with its encodings and facets. Layers, concatenated views, selections and transforms are written in the code (and kept when the chart is opened again). A theme set in a block's `Meta.theme` isn't shown in the previews, which use the **Theme** field or the site default. The whole dataset is still downloaded to read its columns.
:::

For what the chart editor needs from the admin, see {ref}`builder-security`.
