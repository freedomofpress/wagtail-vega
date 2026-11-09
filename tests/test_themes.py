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


def test_resolve_css_vars_leaves_data_alone():
    spec = {
        "mark": {"color": "var(--a)"},
        "data": {"values": [{"label": "var(--a)"}]},
        "datasets": {"s": [{"label": "var(--a)"}]},
        "layer": [{"data": {"values": ["var(--a)"]}, "encoding": {"color": {"value": "var(--a)"}}}],
    }
    out = resolve_css_vars(spec, {"--a": "red"})
    assert out["mark"]["color"] == "red"
    assert out["layer"][0]["encoding"]["color"]["value"] == "red"
    assert out["data"] == spec["data"]
    assert out["datasets"] == spec["datasets"]
    assert out["layer"][0]["data"] == spec["layer"][0]["data"]


def test_plain_dict_label_is_kept_out_of_the_config():
    theme = build_theme("print", {"label": "Print", "font": "Times"})
    assert theme.label == "Print"
    assert theme.config == {"font": "Times"}


def test_missing_theme_is_logged(vega_settings, caplog):
    vega_settings.update(THEMES={"a": {"font": "A"}}, DEFAULT_THEME="a")
    assert get_theme("removed").name == "a"
    assert "'removed' isn't in THEMES" in caplog.text


# -- System checks (#7) ---------------------------------------------------------


def test_checks_pass_for_valid_settings(vega_settings):
    from wagtail_vega.checks import check_themes

    vega_settings.update(THEMES={"a": {"font": "A"}, "b": "vega:dark"}, DEFAULT_THEME="a")
    assert check_themes() == []


def test_checks_report_bad_themes_and_default(vega_settings):
    from wagtail_vega.checks import check_themes

    vega_settings.update(THEMES={"ok": {}, "bad": "no.such.module.THEME"}, DEFAULT_THEME="nope")
    errors = {e.id: e for e in check_themes()}
    assert set(errors) == {"wagtail_vega.E001", "wagtail_vega.E002"}
    assert "no.such.module" in errors["wagtail_vega.E001"].msg
    assert "'nope'" in errors["wagtail_vega.E002"].msg
    assert "bad, ok" in errors["wagtail_vega.E002"].hint


def test_block_meta_theme_is_checked(vega_settings):
    from wagtail_vega.blocks import ChartBlock

    vega_settings.update(THEMES={"house": {}})

    class Typo(ChartBlock):
        class Meta:
            theme = "hosue"

    class Fine(ChartBlock):
        class Meta:
            theme = "house"

    errors = Typo().check()
    assert [e.id for e in errors] == ["wagtail_vega.E003"]
    assert "'hosue'" in errors[0].msg
    assert Fine().check() == []


@pytest.mark.django_db
def test_django_check_command_runs_our_checks(vega_settings):
    from django.core.management import call_command
    from django.core.management.base import SystemCheckError

    vega_settings.update(THEMES={}, DEFAULT_THEME="missing")
    with pytest.raises(SystemCheckError, match="wagtail_vega.E002"):
        call_command("check")


def test_dark_fallbacks():
    theme = build_theme(
        "t", {"config": {"background": "var(--bg, white)"}, "dark_fallbacks": {"--bg": "#111"}}
    )
    assert theme.dark_fallbacks == {"--bg": "#111"} and theme.fallbacks == {}
    # A dict with only dark_fallbacks is a theme definition, not a Vega config
    assert build_theme("t", {"dark_fallbacks": {"--bg": "#111"}}).config == {}
