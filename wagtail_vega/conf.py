"""Access to the ``WAGTAIL_VEGA`` settings dict, with defaults."""

import ipaddress
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.db import DatabaseError

DEFAULTS: dict[str, Any] = {
    # name -> theme definition (dict, dotted path, or "vega:<builtin>")
    "THEMES": {},
    # name of the theme used when neither the block nor the editor picks one
    "DEFAULT_THEME": None,
    # hosts charts may load data from; "*.example.com" matches subdomains.
    # Relative (same-origin) URLs and the site's own hostnames (see
    # get_allowed_hosts) are always allowed.
    "ALLOWED_DATA_HOSTS": [],
    # Use vega-interpreter so charts work without 'unsafe-eval' in CSP
    "CSP_SAFE": False,
    # Render an SVG on the server (requires the "ssr" extra)
    "SSR": False,
    "SSR_CACHE_TIMEOUT": 60 * 60 * 24,
    # Render a <details> table of the chart data for screen readers / no-JS
    "FALLBACK_TABLE": True,
    "FALLBACK_TABLE_MAX_ROWS": 100,
    # Validate specs against the vendored JSON schemas when saving
    "VALIDATE_SCHEMA": True,
    # Default vega-embed options
    "EMBED_OPTIONS": {"actions": False, "renderer": "svg"},
}


def get_setting(name: str) -> Any:
    """The value of ``WAGTAIL_VEGA[name]``, or its default. A value in
    settings replaces the default; dicts are not merged."""
    user = getattr(settings, "WAGTAIL_VEGA", {})
    if name in user:
        return user[name]
    return DEFAULTS[name]


def _is_loopback(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def site_hosts() -> list[str]:
    """This site's own hostnames: those of Wagtail's ``Site`` records and of
    ``WAGTAILADMIN_BASE_URL``. Loopback names and addresses (``localhost``,
    ``127.0.0.1``…) are left out: they'd let charts make readers' browsers
    fetch from their own machine. List them in ``ALLOWED_DATA_HOSTS`` for
    local development if you need to."""
    hosts = set()
    base_url = getattr(settings, "WAGTAILADMIN_BASE_URL", "") or ""
    if base_url:
        hosts.add(urlsplit(base_url).hostname or "")
    try:
        from wagtail.models import Site

        # Cached by Wagtail, and cleared when a Site changes
        hosts.update(urlsplit(root.root_url).hostname for root in Site.get_site_root_paths())
    except DatabaseError:  # e.g. before migrations have run
        pass
    return sorted({h.lower() for h in hosts if h and h != "*" and not _is_loopback(h.lower())})


def get_allowed_hosts() -> list[str]:
    """Hosts that charts may load data from: ``ALLOWED_DATA_HOSTS`` plus this
    site's own hostnames (:func:`site_hosts`). Relative URLs are allowed on
    top of these."""
    return [*get_setting("ALLOWED_DATA_HOSTS"), *site_hosts()]
