"""Browser tests (Playwright) against a live Django server.

Run with ``pytest tests/e2e``. Playwright's bundled Chromium is used by
default (``playwright install chromium``); to use an installed Chrome
instead, add ``--browser-channel chrome``.
"""

import os

import pytest
from django.conf import settings as django_settings

from tests.testapp.demo import create_demo_page

# Playwright's sync API runs an event loop in the test thread, which makes
# Django refuse ORM calls from fixtures unless this is set.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

LOCAL_WEATHER = "/static/testapp/weather.csv"

# A browser test that hangs fails with its name after this long (pytest-timeout)
E2E_TIMEOUT = 120  # seconds


def pytest_collection_modifyitems(items):
    for item in items:
        if item.get_closest_marker("e2e") and not item.get_closest_marker("timeout"):
            item.add_marker(pytest.mark.timeout(E2E_TIMEOUT))


@pytest.fixture(autouse=True)
def _no_autosave(settings):
    """Wagtail's autosave is off in browser tests, except where a test turns
    it on (test_chart_builder.py's autosave tests): its requests would
    overlap the tests' own saves."""
    settings.WAGTAIL_AUTOSAVE_INTERVAL = 0


@pytest.fixture(autouse=True)
def _visual_editor(settings):
    """The chart editor's Visual tab opens in Simple mode in browser tests,
    which drive its settings. Voyager, the default, is tested in
    test_voyager.py, which overrides this fixture."""
    settings.WAGTAIL_VEGA = {**settings.WAGTAIL_VEGA, "VISUAL_EDITOR": "simple"}


@pytest.fixture
def vega_settings(settings):
    """A copy of the test project's WAGTAIL_VEGA that tests can modify."""
    settings.WAGTAIL_VEGA = {**django_settings.WAGTAIL_VEGA}
    return settings.WAGTAIL_VEGA


@pytest.fixture
def chart_page(transactional_db, vega_settings):
    """The demo page, made the site root, with all data served locally."""
    return create_demo_page(weather_url=LOCAL_WEATHER)


@pytest.fixture
def console_errors(page):
    """Collect console errors, page errors and CSP violations."""
    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))
    return errors


@pytest.fixture
def admin_page(page, live_server, admin_user, client):
    """A Playwright page logged in to the Wagtail admin as a superuser."""
    client.force_login(admin_user)
    page.context.add_cookies(
        [
            {
                "name": django_settings.SESSION_COOKIE_NAME,
                "value": client.cookies[django_settings.SESSION_COOKIE_NAME].value,
                "url": live_server.url,
            }
        ]
    )
    return page


@pytest.fixture(autouse=True)
def _close_pages_before_db_teardown(transactional_db, browser):
    """Close every page before the test database is flushed, so in-flight
    requests to the live server don't hit a torn-down database. Autouse
    fixtures are set up first, so this is torn down before tests' own."""
    yield
    for context in browser.contexts:
        context.close()
