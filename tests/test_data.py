import pytest
from django.core.exceptions import ValidationError

from wagtail_vega.data import detect_format, parse_bytes, parse_delimited, parse_json, parse_text


def test_parse_csv_infers_types():
    rows = parse_delimited("a,b,c,d\nx,1,2.5,true\ny,,nan,2024-01-01\n")
    assert rows == [
        {"a": "x", "b": 1, "c": 2.5, "d": True},
        {"a": "y", "b": None, "c": "nan", "d": "2024-01-01"},
    ]


def test_parse_tsv_and_bom():
    assert parse_bytes("﻿a\tb\n1\t2\n".encode(), "x.tsv") == [{"a": 1, "b": 2}]


def test_parse_json():
    assert parse_json('[{"a": 1}]') == [{"a": 1}]
    assert parse_json({"values": [1]}) == [1]
    with pytest.raises(ValidationError):
        parse_json('{"a": 1}')


def test_parse_bytes_rejects_unknown_suffix():
    with pytest.raises(ValidationError):
        parse_bytes(b"", "x.xlsx")


@pytest.mark.parametrize(
    "text,fmt",
    [
        ("a,b\n1,2", "csv"),
        ("a\tb\n1\t2", "tsv"),
        ("a\tb,c\n1\t2", "tsv"),  # ties go to tabs: spreadsheet cells contain commas
        ("a;b;c\n1;2;3", "ssv"),
        ('﻿  [{"a": 1}]', "json"),
        ('{"values": []}', "json"),
        ("single\n1", "csv"),
    ],
)
def test_detect_format(text, fmt):
    assert detect_format(text) == fmt


def test_parse_text_spreadsheet_paste():
    text = "zip\tcount\tshare\n02134\t1,200\t12%\n10001\t950.5\t8%\n"
    assert parse_text(text) == [
        {"zip": "02134", "count": 1200, "share": "12%"},
        {"zip": 10001, "count": 950.5, "share": "8%"},
    ]


def test_parse_short_long_and_blank_rows():
    # Mirrored by parseRows in dataset-block.js (tests/js/dataset-block.test.mjs)
    assert parse_delimited("a,b\n1\n\n2,3,4\n") == [{"a": 1, "b": None}, {"a": 2, "b": 3}]


def test_parse_text_json_and_empty():
    assert parse_text('[{"a": 1}]') == [{"a": 1}]
    assert parse_text("   ") == [] and parse_text(None) == []


@pytest.mark.parametrize(
    "raw,value",
    [
        ("007", "007"),
        ("0", 0),
        ("0.5", 0.5),
        ("1e3", 1000.0),
        ("1_000", "1_000"),
        ("nan", "nan"),
        ("12,34", "12,34"),
        ("-1,234.5", -1234.5),
    ],
)
def test_coerce_edge_cases(raw, value):
    assert parse_delimited(f'x\n"{raw}"') == [{"x": value}]
