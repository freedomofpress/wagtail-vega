"""Optional server-side rendering of charts to SVG using vl-convert.

Install with ``pip install wagtail-vega[ssr]``. Rendering failures are logged
and the chart falls back to client-side rendering only.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from urllib.parse import urlsplit

from django.core.cache import cache

from .conf import get_setting
from .encoders import VegaJSONEncoder
from .spec import VEGA_LITE, host_allowed, iter_urls

logger = logging.getLogger(__name__)

try:
    import vl_convert
except ImportError:  # pragma: no cover - depends on optional extra
    vl_convert = None


def is_available() -> bool:
    """Whether vl-convert is installed."""
    return vl_convert is not None


def allowed_base_urls(spec: Any) -> list[str]:
    """Base URLs vl-convert may fetch from: only the literal, allowlisted
    absolute URLs in the spec. Everything else (including relative URLs and
    URLs built from signals) is blocked."""
    allowed = get_setting("ALLOWED_DATA_HOSTS")
    bases = set()
    for url in iter_urls(spec):
        parts = urlsplit(url)
        if parts.netloc and host_allowed(url, allowed):
            bases.add(f"{parts.scheme}://{parts.netloc}/")
    return sorted(bases)


def render_svg(spec: dict, kind: str, vega_theme: str | None = None) -> str | None:
    """Render a final spec to SVG, cached in Django's default cache for
    ``SSR_CACHE_TIMEOUT`` seconds.

    ``kind`` is ``"vega"`` or ``"vega-lite"``. ``vega_theme`` is the name of a
    theme bundled with vega-embed, and only applies to Vega-Lite. Returns
    ``None`` if vl-convert isn't installed, the spec uses relative URLs, or
    rendering fails.
    """
    if vl_convert is None:
        logger.warning("wagtail-vega SSR is enabled but vl-convert is not installed")
        return None

    relative = [u for u in iter_urls(spec) if not urlsplit(u).netloc]
    if relative:
        # vl-convert has no base URL to resolve these against, and fetching
        # our own site mid-request could deadlock a single-threaded server.
        logger.debug("wagtail-vega: not server-rendering spec with relative URLs %s", relative)
        return None

    payload = json.dumps(spec, cls=VegaJSONEncoder, sort_keys=True)
    digest = hashlib.sha256(f"{kind}:{vega_theme}:{payload}".encode()).hexdigest()
    key = f"wagtail_vega:svg:{digest}"
    svg = cache.get(key)
    if svg is not None:
        return svg

    # Round-trip through JSON so dates/Decimals become plain values, as in the browser
    plain = json.loads(payload)
    bases = allowed_base_urls(plain)
    try:
        if kind == VEGA_LITE:
            svg = vl_convert.vegalite_to_svg(plain, theme=vega_theme, allowed_base_urls=bases)
        else:
            svg = vl_convert.vega_to_svg(plain, allowed_base_urls=bases)
    except Exception:
        logger.exception("wagtail-vega: server-side rendering failed")
        return None

    cache.set(key, svg, get_setting("SSR_CACHE_TIMEOUT"))
    return svg
