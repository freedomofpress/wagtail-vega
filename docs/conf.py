"""Sphinx configuration for the wagtail-vega documentation.

Build locally with::

    pip install -e ".[docs]"
    sphinx-build -W --keep-going -b html docs docs/_build/html
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# autodoc imports wagtail_vega, which needs a configured Django. The test
# project's settings are enough; nothing touches the database.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")

import django  # noqa: E402

django.setup()

import wagtail_vega  # noqa: E402

project = "wagtail-vega"
author = "Freedom of the Press Foundation"
copyright = "Freedom of the Press Foundation"
release = wagtail_vega.__version__
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_copybutton",
]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["_build"]

myst_enable_extensions = ["colon_fence", "deflist", "fieldlist"]
myst_heading_anchors = 3

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {"show-inheritance": True}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "django": (
        "https://docs.djangoproject.com/en/stable/",
        "https://docs.djangoproject.com/en/stable/_objects/",
    ),
    "wagtail": ("https://docs.wagtail.org/en/stable/", None),
}

# Code examples are copied without the shell prompt
copybutton_prompt_text = r"\$ "
copybutton_prompt_is_regexp = True

html_theme = "furo"
html_title = f"wagtail-vega {release}"
html_theme_options = {
    "source_repository": "https://github.com/freedomofpress/wagtail-vega/",
    "source_branch": "main",
    "source_directory": "docs/",
}

linkcheck_ignore = [
    # Local development server used in examples
    r"http://localhost:\d+",
]
# GitHub adds README heading anchors with JavaScript, so linkcheck can't see them
linkcheck_anchors_ignore_for_url = [r"https://github\.com/"]
