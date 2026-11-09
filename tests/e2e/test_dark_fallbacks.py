"""Dark-mode fallbacks for CSS variables in themes (#24).

The admin's chart previews can't use the site's CSS, so var(--token) values
come from the theme's fallbacks; in dark mode, from its dark_fallbacks too.
"""

import pytest
from django.urls import reverse
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

DARK_BG = "rgb(27, 27, 27)"  # the sandbox theme's dark_fallbacks["--chart-bg"]


def preview_background(admin_page, live_server, chart_page, scheme):
    from tests.e2e.test_chart_builder import open_builder

    admin_page.emulate_media(color_scheme=scheme)
    admin_page.goto(live_server.url + reverse("wagtailadmin_pages:edit", args=(chart_page.pk,)))
    dialog = open_builder(admin_page)
    svg = dialog.locator("[data-chart] svg.marks")
    expect(svg).to_be_visible(timeout=15_000)
    return svg.evaluate("s => getComputedStyle(s).backgroundColor")


def test_admin_preview_uses_dark_fallbacks(admin_page, live_server, chart_page):
    # var(--chart-bg, white): no site CSS in the admin, so the dark fallback
    # applies; before #24 this was white behind light-grey dark-mode labels
    assert preview_background(admin_page, live_server, chart_page, "dark") == DARK_BG


def test_admin_preview_light_uses_light_fallbacks(admin_page, live_server, chart_page):
    assert preview_background(admin_page, live_server, chart_page, "light") == "rgb(255, 255, 255)"


def test_site_uses_dark_fallbacks_only_for_tokens_its_css_lacks(
    browser, live_server, chart_page, vega_settings
):
    theme = vega_settings["THEMES"]["house"]
    vega_settings["THEMES"] = {
        **vega_settings["THEMES"],
        "house": {
            **theme,
            "config": {**theme["config"], "view": {"fill": "var(--plot-bg, #eee)"}},
            "dark_fallbacks": {"--plot-bg": "#202830", "--chart-bg": "#ff00ff"},
        },
    }
    page = browser.new_page(color_scheme="dark")
    page.goto(live_server.url + chart_page.url)
    chart = page.locator("wagtail-vega-chart").first
    expect(chart).to_have_class("wagtail-vega__chart is-rendered", timeout=15_000)
    # --plot-bg isn't in site.css: the dark fallback fills it in
    plot = chart.locator(".role-frame path.background").first
    assert plot.get_attribute("fill") == "#202830"
    # --chart-bg is in site.css (#1b1b1b in dark mode): the page's CSS wins
    bg = chart.locator("svg.marks").evaluate("s => getComputedStyle(s).backgroundColor")
    assert bg == DARK_BG
