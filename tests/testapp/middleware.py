import os
import threading

from django.conf import settings
from django.db import connection


class ContentSecurityPolicyMiddleware:
    """Send a strict CSP on frontend pages when settings.SANDBOX_STRICT_CSP is
    set (WAGTAIL_VEGA_CSP_SAFE=1 in the sandbox), to check that charts render
    without 'unsafe-eval' or inline scripts/styles."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(settings, "SANDBOX_STRICT_CSP", False) and not request.path.startswith(
            "/admin/"
        ):
            response["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self' https://vega.github.io"
            )
        return response


class SandboxAutoLoginMiddleware:
    """Log every request in as the sandbox superuser when
    WAGTAIL_VEGA_SANDBOX_AUTOLOGIN=1, so headless browsers can screenshot
    the admin. Test project only; never use outside the sandbox."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            os.environ.get("WAGTAIL_VEGA_SANDBOX_AUTOLOGIN") == "1"
            and not request.user.is_authenticated
        ):
            from django.contrib.auth import get_user_model, login

            user = get_user_model().objects.filter(is_superuser=True).first()
            if user:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)


# Held while a request is handled, and by tests while they read the database
# (see tests/e2e/conftest.py)
DATABASE_LOCK = threading.RLock()


class SerialRequestsMiddleware:
    """Handle one request at a time when the database is in-memory SQLite.

    Browser tests run against Django's threaded live server, and with an
    in-memory SQLite database every thread shares the test's one connection.
    Requests that overlap (the chart editor's live checks, Wagtail's
    autosave, a save) can then corrupt each other's queries. Test project
    only."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not connection.is_in_memory_db():
            return self.get_response(request)
        with DATABASE_LOCK:
            return self.get_response(request)
