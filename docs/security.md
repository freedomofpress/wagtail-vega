# Security

Specs are powerful: they can load data from URLs, show images and link to other pages. wagtail-vega limits where charts can load from, and can run under a strict Content Security Policy.

## The data host allowlist

`ALLOWED_DATA_HOSTS` lists the hosts that charts may load from. It's empty by default, so only relative and same-origin URLs are allowed.

```python
WAGTAIL_VEGA = {
    "ALLOWED_DATA_HOSTS": [
        "vega.github.io",      # exactly this host
        "*.example.org",       # example.org and all its subdomains
    ],
}
```

- Host names are compared without regard to case. Ports aren't checked.
- `"*.example.org"` matches `example.org`, `data.example.org` and `a.b.example.org`.
- `"*"` allows every host. Use it with care.
- Only `http` and `https` URLs are allowed, apart from relative ones.
- Relative URLs, such as `/media/data.csv`, are always allowed, because they're on your own site. So are absolute URLs to your site's own hostnames: those of Wagtail's sites and of `WAGTAILADMIN_BASE_URL`. `localhost` and loopback addresses are left out even if a site uses them, since they'd let a chart make readers' browsers fetch from their own machine; list them in `ALLOWED_DATA_HOSTS` for local development.
- URLs are checked the way browsers read them: leading and trailing spaces and control characters are ignored, tabs and newlines removed, and backslashes count as slashes. So `/\evil.example/data.csv`, which browsers fetch from `evil.example`, isn't mistaken for a path on your site. Scheme-relative URLs (`//data.example.org/x.csv`) are allowed if their host is.

The URLs editors can enter for URL datasets must also be `http`, `https` or a path starting with `/`. A path like `data.csv` is rejected because it would depend on the page's URL.

### What's checked where

| What | Checked | How |
| --- | --- | --- |
| Literal `url` strings anywhere in a spec | When the page is saved, and as the spec is edited | `SpecBlock` rejects specs with a `url` that isn't relative or on an allowed host. The admin's code editor runs the same check live (see below). |
| URL datasets entered by editors | When the page is saved | `DatasetBlock` rejects URLs that aren't allowed. |
| Remote datasets returned by `get_datasets()` | In the browser and during server-side rendering | Not checked on save. |
| Everything a chart loads in the browser: data, images, and links | Each time it's loaded | A restricted Vega loader refuses URLs that aren't same-origin or on an allowed host. This also covers URLs built at runtime, for example from signals, which can't be checked on save. |
| Everything vl-convert loads during server-side rendering | Each time a chart is rendered | vl-convert may only fetch from the literal, allowed, absolute URLs in the spec. Specs that use relative URLs aren't server-rendered. |

The allowlist is copied into each chart's payload so the browser can enforce it.

### Live validation in the admin

The spec editor checks the spec as it's edited by posting it to `/admin/wagtail-vega/validate-spec/` ({py:func}`wagtail_vega.views.validate_spec`). Like the rest of the admin, the endpoint needs a logged-in user with permission to access the Wagtail admin, and Django's CSRF protection applies. It runs the same checks as saving a page, {py:func}`~wagtail_vega.validation.spec_problems`, and doesn't save or fetch anything. Its responses can tell an admin user which hosts aren't allowed, which they could find out by saving anyway.

The editor itself, CodeMirror 6, is vendored like the Vega libraries (see {doc}`contributing`), so the admin makes no CDN requests either.

(voyager-security)=

### The visual chart builder (Vega Voyager)

The spec field's **Build chart with Voyager** button (see {doc}`editor-experience`) runs Voyager, whose last release (2018) uses React 15, vega 4 and vega-lite 2. It's vendored and integrity-checked like the other libraries, and kept away from the admin:

- It runs only on its own admin page, `/admin/wagtail-vega/voyager/`, loaded in an `<iframe sandbox="allow-scripts">`. The page is also sent with its own `Content-Security-Policy`, starting `sandbox allow-scripts`, so it stays sandboxed even if opened on its own. Without `allow-same-origin`, it gets an opaque origin: it can't read the admin's DOM, cookies or CSRF token. Its scripts and styles never load in the admin page itself.
- The same policy cuts Voyager off from the network (`default-src 'none'`, `connect-src 'none'`, `form-action 'none'`, `base-uri 'none'`). Scripts, styles, images and fonts may only come from your static files. The admin page fetches the chart's data and passes it in, so Voyager never needs to make a request itself.
- The admin and the iframe talk with `postMessage`. The admin only accepts messages from that iframe's window with the sandbox's `"null"` origin; the iframe only accepts messages from its parent at the admin's origin, and only sends to that origin.
- Documents are read through `/admin/wagtail-vega/document-rows/?id=…`, which also needs permission to choose (or change) the document. URL datasets are fetched by the admin page, and only from the allowlist, checked on the URL as the browser resolves it.
- The spec it produces is checked with the live validation endpoint above before it's written to the field, and again when the page is saved.

