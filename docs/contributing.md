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
| `tests/test_chart_builder.py` | The spec field's markup and the chart editor's settings, the document-rows endpoint (permissions, parsing), and that the specs the builder writes pass validation. |
| `tests/test_static.py` | `collectstatic` with `ManifestStaticFilesStorage`, which fails on dangling source-map references. |
| `tests/e2e/` | Playwright browser tests: the dataset editor, the code editors, the spec field and chart editor (each common chart built with the keyboard only, saved and rendered; autosave; invalid JSON), and chart rendering with themes, dark mode, a strict CSP, no JavaScript and URL blocking. Marked `e2e`. |
| `tests/js/` | Unit tests for the browser scripts: data parsing and type detection, JSON error locations and JSON path mapping, the chart builder's specs (every common chart, and opening existing specs without losing anything; the cases are in `tests/js/fixtures/chart-specs.json`, which the Python tests also validate), and security helpers. They use `node:test` and need Node 20 or newer, but no npm packages. |

To skip the browser tests, run `pytest -m "not e2e"`. The SSR tests are skipped if vl-convert isn't installed.

Each browser test fails after 120 seconds ([pytest-timeout](https://pypi.org/project/pytest-timeout/), set in `tests/e2e/conftest.py`), so a test that hangs fails with its name rather than stalling the run. A test can set its own limit with `@pytest.mark.timeout(seconds)`. Run the browser tests with `-v` to see each test's name as it runs.

The browser tests run against Django's live server. With the in-memory SQLite database that CI uses, its threads share one database connection, so the test project's `SerialRequestsMiddleware` handles one request at a time, and tests that read the database while the page may still be making requests hold `tests.testapp.middleware.DATABASE_LOCK`. Wagtail's autosave is off in browser tests (`WAGTAIL_AUTOSAVE_INTERVAL = 0`) except in the tests for it.

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

Vega, Vega-Lite, vega-embed and the Vega and Vega-Lite JSON schemas are vendored into the package from npm. Their versions are pinned exactly in `package.json`, and `package-lock.json` records each tarball's integrity hash, which `npm ci` checks. To update them, change the versions in `package.json`, or merge a Dependabot pull request, then run:

```console
$ npm install --ignore-scripts
$ npm run vendor
```

`scripts/vendor.mjs` copies the files into `wagtail_vega/static/wagtail_vega/vendor/` and `wagtail_vega/schemas/`, and records the versions in `vendor/VERSIONS.json`. Run the full test suite afterwards, including the browser tests. CI runs `npm ci --ignore-scripts && npm run build` and fails if the committed files differ from what the pinned packages produce.

vega-embed bundles vega-interpreter, which CSP-safe mode and the chart builder's preview use, so it isn't vendored separately.

Source-map comments are stripped from every vendored script, because `ManifestStaticFilesStorage` fails on references to maps that aren't vendored. The admin's chart builder previews charts with the same files, so check it in the sandbox too.

### CodeMirror

The admin's code editor uses [CodeMirror 6](https://codemirror.net/), which ships as ES modules split over many packages. They're bundled with [esbuild](https://esbuild.github.io/) into one script, `wagtail_vega/static/wagtail_vega/admin/vendor/codemirror.js`, which is committed, so installing wagtail-vega doesn't need Node.

- The packages and esbuild are pinned to exact versions in `package.json` and `package-lock.json`. `npm ci` checks each one against the lockfile's integrity hash. `npm run build` rebuilds both the CodeMirror bundle and the vendored Vega files.
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
- Host allowlist matching: `wagtail_vega/spec.py` (`host_allowed`), `static/wagtail_vega/wagtail-vega.js` (`hostAllowed`) and `static/wagtail_vega/admin/chart-builder.js` (`urlAllowed`).
- Theme merging: `BaseChartBlock.get_spec` and `deep_merge` in Python, and `previewSpec` and `deepMerge` in `static/wagtail_vega/admin/chart-builder.js`, for the builder's preview.
- `var()` resolution: `wagtail_vega/themes.py` and `static/wagtail_vega/wagtail-vega.js`.

When you change behaviour, update the documentation in `docs/` and add an entry to {doc}`changelog`.

## Translations

User-facing strings in Python and templates are marked for translation. To start a translation, run this from the `wagtail_vega` directory (it needs GNU gettext):

```sh
django-admin makemessages -l de
django-admin makemessages -l de -d djangojs --ignore "static/wagtail_vega/vendor/*" --ignore "static/wagtail_vega/admin/vendor/*"
```

The first collects strings from Python and templates, including all the chart editor's text (`builder_strings.py`). The second collects the admin scripts' messages, such as the JSON error messages and the pasted-data summary, which call `gettext()` and `ngettext()`. The admin loads their translations from Django's JavaScript catalogue at `/admin/wagtail-vega/jsi18n/`.

Then translate `wagtail_vega/locale/de/LC_MESSAGES/django.po` and `djangojs.po`, compile them with `django-admin compilemessages`, and open a pull request.
