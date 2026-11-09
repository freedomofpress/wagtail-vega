"""Charts render in a real browser: themes, dark mode, CSP, no-JS, security."""

import pytest
from playwright.sync_api import expect

from wagtail_vega import ssr

pytestmark = pytest.mark.e2e

CHARTS = "wagtail-vega-chart"


def wait_for_charts(page, count=4):
    expect(page.locator(f"{CHARTS}.is-rendered")).to_have_count(count, timeout=15_000)


def test_all_charts_render(page, live_server, chart_page, console_errors):
    page.goto(live_server.url + chart_page.url)
    wait_for_charts(page)
    expect(page.locator(f"{CHARTS}.has-error")).to_have_count(0)
    for chart in page.locator(CHARTS).all():
        expect(chart.locator("svg.marks")).to_have_count(1)
    # Data from pasted TSV, pasted JSON, the database, and a URL all arrived
    assert page.locator(".mark-rect path, .mark-rect rect").count() > 10
    assert page.locator(".mark-line path").count() == 1
    assert console_errors == []


def test_accessibility_markup(page, live_server, chart_page):
    page.goto(live_server.url + chart_page.url)
    wait_for_charts(page)
    figure = page.locator("figure.wagtail-vega").first
    description_id = figure.get_attribute("aria-describedby")
    expect(page.locator(f"#{description_id}")).to_have_text(
        "Grouped bar chart of records requests per quarter."
    )
    expect(figure.locator("figcaption")).to_have_text("Source: example data")
    figure.locator("summary").click()
    expect(figure.locator("details table th").first).to_have_text("quarter")
    # Interactive controls (the Vega slider) stay reachable
    expect(page.get_by_role("slider")).to_have_count(1)


def axis_label_fill(page, index=0):
    return (
        page.locator(CHARTS).nth(index).locator(".role-axis-label text").first.get_attribute("fill")
    )


def test_theme_light_and_dark(browser, live_server, chart_page):
    light = browser.new_page(color_scheme="light")
    light.goto(live_server.url + chart_page.url)
    wait_for_charts(light)
    assert axis_label_fill(light) == "#333"
    # --brand from the site's CSS drives the first category colour
    assert light.locator(CHARTS).first.locator(".mark-rect path").first.get_attribute("fill") in (
        "#6a4c93",
        "#2a9d8f",
    )
    fills = {
        p.get_attribute("fill")
        for p in light.locator(CHARTS).first.locator(".mark-rect path").all()
    }
    assert "#6a4c93" in fills

    dark = browser.new_page(color_scheme="dark")
    dark.goto(live_server.url + chart_page.url)
    wait_for_charts(dark)
    assert axis_label_fill(dark) == "#ddd"


def test_data_color_scheme_attribute_and_refresh(page, live_server, chart_page):
    page.emulate_media(color_scheme="light")
    page.goto(live_server.url + chart_page.url)
    wait_for_charts(page)
    assert axis_label_fill(page) == "#333"
    page.evaluate(
        """() => {
            document.documentElement.dataset.colorScheme = "dark";
            document.dispatchEvent(new Event("wagtail-vega:refresh"));
        }"""
    )
    expect(page.locator(CHARTS).first.locator(".role-axis-label text").first).to_have_attribute(
        "fill", "#ddd"
    )


def test_strict_csp(page, live_server, chart_page, settings, vega_settings, console_errors):
    settings.SANDBOX_STRICT_CSP = True
    vega_settings["CSP_SAFE"] = True
    violations = []
    page.on("console", lambda m: "Content Security Policy" in m.text and violations.append(m.text))

    response = page.goto(live_server.url + chart_page.url)
    assert "script-src 'self';" in response.headers["content-security-policy"]
    page.evaluate(
        """() => document.addEventListener("securitypolicyviolation",
            (e) => console.error("CSP violation: " + e.violatedDirective))"""
    )
    wait_for_charts(page)
    # The Vega filter expression ran via the interpreter (G and A are below
    # the threshold of 30, so 6 of 8 bars are drawn)
    assert page.locator(CHARTS).nth(1).locator(".mark-rect path").count() == 6
    # The URL CSV was parsed without eval
    assert page.locator(CHARTS).nth(3).locator(".mark-rect path").count() > 0
    assert violations == [] and console_errors == []
    # Vega's own CSV reader is untouched for other charts on the page
    assert page.evaluate("vega.formats('wagtail-vega-csv') !== null")
    assert not page.evaluate("vega.formats('csv').toString().includes('parseDelimited')")


@pytest.mark.skipif(not ssr.is_available(), reason="vl-convert not installed")
def test_server_rendered_without_javascript(browser, live_server, chart_page, vega_settings):
    vega_settings["SSR"] = True
    page = browser.new_page(java_script_enabled=False)
    page.goto(live_server.url + chart_page.url)
    # The fourth chart loads a relative URL, which SSR leaves to the browser
    expect(page.locator(".wagtail-vega__ssr svg")).to_have_count(3)
    expect(page.locator(".wagtail-vega__noscript")).to_have_count(1)
    # CSS variables were resolved from the theme's fallbacks on the server
    assert "#c0392b" in page.locator(".wagtail-vega__ssr").first.inner_html()
    expect(page.locator("details.wagtail-vega__data")).to_have_count(3)


