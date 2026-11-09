# Changelog

All notable changes to wagtail-vega are listed here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.1.0 (unreleased)

First release.

- `ChartBlock`, for Vega and Vega-Lite charts with named datasets that editors paste, upload as documents or load from URLs.
- `BaseChartBlock`, for charts with data supplied from code.
- Themes, with dark mode and CSS custom properties.
- Data host allowlist, CSP-safe mode and optional server-side rendering.
- `wagtail-vega:rendered` and `wagtail-vega:error` events; data that fails to load is reported as an error.
- Translatable chart template text.
- `get_api_representation()`, so Wagtail's API returns renderable charts.
- System checks for theme settings and `Meta.theme`.
- The data host allowlist includes the site's own hostnames, and checks URLs the way browsers parse them.
- A code editor (CodeMirror 6) for specs, JSON fields and pasted data, which underlines JSON syntax errors, spec schema and data host errors (validated live on the server), errors from a failed save, and ragged rows in pasted data. Available as the `wagtail_vega.widgets.CodeEditor` widget.
- A keyboard-accessible chart builder: a **Build chart from data** button on the spec field opens a lightbox with the chart's data, native form controls for the chart type, encodings and facets, suggestions from the data's columns, and a live preview in the chart's theme. It writes a Vega-Lite v6 spec that refers to the dataset by name, and opens existing single-view charts, keeping whatever it doesn't edit. `SpecBlock(builder=False)` leaves it out. It replaces the Vega Voyager integration, which was removed before release along with its vendored bundle (2.6 MB) and its `voyager=` option.
- Editor and reader experience:
  - A spec that loads a dataset the chart doesn't have is an error on save, and underlined as you type.
  - Collapsed chart blocks are labelled with the spec's title, caption or description.
  - A new chart's spec field is empty, with an example spec as its placeholder, rather than `null`; the pasted data field has an example too.
  - Clearer labels and help text for **Data**, **Pasted data**, **Spec**, **Description** and **Caption**. The chart builder button is labelled **Build chart from data**. Because StreamField migrations record help text and labels, `makemigrations` creates a migration for models that use `ChartBlock`; it doesn't change any data.
  - Screen readers announce the **Source** toggle as a named radio group, and the pasted data summary as part of the editor's description.
  - Readers see a message when a chart can't be displayed, and the no-JavaScript message points to the data table. Space is kept for charts while they load. The data table right-aligns numbers, scrolls sideways on narrow screens, and closed tables are left out when printing.
- Supports Wagtail 7.4 LTS and newer.
- Documentation, built with Sphinx.
