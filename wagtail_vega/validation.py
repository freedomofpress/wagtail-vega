"""Validate specs against the vendored Vega / Vega-Lite JSON schemas and the
data host allowlist."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from django.utils.translation import gettext as _
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError, best_match

from .conf import get_setting
from .spec import VEGA, VEGA_LITE, JSONPath, SpecError, disallowed_url_paths, spec_kind

SCHEMA_DIR = Path(__file__).parent / "schemas"
MAX_ERRORS = 5


@cache
def get_validator(kind: str) -> Draft7Validator:
    filename = {VEGA: "vega.json", VEGA_LITE: "vega-lite.json"}[kind]
    schema = json.loads((SCHEMA_DIR / filename).read_text())
    return Draft7Validator(schema)


@dataclass(frozen=True)
class SpecProblem:
    """A problem with a spec, at ``path`` (keys and indices; empty for the
    whole spec)."""

    path: JSONPath
    message: str

    def __str__(self) -> str:
        """``encoding.x.type: message``. The admin's code editor parses the
        leading dotted path to highlight the problem in place."""
        dotted = ".".join(str(p) for p in self.path)
        return f"{dotted}: {self.message}" if dotted else self.message


def _problem(error: ValidationError) -> SpecProblem:
    message = error.message
    if len(message) > 300:
        message = message[:300] + "…"
    return SpecProblem(tuple(error.absolute_path), message)


def schema_problems(spec: dict[str, Any]) -> list[SpecProblem]:
    """Problems found by validating against the JSON schema (empty if valid).

    Raises ``SpecError`` if the ``$schema`` is missing or unrecognised.
    """
    validator = get_validator(spec_kind(spec))
    errors = list(validator.iter_errors(spec))
    if not errors:
        return []
    # Top-level specs are a large anyOf; best_match descends into the most
    # relevant branch, which gives far more useful messages than the root.
    problems = [_problem(best_match(errors))]
    for error in errors:
        if len(problems) >= MAX_ERRORS:
            break
        problem = _problem(error)
        if problem not in problems and not error.context:
            problems.append(problem)
    return problems


def validate_spec(spec: dict[str, Any]) -> list[str]:
    """Return a list of human-readable schema errors (empty if valid).

    Raises ``SpecError`` if the ``$schema`` is missing or unrecognised.
    """
    return [str(p) for p in schema_problems(spec)]


def spec_problems(spec: Any) -> list[SpecProblem]:
    """Everything ``SpecBlock`` checks when a page is saved: the spec is an
    object with a known ``$schema``, matches the JSON schema (if the
    VALIDATE_SCHEMA setting is on), and only loads data from allowed hosts.

    Used both on save and by the admin's live validation endpoint, so the
    editor shows exactly the errors that saving would.
    """
    if not isinstance(spec, dict):
        return [SpecProblem((), _("The spec must be a JSON object."))]
    try:
        problems = schema_problems(spec) if get_setting("VALIDATE_SCHEMA") else []
        if not problems:
            spec_kind(spec)
    except SpecError as e:
        return [SpecProblem(("$schema",) if "$schema" in spec else (), str(e))]
    for path, url in disallowed_url_paths(spec, get_setting("ALLOWED_DATA_HOSTS")):
        problems.append(SpecProblem(path, _("Loading data from %s is not allowed.") % url))
    return problems
