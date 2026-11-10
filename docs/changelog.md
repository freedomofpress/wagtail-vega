# Changelog

All notable changes to wagtail-vega are listed here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.1.0 (unreleased)

First release.

- `ChartBlock`, for Vega and Vega-Lite charts with named datasets that editors paste, upload as documents or load from URLs.
- `BaseChartBlock`, for charts with data supplied from code.
- Custom dataset source types, for data that editors choose per dataset from your own database, next to Paste / Document / URL (#34):
  - `DatasetBlock.source_fields`, `clean_source()`, `get_source_dataset()` and `field_order`, and the `SOURCE_CHOICES` list; `SOURCE_FIELDS` is kept for compatibility. System checks (`wagtail_vega.E004`–`E006`) catch sources and fields that don't match.
  - The admin form shows and hides a new source's fields with no extra script, and `DatasetBlock.source_rows_urls` with the `SourceRowsView` admin view gives it a live summary and chart editor previews.
  - In the browser: `wagtailVegaAdmin.registerSource()`, `sources.readFields()`, `dataFormat.summariseRows()` and `renderSummary()`, and the `DatasetBlockDefinition` class. `DatasetBlockAdapter.extra_js` and `extra_css` load a subclass's own scripts in order.
  - The chart editor never reads the pasted data of a dataset whose source isn't Paste; a source it can't load is listed with a note.
- Themes, with dark mode and CSS custom properties.
- Data host allowlist, CSP-safe mode and optional server-side rendering.
- `wagtail-vega:rendered` and `wagtail-vega:error` events; data that fails to load is reported as an error.
- Translatable text throughout: the chart template, the chart editor (from Python), and the admin scripts' messages (through Django's JavaScript catalogue).
- `get_api_representation()`, so Wagtail's API returns renderable charts.
- System checks for theme settings and `Meta.theme`.
- `dark_fallbacks` in themes, for CSS variables in dark mode where the page's CSS isn't available, such as the admin's chart previews.
- The data host allowlist includes the site's own hostnames, and checks URLs the way browsers parse them.
- A code editor (CodeMirror 6) for specs, JSON fields and pasted data, which underlines JSON syntax errors, spec schema and data host errors (validated live on the server), errors from a failed save, and ragged rows in pasted data. Available as the `wagtail_vega.widgets.CodeEditor` widget.
- A keyboard-accessible chart editor. The spec field shows the chart, a list of the spec's problems, and an **Edit chart** button, rather than JSON. The button opens one editor in a lightbox, with **Visual** and **Code** tabs and a live preview in the chart's theme, all on the same spec:
  - **Visual**: native form controls for the chart type, encodings and facets, with suggestions from the data's columns. They write a Vega-Lite v6 spec that refers to the dataset by name, and open existing single-view charts, keeping whatever they don't edit.
  - **Code**: the code editor, for any Vega or Vega-Lite spec. Specs the settings can't show (Vega, layers…) are edited and previewed here.
  - Every change goes into the field as it's made, so Wagtail's autosave saves it. There's no "use" or "cancel" step: Close and Esc just close, and **Undo changes since opening** puts the spec back. Opening the editor never changes the spec.
  - `SpecBlock(builder=False)` leaves it out and shows the code editor inline.
- [Vega Voyager](https://github.com/vega/voyager) as the **Visual** tab's default mode, next to the settings, now called **Simple** (#36). A switch chooses between them; `WAGTAIL_VEGA["VISUAL_EDITOR"]` sets the default (`"voyager"` or `"simple"`), the browser remembers the editor's last choice, and narrow screens open in Simple.
  - Voyager runs in a sandboxed iframe on an admin-only page, with no network access. It's vendored with npm (about 2.6 MB, loaded only when Voyager is first shown).
  - It gets its data like the settings: pasted data, documents, URLs and custom sources, and the same **Dataset** picker.
  - Its charts are converted to Vega-Lite v6 that loads the dataset by name, and written to the field as they change, so Wagtail autosaves them. Opening a chart in Voyager never changes it: only a change the editor makes there is written.
  - Before a chart opens in Voyager, the editor lists what Voyager would drop, such as grouped bars (shown stacked), params and selections, or axis settings, and suggests Simple or Code. Charts Voyager can't open, such as Vega specs and layers, aren't opened.
  - The Voyager mode notes that it needs a mouse, and offers Simple.
- Editor and reader experience:
  - A spec that loads a dataset the chart doesn't have is an error on save, and underlined as you type.
  - Collapsed chart blocks are labelled with the spec's title, caption or description.
  - A new chart's spec field is empty, with an example spec as its placeholder, rather than `null`; the pasted data field has an example too.
  - Clearer labels and help text for **Data**, **Pasted data**, **Spec**, **Description** and **Caption**. The chart editor's button is labelled **Edit chart**. Because StreamField migrations record help text and labels, `makemigrations` creates a migration for models that use `ChartBlock`; it doesn't change any data.
  - Screen readers announce the **Source** toggle as a named radio group, and the pasted data summary as part of the editor's description.
  - Readers see a message when a chart can't be displayed, and the no-JavaScript message points to the data table. Space is kept for charts while they load. The data table right-aligns numbers, scrolls sideways on narrow screens, and closed tables are left out when printing.
- Supports Wagtail 7.4 LTS and newer.
- Documentation, built with Sphinx.
