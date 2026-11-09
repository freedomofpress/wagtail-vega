import pytest

from wagtail_vega.spec import SpecError
from wagtail_vega.validation import validate_spec


def test_valid_specs(vl_bar, vg_bar):
    assert validate_spec(vl_bar) == []
    assert validate_spec(vg_bar) == []


def test_invalid_vega_lite_points_at_field(vl_bar):
    vl_bar["encoding"]["x"]["type"] = "nominl"
    errors = validate_spec(vl_bar)
    assert errors and errors[0].startswith("encoding.x.type:")


def test_invalid_vega(vg_bar):
    vg_bar["width"] = "wide"
    assert any(e.startswith("width:") for e in validate_spec(vg_bar))


def test_missing_schema():
    with pytest.raises(SpecError):
        validate_spec({"mark": "bar"})
