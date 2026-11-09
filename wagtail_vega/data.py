"""Turn editor-supplied data (CSV, JSON, documents) into lists of rows."""

from __future__ import annotations

import csv
import io
import json
from pathlib import PurePath
from typing import Any

from django.core.cache import cache
from django.core.exceptions import ValidationError


def _coerce(value: str) -> Any:
    """Infer numbers/booleans/nulls like Vega's ``parse: "auto"`` would.

    Inline values are not parsed by Vega, so without this every CSV column
    would be a string and quantitative encodings would misbehave. Dates are
    left as strings; Vega-Lite parses them for temporal fields.
    """
    stripped = value.strip()
    if stripped == "":
        return None
    lowered = stripped.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        number = float(stripped)
    except ValueError:
        return value
    # Reject "nan"/"inf", which aren't valid JSON
    return number if number == number and abs(number) != float("inf") else value


def parse_delimited(text: str, delimiter: str = ",") -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text.strip()), delimiter=delimiter)
    if not reader.fieldnames:
        return []
    return [{k: _coerce(v or "") for k, v in row.items() if k is not None} for row in reader]


def parse_json(text: str | list | dict) -> list[Any]:
    data = json.loads(text) if isinstance(text, str) else text
    if isinstance(data, dict) and "values" in data:
        data = data["values"]
    if not isinstance(data, list):
        raise ValidationError("JSON data must be an array of rows.")
    return data


def parse_bytes(content: bytes, filename: str) -> list[Any]:
    suffix = PurePath(filename).suffix.lower()
    text = content.decode("utf-8-sig")
    if suffix == ".json":
        return parse_json(text)
    if suffix == ".tsv":
        return parse_delimited(text, "\t")
    if suffix == ".csv":
        return parse_delimited(text)
    raise ValidationError("Data documents must be .csv, .tsv or .json files.")


DOCUMENT_SUFFIXES = (".csv", ".tsv", ".json")


def document_rows(document) -> list[Any]:
    """Parse a Wagtail document, cached by its content hash."""
    key = f"wagtail_vega:doc:{document.pk}:{document.file_hash or document.file.name}"
    rows = cache.get(key)
    if rows is None:
        with document.open_file() as f:
            rows = parse_bytes(f.read(), document.file.name)
        cache.set(key, rows, None)
    return rows