All its admin views need permission to access the Wagtail admin.

:::{note}
**If your admin has a Content Security Policy**, the Voyager page needs `'unsafe-eval'` in `script-src`: vega 4 and Voyager's schema validator compile code with `new Function`. The page sends its own `sandbox` policy; a policy your middleware adds to admin responses applies on top. Allow `frame-src 'self'` (and `frame-ancestors 'self'`) for the iframe, and add the hosts of any URL datasets to `connect-src`, since the admin page fetches them for Voyager. The page also needs `X-Frame-Options: SAMEORIGIN`, which it sets itself.
:::

Some consequences:

- URLs that a custom data source returns from `get_datasets()` aren't entered by editors, so nothing checks them on save. When a chart is rendered, a blocked one is logged as a warning on the `wagtail_vega.blocks` logger, so you notice before readers do.
- The allowlist only covers what charts **load**: data and images. [`href`](https://vega.github.io/vega-lite/docs/encoding.html#href) links in a chart can go anywhere, like any other link on the page. Vega still refuses `javascript:` links.
- If you change the allowlist, existing pages aren't checked again, but their charts are blocked in the browser from loading from removed hosts.

## What ends up in the page

Each chart's spec and inline data are written into the page as JSON, in a `<script type="application/json">` tag made with Django's `json_script`. Anyone who can view the page can read them, so don't put private data in charts, including from {doc}`custom data sources <custom-data>`.

The JSON is escaped so it can't close the `<script>` tag. The description, caption and data table are escaped by Django's templates like any other content. The server-rendered SVG comes from vl-convert, and is output as it is.

Vega specs can contain [expressions](https://vega.github.io/vega/docs/expressions/). These are a limited language, not JavaScript, but treat permission to edit specs like other permissions that affect what runs on your pages.

## Content Security Policy

wagtail-vega's frontend works under a strict Content Security Policy:

- All scripts are external files from your static files, loaded with `defer`. There are no inline scripts. The chart payload is a `<script type="application/json">`, which browsers don't run, so `script-src` doesn't apply to it.
- No styles are added at runtime. vega-embed's and vega-tooltip's default styles are turned off, and equivalent styles ship in `wagtail-vega.css`, so `style-src 'self'` works.
- The Vega libraries are vendored, so no CDN needs to be allowed.

By default, though, Vega compiles expressions and CSV parsers with `new Function`, which needs `'unsafe-eval'` in `script-src`. To avoid that, turn on CSP-safe mode.

(csp-safe)=

### CSP-safe mode

```python
WAGTAIL_VEGA = {"CSP_SAFE": True}
```

In CSP-safe mode:

- `{% wagtail_vega_assets %}` also loads `vega-interpreter.js`, and charts are rendered with `ast: true` and the [vega-interpreter](https://github.com/vega/vega/tree/main/packages/vega-interpreter) expression evaluator, which doesn't use `eval`.
- Vega's `csv`, `tsv` and `dsv` data format readers are replaced with an eval-free parser.

With it on, charts work with a policy like this one, which the test suite checks:

```text
default-src 'self';
script-src 'self';
style-src 'self';
img-src 'self' data:;
connect-src 'self' https://vega.github.io
```

Add each host in `ALLOWED_DATA_HOSTS` that the browser loads data from to `connect-src`, and any host charts load images from to `img-src`. If you serve static files from another origin, such as a CDN or S3, add it to `script-src` and `style-src`.

Things to know:

- The interpreter is slower than compiled expressions, which matters for charts with a lot of data or interaction.
- A few expression functions aren't available in the interpreter. Test charts that use unusual expressions with CSP-safe mode on.
- The replacement CSV/TSV parser is registered under its own format names (`wagtail-vega-csv` and so on), and only wagtail-vega's charts are pointed at it. Any other Vega charts on the page keep Vega's own parser.
- These notes are about the pages your site serves. The Wagtail admin has its own CSP requirements.
