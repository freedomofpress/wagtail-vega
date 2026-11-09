import pytest
from django.core.exceptions import ImproperlyConfigured

from wagtail_vega.themes import build_theme, get_theme, resolve_css_vars, theme_choices

PRINT_THEME = {"font": "Times"}


def test_plain_dict_is_config():
    theme = build_theme("t", {"font": "Inter"})
    assert theme.config == {"font": "Inter"} and theme.dark is None


def test_full_definition():
    theme = build_theme(
        "t", {"label": "T", "config": {"a": 1}, "dark": {"b": 2}, "fallbacks": {"--x": "red"}}
    )
    assert (theme.label, theme.config, theme.dark, theme.fallbacks) == (
        "T",
        {"a": 1},
        {"b": 2},
        {"--x": "red"},
    )


def test_builtin_and_dotted_path():
    assert build_theme("d", "vega:dark").vega_theme == "dark"
    assert build_theme("p", "tests.test_themes.PRINT_THEME").config == {"font": "Times"}


def test_bad_definitions():
    with pytest.raises(ImproperlyConfigured):
        build_theme("x", "tests.nope.THEME")
    with pytest.raises(ImproperlyConfigured):
        build_theme("x", {"config": {}, "colour": 1})


def test_get_theme_default(vega_settings):
    vega_settings.update(THEMES={"a": {"font": "A"}, "b": {"font": "B"}}, DEFAULT_THEME="a")
    assert get_theme(None).name == "a"
    assert get_theme("b").name == "b"
    assert get_theme("missing").name == "a"
    assert theme_choices() == [("", "Site default (a)"), ("a", "a"), ("b", "b")]


def test_get_theme_none(vega_settings):
    assert get_theme(None) is None


def test_bad_default(vega_settings):
    vega_settings.update(DEFAULT_THEME="nope")
    with pytest.raises(ImproperlyConfigured):
        get_theme(None)


def test_resolve_css_vars():
    value = {"range": ["var(--a)", "var(--b, #000)", "var(--c)", "plain"]}
    assert resolve_css_vars(value, {"--a": "red"}) == {
        "range": ["red", "#000", "var(--c)", "plain"]
    }
