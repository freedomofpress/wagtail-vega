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
- A code editor (CodeMirror 6) for specs, JSON fields and pasted data, which underlines JSON syntax errors, spec schema and data host errors (validated live on the server), errors from a failed save, and ragged rows in pasted data. Available as the `wagtail_vega.widgets.CodeEditor` widget.
- A keyboard-accessible chart builder: a **Build chart** button on the spec field opens a lightbox with the chart's data, native form controls for the chart type, encodings and facets, suggestions from the data's columns, and a live preview in the chart's theme. It writes a Vega-Lite v6 spec that refers to the dataset by name, and opens existing single-view charts, keeping whatever it doesn't edit. `SpecBlock(builder=False)` leaves it out. It replaces the Vega Voyager integration, which was removed before release along with its vendored bundle (2.6 MB) and its `voyager=` option.
- Supports Wagtail 7.4 LTS and newer.
- Documentation, built with Sphinx.
