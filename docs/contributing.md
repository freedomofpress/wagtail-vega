# Testing and contributing

The code is on [GitHub](https://github.com/freedomofpress/wagtail-vega). Issues and pull requests are welcome.

## Setting up

```console
$ python -m venv .venv
$ .venv/bin/pip install -e ".[dev,docs]"
$ .venv/bin/python -m playwright install chromium
```

Instead of installing Playwright's Chromium, you can use an installed Chrome by passing `--browser-channel chrome` to pytest.

## Running the tests

```console
$ .venv/bin/pytest            # Python, admin and browser tests
$ npm test                    # JavaScript unit tests
$ .venv/bin/ruff check . && .venv/bin/ruff format --check .
```

| Path | What it covers |
| --- | --- |
| `tests/test_*.py` | Unit tests: spec handling, validation, themes, data parsing, blocks and SSR. |
| `tests/test_admin.py` | Creating, validating and previewing chart pages through the Wagtail admin. |
| `tests/test_editor.py` | The code editor widget and its telepath adapters, and the live validation endpoint. |
| `tests/e2e/` | Playwright browser tests: the dataset editor and the code editors, and chart rendering with themes, dark mode, a strict CSP, no JavaScript and URL blocking. Marked `e2e`. |
| `tests/js/` | Unit tests for the browser scripts: data parsing and type detection, JSON error locations and JSON path mapping, and security helpers. They use `node:test` and need Node 20 or newer, but no npm packages. |

To skip the browser tests, run `pytest -m "not e2e"`. The SSR tests are skipped if vl-convert isn't installed.

### The test matrix

CI runs the Python tests, browser tests included, on:

- Wagtail 7.4 with Django 5.2 (Python 3.10) and Django 6.0 (Python 3.13);
- Wagtail 8.0 with Django 6.0 (Python 3.13);
- Wagtail 8.1 with Django 6.1 (Python 3.14);
- Wagtail's nightly build (Python 3.14), as a non-blocking job.

To run the same matrix locally, use [tox](https://tox.wiki/). You need the Python versions installed.

```console
$ tox                                       # everything
$ tox -e py310-wagtail74-django52 -- --browser-channel chrome
$ tox -e lint,js
```

## The sandbox site

The test project in `tests/` doubles as a sandbox for trying charts out. `tests/testapp/models.py` has a `ChartPage` with both a `ChartBlock` and a database-backed `DonationsChartBlock`, and `tests/settings.py` has a full `WAGTAIL_VEGA` configuration.

```console
$ .venv/bin/python manage.py migrate
$ .venv/bin/python manage.py seed_sandbox
$ .venv/bin/python manage.py runserver
```

Open <http://localhost:8000> for the example charts, and <http://localhost:8000/admin/> to edit them. Log in as `admin` with the password `admin`.

These environment variables change the sandbox's behaviour:

`WAGTAIL_VEGA_CSP_SAFE=1`
: Turns on `CSP_SAFE`, and sends a strict Content Security Policy on frontend pages.

`WAGTAIL_VEGA_SSR=1`
: Turns on server-side rendering.

`WAGTAIL_VEGA_SANDBOX_AUTOLOGIN=1`
: Logs every request in as the sandbox superuser, so headless browsers can screenshot the admin. Never use it outside the sandbox.

## Building the documentation

The documentation is written in Markdown, with [MyST](https://myst-parser.readthedocs.io/), and built with [Sphinx](https://www.sphinx-doc.org/) and the [Furo](https://pradyunsg.me/furo/) theme.

```console
$ .venv/bin/sphinx-build -W --keep-going -b html docs docs/_build/html
```

Then open `docs/_build/html/index.html`. Warnings are errors, as in CI. To check external links:

```console
$ .venv/bin/sphinx-build -b linkcheck docs docs/_build/linkcheck
```

The API reference imports `wagtail_vega`, so `docs/conf.py` sets up Django with the test project's settings.

Pull requests get a preview build on Read the Docs, configured in `.readthedocs.yaml`.

## Updating the vendored libraries

Vega, Vega-Lite, vega-embed, vega-interpreter and the Vega and Vega-Lite JSON schemas are vendored into the package. To update them, change the versions in `scripts/vendor.py` and run it:

```console
$ python scripts/vendor.py
```

It downloads each package from npm, checks it against npm's integrity hash, and writes the files into `wagtail_vega/static/wagtail_vega/vendor/` and `wagtail_vega/schemas/`. The versions are recorded in `vendor/VERSIONS.json`. Run the full test suite afterwards, including the browser tests.

### CodeMirror

The admin's code editor uses [CodeMirror 6](https://codemirror.net/), which ships as ES modules split over many packages. They're bundled with [esbuild](https://esbuild.github.io/) into one script, `wagtail_vega/static/wagtail_vega/admin/vendor/codemirror.js`, which is committed, so installing wagtail-vega doesn't need Node.

- The packages and esbuild are pinned to exact versions in `package.json` and `package-lock.json`. `npm ci` checks each one against the lockfile's integrity hash.
- `scripts/codemirror/entry.mjs` lists what's bundled. Export only what `code-editor.js` uses, to keep the bundle small.
- `scripts/build-codemirror.mjs` writes the bundle, `codemirror.LICENSE` with the licence of every bundled package, and `codemirror.VERSIONS.json`.
- The build is deterministic. CI runs `npm ci && npm run build` and fails if the result differs from what's committed.

To update CodeMirror, change the versions in `package.json`, then:

```console
$ npm install
$ npm run build
```

Run the full test suite afterwards, including the browser tests, and look at the editor in the sandbox in both light and dark mode.

## Keeping things in sync

Some logic exists in both Python and JavaScript, and must be changed in both places:

- Pasted data detection, parsing and type inference: `wagtail_vega/data.py` and `static/wagtail_vega/admin/data-format.js`.
- The `path: message` format of spec errors: `SpecProblem` in `wagtail_vega/validation.py`, which `static/wagtail_vega/admin/json-source.js` (`splitMessage`) parses to highlight errors after a failed save.
- Host allowlist matching: `wagtail_vega/spec.py` (`host_allowed`) and `static/wagtail_vega/wagtail-vega.js` (`hostAllowed`).
- `var()` resolution: `wagtail_vega/themes.py` and `static/wagtail_vega/wagtail-vega.js`.

When you change behaviour, update the documentation in `docs/` and add an entry to {doc}`changelog`.
