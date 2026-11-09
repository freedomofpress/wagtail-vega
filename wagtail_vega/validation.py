"""Validate specs against the vendored Vega / Vega-Lite JSON schemas."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError, best_match

from .spec import VEGA, VEGA_LITE, spec_kind

SCHEMA_DIR = Path(__file__).parent / "schemas"
MAX_ERRORS = 5


@cache
def get_validator(kind: str) -> Draft7Validator:
    filename = {VEGA: "vega.json", VEGA_LITE: "vega-lite.json"}[kind]
    schema = json.loads((SCHEMA_DIR / filename).read_text())
    return Draft7Validator(schema)


def _format(error: ValidationError) -> str:
    path = ".".join(str(p) for p in error.absolute_path)
    message = error.message
    if len(message) > 300:
        message = message[:300] + "…"
    return f"{path}: {message}" if path else message


def validate_spec(spec: dict[str, Any]) -> list[str]:
    """Return a list of human-readable schema errors (empty if valid).

    Raises ``SpecError`` if the ``$schema`` is missing or unrecognised.
    """
    validator = get_validator(spec_kind(spec))
    errors = list(validator.iter_errors(spec))
    if not errors:
        return []
    # Top-level specs are a large anyOf; best_match descends into the most
    # relevant branch, which gives far more useful messages than the root.
    messages = [_format(best_match(errors))]
    for error in errors:
        if len(messages) >= MAX_ERRORS:
            break
        msg = _format(error)
        if msg not in messages and not error.context:
            messages.append(msg)
    return messages
