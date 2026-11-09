# The editor experience

This page describes what editors see when they work with a `ChartBlock`, so you can explain it to them, or write your own editor guide. For the rules behind each field, see {doc}`adding-charts`.

## Adding a chart

Editors add a **Chart** block from the StreamField's block menu. Its fields are shown in this order:

1. **Data**: a list of datasets. Each has a **Name**, which defaults to `source`, and a **Source** toggle.
2. **Spec**: a JSON text area for the Vega or Vega-Lite spec.
3. **Description**: a short description of the chart, for people using screen readers. It isn't shown on the page.
4. **Caption**: shown under the chart.
5. **Theme**: a dropdown of the site's themes. The blank option is labelled with the default theme, e.g. "Site default (House style)".

A typical workflow is:

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

  It warns about rows with the wrong number of values and about invalid JSON, before the page is saved.

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

## Developer-defined charts

Blocks based on {py:class}`~wagtail_vega.blocks.BaseChartBlock` (see {doc}`custom-data`) show only **Spec**, **Description** and **Caption**, plus any fields you add. Tell editors which dataset names the block provides, and what columns they have, for example in the block's `help_text`.

## Code editor

% TODO: Document the CodeMirror-based code editor for the spec and paste
% fields (inline error highlighting) once it is merged.

:::{note}
This section is a placeholder. It will describe the code editor for the spec and paste fields, with inline error highlighting.
:::

## Visual chart builder (Vega Voyager)

% TODO: Document the Vega Voyager button on the spec field, which opens a
% visual chart builder in a lightbox, once it is merged.

:::{note}
This section is a placeholder. It will describe the visual chart builder, which opens from the spec field.
:::
