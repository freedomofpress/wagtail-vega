"""Turn editor-supplied data (pasted text, documents) into lists of rows."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import PurePath
from typing import Any

from django.core.cache import cache
from django.core.exceptions import ValidationError

# Keep these in sync with static/wagtail_vega/admin/dataset-block.js
NUMBER_RE = re.compile(r"^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$")
# "1,234" / "1,234,567.89", as copied from a formatted spreadsheet
THOUSANDS_RE = re.compile(r"^[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
# "02134", "007": zip codes and IDs, which must stay text
LEADING_ZERO_RE = re.compile(r"^[-+]?0\d")


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
    if LEADING_ZERO_RE.match(stripped):
        return value
    if THOUSANDS_RE.match(stripped):
        stripped = stripped.replace(",", "")
    elif not NUMBER_RE.match(stripped):
        return value
    number = float(stripped)
    return (
        int(number)
        if number.is_integer() and "." not in stripped and "e" not in lowered
        else number
    )


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


# Order matters: ties go to the first entry (cells often contain commas)
DELIMITERS = {"tsv": "\t", "csv": ",", "ssv": ";"}


def detect_format(text: str) -> str:
    """Guess whether pasted text is JSON, CSV, TSV or semicolon-separated.

    Spreadsheets (Excel, Google Sheets, Numbers) copy cells as TSV, so the
    delimiter is whichever of tab/comma/semicolon is most common in the
    header row.
    """
    text = text.lstrip("\ufeff\r\n ")
    if text[:1] in ("[", "{"):
        return "json"
    header = text.split("\n", 1)[0]
    counts = {fmt: header.count(d) for fmt, d in DELIMITERS.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] else "csv"


def parse_text(text: str | None) -> list[Any]:
    """Parse pasted data in any supported format."""
    text = (text or "").lstrip("\ufeff")
    if not text.strip():
        return []
    fmt = detect_format(text)
    if fmt == "json":
        return parse_json(text)
    return parse_delimited(text, DELIMITERS[fmt])


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
