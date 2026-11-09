import pytest
from django.core.cache import cache

VL = "https://vega.github.io/schema/vega-lite/v6.json"
VG = "https://vega.github.io/schema/vega/v6.json"


@pytest.fixture
def vl_bar():
    return {
        "$schema": VL,
        "data": {"name": "source"},
        "mark": "bar",
        "encoding": {
            "x": {"field": "a", "type": "nominal"},
            "y": {"field": "b", "type": "quantitative"},
        },
    }


@pytest.fixture
def vg_bar():
    return {
        "$schema": VG,
        "width": 200,
        "height": 100,
        "data": [
            {"name": "source", "values": [{"a": "x", "b": 0}]},
            {
                "name": "filtered",
                "source": "source",
                "transform": [{"type": "filter", "expr": "datum.b > 0"}],
            },
        ],
        "scales": [
            {
                "name": "x",
                "type": "band",
                "domain": {"data": "source", "field": "a"},
                "range": "width",
            },
            {"name": "y", "domain": {"data": "source", "field": "b"}, "range": "height"},
        ],
        "marks": [
            {
                "type": "rect",
                "from": {"data": "source"},
                "encode": {
                    "enter": {
                        "x": {"scale": "x", "field": "a"},
                        "width": {"scale": "x", "band": 1},
                        "y": {"scale": "y", "field": "b"},
                        "y2": {"scale": "y", "value": 0},
                    }
                },
            }
        ],
    }


@pytest.fixture
def vega_settings(settings):
    """Reset WAGTAIL_VEGA to defaults; tests tweak it as needed."""
    settings.WAGTAIL_VEGA = {}
    return settings.WAGTAIL_VEGA


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts with an empty cache (parsed documents, SSR output)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    """Uploads go to a fresh folder per test, as on CI. (A shared folder makes
    Django rename duplicate filenames, which can hide caching bugs.)"""
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def _site_hosts(request, monkeypatch):
    """The data allowlist includes the site's own hostnames, which come from
    the database. Tests without database access get none."""
    uses_db = request.node.get_closest_marker("django_db") or {
        "db",
        "transactional_db",
        "admin_client",
        "admin_user",
        "live_server",
    } & set(request.fixturenames)
    if not uses_db:
        monkeypatch.setattr("wagtail_vega.conf.site_hosts", lambda: [])
