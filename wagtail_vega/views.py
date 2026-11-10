"""Admin views."""

import json

from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from wagtail.admin.auth import require_admin_access
from wagtail.documents import get_document_model

from .data import DOCUMENT_SUFFIXES
from .data import document_rows as parse_document
from .encoders import VegaJSONEncoder
from .validation import spec_problems


@require_admin_access
@require_POST
def validate_spec(request):
    """Live validation for the admin's spec editor and chart builder.

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


def document_permissions():
    Document = get_document_model()
    try:
        from wagtail.permissions import policy_registry

        return policy_registry.get_by_type(Document)
    except (ImportError, LookupError):  # older Wagtail
        from wagtail.documents.permissions import permission_policy

        return permission_policy


@require_admin_access
@require_GET
def document_rows(request):
    """The parsed rows of a data document (``?id=``), as charts will see them.

    The chart builder uses this to show a document dataset's columns and to
    draw its preview. The user needs permission to choose or change the
    document."""
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


@method_decorator(require_admin_access, name="dispatch")
class SourceRowsView(View):
    """The rows of a custom dataset source, for the admin: the dataset's
    summary and the chart editor's preview. Pairs with
    ``DatasetBlock.source_rows_urls``, and answers like ``document_rows``.

    The admin sends a GET request with the source's fields as query
    parameters, named after the fields, and repeated for fields with several
    values (such as a multiple choice): read them with ``request.GET.get()``
    and ``request.GET.getlist()``. Implement ``get_rows()`` to return the
    rows. They're sent as ``{"rows": [...]}``, encoded as charts encode them
    (``VegaJSONEncoder``: Decimals become numbers, dates ISO 8601 strings).
    Raise ``ValidationError`` to show the editor a message instead; it's sent
    as ``{"error": "..."}``, with status 400.

    Admin users only. Register it with Wagtail's ``register_admin_urls``
    hook::

        @hooks.register("register_admin_urls")
        def register_admin_urls():
            return [
                path("incident-rows/", IncidentRowsView.as_view(), name="incident_rows"),
            ]
    """

    http_method_names = ["get", "head", "options"]

    def get_rows(self, request) -> list[dict]:
        """The rows for the fields in ``request.GET``. Subclasses implement
        this."""
        raise NotImplementedError(f"{type(self).__name__} must implement get_rows().")

    def get(self, request, *args, **kwargs):
        try:
            rows = self.get_rows(request)
        except ValidationError as e:
            return JsonResponse({"error": " ".join(e.messages)}, status=400)
        return JsonResponse({"rows": list(rows)}, encoder=VegaJSONEncoder)
