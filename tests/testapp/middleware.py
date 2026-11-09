import os


class ContentSecurityPolicyMiddleware:
    """Send a strict CSP on frontend pages when WAGTAIL_VEGA_CSP_SAFE=1, to
    check that charts render without 'unsafe-eval' or inline scripts/styles."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if os.environ.get("WAGTAIL_VEGA_CSP_SAFE") == "1" and not request.path.startswith(
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
