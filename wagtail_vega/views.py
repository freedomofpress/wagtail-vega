"""Admin views behind the "Build chart with Voyager" button.

They are registered with ``register_admin_urls``, so Wagtail only lets in
users who can access the admin.
"""

from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils.translation import gettext as _
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST
from wagtail.documents import get_document_model

from .data import DOCUMENT_SUFFIXES
from .data import document_rows as parse_document
from .encoders import VegaJSONEncoder
from .validation import spec_errors

# The Voyager page runs old third-party code (React 15, vega 4). Sandboxing
# it without allow-same-origin gives it an opaque origin: it can't read the
# admin's cookies or DOM, or make credentialed requests the admin trusts. The
# iframe has the same sandbox attribute; the header also covers the page
# being opened on its own.
FRAME_CSP = "sandbox allow-scripts"


def document_permissions():
    Document = get_document_model()
    try:
        from wagtail.permissions import policy_registry

        return policy_registry.get_by_type(Document)
    except (ImportError, LookupError):  # older Wagtail
        from wagtail.documents.permissions import permission_policy

        return permission_policy


@require_GET
@xframe_options_sameorigin
def voyager(request):
    response = TemplateResponse(request, "wagtail_vega/admin/voyager.html")
    response["Content-Security-Policy"] = FRAME_CSP
    return response


@require_GET
def document_rows(request):
    """The parsed rows of a data document, as charts will see them."""
    try:
        pk = int(request.GET.get("id", ""))
    except ValueError:
        return HttpResponseBadRequest("Missing or invalid id")
    document = get_object_or_404(get_document_model(), pk=pk)
    if not document_permissions().user_has_any_permission_for_instance(
        request.user, ["choose", "change"], document
    ):
        return JsonResponse({"error": _("You can't use this document.")}, status=403)
    if not document.file.name.lower().endswith(DOCUMENT_SUFFIXES):
        return JsonResponse({"error": _("Choose a .csv, .tsv or .json document.")}, status=400)
    try:
        rows = parse_document(document)
    except (ValidationError, ValueError, UnicodeDecodeError) as e:
        # json.JSONDecodeError is a ValueError
        message = e.messages[0] if isinstance(e, ValidationError) else str(e)
        return JsonResponse({"error": _("Couldn't read this data: %s") % message}, status=400)
    return JsonResponse({"rows": rows}, encoder=VegaJSONEncoder)


@require_POST
def validate_spec(request):
    """Check a spec the way saving the page would. Expects ``{"spec": ...}``."""
    try:
        spec = json.loads(request.body)["spec"]
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest("Expected a JSON body with a spec")
    return JsonResponse({"errors": [str(e) for e in spec_errors(spec)]})
