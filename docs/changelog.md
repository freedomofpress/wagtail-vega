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
- Supports Wagtail 7.4 LTS and newer.
- Documentation, built with Sphinx.
