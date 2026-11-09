# The editor experience

This page describes what editors see when they work with a `ChartBlock`, so you can explain it to them, or write your own editor guide. For the rules behind each field, see {doc}`adding-charts`.

## Adding a chart

Editors add a **Chart** block from the StreamField's block menu. Its fields are shown in this order:

1. **Data**: a list of datasets. A new chart starts with one, named `source`, ready for pasting. Each has a **Name** and a **Source** toggle.
2. **Spec**: the Vega or Vega-Lite spec, in a [code editor](#code-editor) that underlines problems as you type. While it's empty, it shows an example spec that loads the `source` dataset.
3. **Description**: what the chart shows, and what readers should take from it, for people using screen readers. It isn't shown on the page.
4. **Caption**: shown under the chart, e.g. a title, the source of the data, or notes.
5. **Theme**: a dropdown of the site's themes. The blank option is labelled with the default theme, e.g. "Site default (House style)".

When a chart block is collapsed, its header shows the spec's `title`, or else its caption or description, so editors can tell charts apart.

A typical workflow is:

1. Find a chart in the [Vega-Lite examples](https://vega.github.io/vega-lite/examples/) that looks like the one you want.
2. Paste its spec into **Spec**, and replace its `data` with `{"name": "source"}`.
3. Copy the data from a spreadsheet and paste it into the dataset.
4. Preview the page, then adjust the spec.

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

Missing datasets
: In a {py:class}`~wagtail_vega.blocks.ChartBlock`, the name in each `"data": {"name": ...}` is underlined if the chart has no dataset with that name. This is checked again when a dataset is renamed, added or removed, and when the page is saved.

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

## Visual chart builder (Vega Voyager)

Above the spec's code editor is a **Build chart from data** button. It opens [Vega Voyager](https://github.com/vega/voyager) in a lightbox, loaded with the chart's data. Editors build a chart by dragging fields onto encoding shelves (x, y, colour…), or by picking one of the views Voyager suggests, and then choose **Use this chart** to put its spec in the field.

Data
: Voyager gets the data from the form as it is now, whether or not the page has been saved. Pasted data is read exactly as it will be for the chart, documents are read on the server, and URL datasets are fetched by the browser, from allowed hosts only. If the chart has several datasets, a **Dataset** menu picks one. Datasets with no data yet are left out.

Opening the current chart
: If the field holds a single-view Vega-Lite chart, Voyager opens with its mark and fields. Anything else, such as a Vega spec, layers or concatenated views, starts from the data, and a note says so. Voyager only understands Vega-Lite 2, so parts of the chart it doesn't know are dropped when it opens. For example, grouped bars (`xOffset`) open as stacked bars. If the editor then chooses **Use this chart**, those parts are gone from the spec; the confirmation step's **Keep editing** button, or undo in the code editor, gets them back.

Using the chart
: **Use this chart** turns Voyager's chart into a Vega-Lite v6 spec that loads the dataset by name (`"data": {"name": "source"}`, never a copy of the data), and checks it with the same checks as saving. If the field already has a spec, the lightbox asks before replacing it. The title, description, width, height and `config` of the spec it replaces are kept. The change goes into the code editor as one edit, so Ctrl+Z (Cmd+Z) undoes it.

Cancelling
: **Cancel**, the close button and Esc close the lightbox without changing the field. Focus goes back to the button.

The button is disabled, with a note, on charts whose data comes from code ({py:class}`~wagtail_vega.blocks.BaseChartBlock` subclasses without a `data` field), because there's no data in the form to give Voyager. Developers can leave the button out with `SpecBlock(voyager=False)`.

:::{admonition} Limitations
Voyager is no longer maintained; its last release was in 2018. It builds single-view charts from the features Vega-Lite 2 had, so finishing touches (titles, axis formats, tooltips…) are made in the spec afterwards. Building a chart in it needs a mouse, since it relies on drag and drop, and it has no dark theme. The lightbox around it works with the keyboard and screen readers. Very large datasets are sent to it whole, which can make it slow.
:::

For how Voyager is isolated from the admin, see {ref}`voyager-security`.
