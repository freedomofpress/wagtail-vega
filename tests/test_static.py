"""The package's static files work with ManifestStaticFilesStorage, which many
production sites use. It fails collectstatic on any reference it can't
resolve, such as a sourceMappingURL to a map that isn't vendored."""

from pathlib import Path

from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management import call_command

PACKAGE_STATIC = Path(__file__).parent.parent / "wagtail_vega" / "static"


def test_collectstatic_with_manifest_storage(settings, tmp_path):
    settings.STATIC_ROOT = tmp_path
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
    }
    call_command("collectstatic", interactive=False, verbosity=0)

    # Every file the package ships made it into the manifest, hashed
    shipped = [
        p.relative_to(PACKAGE_STATIC).as_posix() for p in PACKAGE_STATIC.rglob("*") if p.is_file()
    ]
    assert "wagtail_vega/vendor/vega-lite.min.js" in shipped
    assert "wagtail_vega/admin/chart-builder.js" in shipped
    assert "wagtail_vega/vendor/voyager/voyager.js" in shipped
    assert "wagtail_vega/vendor/voyager/voyager.css" in shipped
    for name in shipped:
        hashed = staticfiles_storage.stored_name(name)
        assert hashed != name, name
        assert (tmp_path / hashed).is_file(), name


def test_no_dangling_source_maps():
    """Shipped scripts and styles don't point at maps that aren't shipped."""
    for path in PACKAGE_STATIC.rglob("*"):
        if path.suffix not in (".js", ".css"):
            continue
        text = path.read_text(errors="replace")
        for line in text.splitlines():
            if "sourceMappingURL=" in line and not line.strip().startswith(
                "//# sourceMappingURL=data:"
            ):
                target = line.split("sourceMappingURL=", 1)[1].split()[0].rstrip("*/")
                assert (path.parent / target).is_file(), f"{path}: {target}"
