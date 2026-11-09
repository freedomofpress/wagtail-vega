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
- `dark_fallbacks` in themes, for CSS variables in dark mode where the page's CSS isn't available, such as the admin's chart previews.
- The data host allowlist includes the site's own hostnames, and checks URLs the way browsers parse them.
- A code editor (CodeMirror 6) for specs, JSON fields and pasted data, which underlines JSON syntax errors, spec schema and data host errors (validated live on the server), errors from a failed save, and ragged rows in pasted data. Available as the `wagtail_vega.widgets.CodeEditor` widget.
- A keyboard-accessible chart editor. The spec field shows the chart, a list of the spec's problems, and an **Edit chart** button, rather than JSON. The button opens one editor in a lightbox, with **Visual** and **Code** tabs and a live preview in the chart's theme, all on the same spec:
  - **Visual**: native form controls for the chart type, encodings and facets, with suggestions from the data's columns. They write a Vega-Lite v6 spec that refers to the dataset by name, and open existing single-view charts, keeping whatever they don't edit.
  - **Code**: the code editor, for any Vega or Vega-Lite spec. Specs the settings can't show (Vega, layers…) are edited and previewed here.
  - Every change goes into the field as it's made, so Wagtail's autosave saves it. There's no "use" or "cancel" step: Close and Esc just close, and **Undo changes since opening** puts the spec back. Opening the editor never changes the spec.
  - `SpecBlock(builder=False)` leaves it out and shows the code editor inline. It replaces the Vega Voyager integration, which was removed before release along with its vendored bundle (2.6 MB) and its `voyager=` option.
- Editor and reader experience:
  - A spec that loads a dataset the chart doesn't have is an error on save, and underlined as you type.
  - Collapsed chart blocks are labelled with the spec's title, caption or description.
  - A new chart's spec field is empty, with an example spec as its placeholder, rather than `null`; the pasted data field has an example too.
  - Clearer labels and help text for **Data**, **Pasted data**, **Spec**, **Description** and **Caption**. The chart editor's button is labelled **Edit chart**. Because StreamField migrations record help text and labels, `makemigrations` creates a migration for models that use `ChartBlock`; it doesn't change any data.
  - Screen readers announce the **Source** toggle as a named radio group, and the pasted data summary as part of the editor's description.
  - Readers see a message when a chart can't be displayed, and the no-JavaScript message points to the data table. Space is kept for charts while they load. The data table right-aligns numbers, scrolls sideways on narrow screens, and closed tables are left out when printing.
- Supports Wagtail 7.4 LTS and newer.
- Documentation, built with Sphinx.