def test_without_javascript_or_ssr(browser, live_server, chart_page):
    page = browser.new_page(java_script_enabled=False)
    page.goto(live_server.url + chart_page.url)
    expect(page.locator(".wagtail-vega__ssr")).to_have_count(0)
    expect(page.locator("details.wagtail-vega__data")).to_have_count(3)


def test_runtime_urls_outside_allowlist_are_blocked(page, live_server, transactional_db):
    """A URL built from a signal can't be checked on save; the browser-side
    loader must refuse it, and no request may be made."""
    from tests.testapp.demo import ensure_site
    from tests.testapp.models import ChartPage

    spec = {
        "$schema": "https://vega.github.io/schema/vega/v6.json",
        "signals": [{"name": "src", "value": "https://evil.example/steal.csv"}],
        "data": [{"name": "d", "url": {"signal": "src"}, "format": {"type": "csv"}}],
    }
    home = ensure_site().root_page
    chart_page = home.add_child(
        instance=ChartPage(title="Evil", slug="evil", body=[("chart", {"spec": spec, "data": []})])
    )
    requested = []

    def block(route):
        requested.append(route.request.url)
        route.abort()

    page.route("https://evil.example/**", block)
    messages = []
    page.on("console", lambda m: messages.append(m.text))
    page.goto(live_server.url + chart_page.url)
    page.wait_for_timeout(1500)
    assert requested == []
    assert any("not allowed" in m for m in messages)


def make_page(slug, *blocks):
    from tests.testapp.demo import ensure_site
    from tests.testapp.models import ChartPage

    home = ensure_site().root_page
    return home.add_child(instance=ChartPage(title=slug, slug=slug, body=list(blocks)))


VG = "https://vega.github.io/schema/vega/v6.json"


def vega_bars(data):
    """A raw Vega bar chart over the "weather" dataset's rows."""
    return {
        "$schema": VG,
        "width": 200,
        "height": 100,
        "data": [{"name": "weather"}],
        "scales": [
            {
                "name": "x",
                "type": "band",
                "domain": {"data": "weather", "field": "date"},
                "range": "width",
            },
        ],
        "marks": [
            {
                "type": "rect",
                "from": {"data": "weather"},
                "encode": {
                    "enter": {
                        "x": {"scale": "x", "field": "date"},
                        "width": {"scale": "x", "band": 1},
                        "y": {"value": 0},
                        "height": {"value": 10},
                        "href": {"value": "https://elsewhere.example/story"},
                    }
                },
            },
        ],
    }


def url_chart(url):
    return (
        "chart",
        {
            "spec": vega_bars(None),
            "data": [{"name": "weather", "source_type": "url", "url": url, "format": ""}],
        },
    )


def test_vega_csv_url_without_format(page, live_server, transactional_db):
    """Vega reads URLs as JSON unless told otherwise: the format is inferred."""
    chart_page = make_page("vega-csv", url_chart("/static/testapp/weather.csv"))
    page.goto(live_server.url + chart_page.url)
    wait_for_charts(page, 1)
    assert page.locator(".mark-rect path").count() == 48


def test_data_errors_are_reported(page, live_server, transactional_db):
    chart_page = make_page("broken", url_chart("/static/testapp/missing.csv"))
    page.add_init_script(
        """document.addEventListener("wagtail-vega:error",
            (e) => { window.chartError = String(e.detail.error); })"""
    )
    page.goto(live_server.url + chart_page.url)
    expect(page.locator(f"{CHARTS}.has-error")).to_have_count(1)
    expect(page.locator(f"{CHARTS}.is-rendered")).to_have_count(0)
    assert "Loading failed" in page.evaluate("window.chartError")


def test_chart_links_to_other_hosts_work(page, live_server, transactional_db):
    """The data allowlist doesn't apply to hyperlinks in charts."""
    chart_page = make_page("links", url_chart("/static/testapp/weather.csv"))
    page.route(
        "https://elsewhere.example/**",
        lambda route: route.fulfill(status=200, content_type="text/html", body="<p>story</p>"),
    )
    page.goto(live_server.url + chart_page.url)
    wait_for_charts(page, 1)
    with page.expect_request("https://elsewhere.example/story"):
        page.locator(".mark-rect path").first.click()


def test_page_body_without_context_loads_scripts_once(page, live_server, chart_page):
    """{{ page.body }} renders blocks without a request; the loader keeps the
    libraries from loading once per chart."""
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(live_server.url + chart_page.url + "?raw=1")
    wait_for_charts(page)
    assert page.locator("script[src*='wagtail-vega-loader.js']").count() == 4
    assert sum("vendor/vega.min.js" in u for u in requests) == 1
    assert page.evaluate("document.querySelectorAll('script[src*=\"vega.min.js\"]').length") == 1
