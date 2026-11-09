import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "not-secret"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "wagtail_vega",
    "tests.testapp",
    "wagtail.api.v2",
    "rest_framework",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "tests.testapp.middleware.SerialRequestsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "tests.testapp.middleware.SandboxAutoLoginMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
    "tests.testapp.middleware.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DATABASE_NAME", BASE_DIR / "sandbox.sqlite3"),
    }
}

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
USE_TZ = True

WAGTAIL_SITE_NAME = "wagtail-vega sandbox"
WAGTAILADMIN_BASE_URL = "http://localhost:8000"

WAGTAIL_VEGA = {
    "THEMES": {
        "house": {
            "label": "House style",
            "config": {
                "font": "Georgia, serif",
                "background": "var(--chart-bg, white)",
                # Every colour has at least 3:1 contrast with the background
                # (WCAG 1.4.11), in light and dark mode
                "range": {"category": ["var(--brand)", "#2a9d8f", "#b45309", "#264653", "#be185d"]},
                "axis": {"labelColor": "#333", "titleColor": "#333"},
                "title": {"color": "#111"},
                "legend": {"labelColor": "#333", "titleColor": "#333"},
            },
            "dark": {
                "range": {"category": ["var(--brand)", "#4fd1c5", "#f4a261", "#e9c46a", "#93c5fd"]},
                "axis": {"labelColor": "#ddd", "titleColor": "#ddd", "gridColor": "#444"},
                "title": {"color": "#fff"},
                "legend": {"labelColor": "#ddd", "titleColor": "#ddd"},
                "view": {"stroke": "#444"},
            },
            "fallbacks": {"--brand": "#c0392b"},
            # The admin's previews can't use the site's CSS (site.css)
            "dark_fallbacks": {"--chart-bg": "#1b1b1b"},
        },
        "538": "vega:fivethirtyeight",
    },
    "DEFAULT_THEME": "house",
    "ALLOWED_DATA_HOSTS": ["vega.github.io"],
    "CSP_SAFE": os.environ.get("WAGTAIL_VEGA_CSP_SAFE") == "1",
    "SSR": os.environ.get("WAGTAIL_VEGA_SSR") == "1",
}

# Test project only: see tests/testapp/middleware.py
SANDBOX_STRICT_CSP = os.environ.get("WAGTAIL_VEGA_CSP_SAFE") == "1"
