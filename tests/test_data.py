import pytest
from django.core.exceptions import ValidationError

from wagtail_vega.data import parse_bytes, parse_delimited, parse_json


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
