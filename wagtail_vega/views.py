"""Admin views."""

import json

from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from wagtail.admin.auth import require_admin_access

from .validation import spec_problems


@require_admin_access
@require_POST
def validate_spec(request):
    """Live validation for the admin's spec editor.

    POST a spec as JSON (with the CSRF token header); the response is
    ``{"errors": [{"path": ["encoding", "x", "type"], "message": "..."}]}``,
    the same problems that saving the spec would report. Admin users only
    (``require_admin_access``, which ``register_admin_urls`` also applies).
    """
    try:
        spec = json.loads(request.body)
    except ValueError:
        return JsonResponse(
            {"errors": [{"path": [], "message": _("Enter a valid JSON.")}]}, status=400
        )
    errors = [{"path": list(p.path), "message": p.message} for p in spec_problems(spec)]
    return JsonResponse({"errors": errors})
