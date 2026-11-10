"""StreamField blocks for Vega / Vega-Lite charts.

``ChartBlock`` is the editor-facing block: editors paste a spec and attach
named datasets (pasted CSV/TSV/JSON, a document, or an allowlisted URL).

``BaseChartBlock`` is the extension point for developers. Subclass it and
override ``get_datasets()`` to supply data from anywhere, e.g. the database::

    class DonationsChartBlock(BaseChartBlock):
        def get_datasets(self, value, context=None):
            return {"source": list(Donation.objects.values("month", "total"))}

The spec refers to datasets by name: ``{"data": {"name": "source"}}``.

``DatasetBlock`` is the extension point for new kinds of data that editors
choose per dataset, next to Paste / Document / URL: see its
``source_fields``, ``clean_source()`` and ``get_source_dataset()``.
"""

from __future__ import annotations

import collections
import json
import logging
import secrets
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django import forms
from django.core import checks
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, URLValidator
from django.forms.fields import InvalidJSONInput
from django.forms.utils import ErrorList
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import json_script
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.admin.telepath import register
from wagtail.blocks.field_block import FieldBlockAdapter
from wagtail.blocks.struct_block import StructBlockAdapter, StructBlockValidationError
from wagtail.documents.blocks import DocumentChooserBlock

from . import ssr
from .conf import DEFAULTS, get_allowed_hosts, get_setting
from .data import DOCUMENT_SUFFIXES, document_rows, parse_text
from .encoders import VegaJSONEncoder
from .spec import (
    dataset_references,
    deep_merge,
    host_allowed,
    inject_datasets,
    is_remote,
    normalize_url,
    remote_data,
    spec_kind,
)
from .themes import Theme, get_theme, resolve_css_vars, theme_choices
from .validation import SpecProblem, spec_problems
from .widgets import EDITOR_JS, CodeEditor, admin_js

logger = logging.getLogger(__name__)


class FieldOrderMixin:
    """Lets a StructBlock subclass set ``field_order``: a tuple of child block
    names shown first, in that order. Unlisted fields follow in declaration
    order, and names the block doesn't have are ignored. Subclasses inherit
    the order."""

    field_order: tuple[str, ...] = ()

    def __init__(self, *args, **kwargs):
        if self.field_order:
            # StructBlock.__init__ copies base_blocks, so an instance attribute
            # set here decides the order on all supported Wagtail versions.
            declared = type(self).base_blocks
            names = [n for n in self.field_order if n in declared]
            names += [n for n in declared if n not in names]
            self.base_blocks = collections.OrderedDict((n, declared[n]) for n in names)
        super().__init__(*args, **kwargs)


# --------------------------------------------------------------------------
# JSON input
# --------------------------------------------------------------------------


class PrettyJSONField(forms.JSONField):
    def prepare_value(self, value):
        if isinstance(value, InvalidJSONInput):
            return value
        if value is None:
            # An empty field, not the JSON text "null"
            return ""
        return json.dumps(value, indent=2, ensure_ascii=False, cls=self.encoder)


class JSONBlock(blocks.FieldBlock):
    """JSON in a code editor, stored as native JSON in the StreamField."""

    editor_mode = "json"
    builder = False

    def __init__(
        self, required=True, help_text=None, rows=16, validators=(), placeholder=None, **kwargs
    ):
        attrs = {"rows": rows, "class": "wagtail-vega-json"}
        if placeholder:
            # Shown in the code editor while it's empty
            attrs["placeholder"] = placeholder
        self.field = PrettyJSONField(
            required=required,
            help_text=help_text,
            validators=validators,
            encoder=VegaJSONEncoder,
            widget=CodeEditor(mode=self.editor_mode, attrs=attrs, builder=self.builder),
        )
        super().__init__(**kwargs)

    def value_from_form(self, value):
        if isinstance(value, str) and not isinstance(value, InvalidJSONInput):
            if not value.strip():
                return None
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # Keep the editor's text so it is redisplayed with the error
                return InvalidJSONInput(value)
        return value

    def get_searchable_content(self, value):
        return []

    class Meta:
        icon = "code"


SPEC_PLACEHOLDER = _(
    """Paste a spec here. For example, a bar chart of the dataset called "source":

{
  "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
  "data": {"name": "source"},
  "mark": "bar",
  "encoding": {
    "x": {"field": "quarter", "type": "nominal"},
    "y": {"field": "requests", "type": "quantitative"}
  }
}"""
)


class SpecBlock(JSONBlock):
    """A Vega or Vega-Lite specification, validated on save (and live, in the
    editor)."""

    editor_mode = "spec"

    def __init__(self, builder=True, **kwargs):
        # The field shows the chart and an "Edit chart" button that opens
        # the chart editor (see widgets.CodeEditor); builder=False leaves
        # them out and shows the code editor inline.
        self.builder = builder
        kwargs.setdefault(
            "help_text",
            _(
                "The chart's Vega-Lite or Vega spec, in JSON. Load a dataset by its name, "
                'e.g. "data": {"name": "source"}.'
            ),
        )
        kwargs.setdefault("placeholder", SPEC_PLACEHOLDER)
        super().__init__(**kwargs)

    def clean(self, value):
        value = super().clean(value)
        if value is None:
            return value
        problems = spec_problems(value)
        if problems:
            raise ValidationError([str(p) for p in problems])
        return value


class CodeFieldBlockAdapter(FieldBlockAdapter):
    """Passes the block's server-side errors to its code editor, which
    highlights each one at the JSON path it starts with."""

    js_constructor = "wagtail_vega.blocks.CodeFieldBlock"

    @cached_property
    def media(self):
        return super().media + forms.Media(js=admin_js(EDITOR_JS))


register(CodeFieldBlockAdapter(), JSONBlock)


# --------------------------------------------------------------------------
# Data sources
# --------------------------------------------------------------------------

PASTE, DOCUMENT, URL = "paste", "document", "url"
#: The built-in sources, as ``(value, label)`` choices for ``source_type``.
#: Extend it to add a source: ``[*SOURCE_CHOICES, ("incidents", "Incidents")]``.
SOURCE_CHOICES = [(PASTE, _("Paste")), (DOCUMENT, _("Document")), (URL, _("URL"))]
#: The built-in sources' fields. ``DatasetBlock.source_fields`` is what's
#: used; this name is kept for compatibility.
SOURCE_FIELDS = {PASTE: ("paste",), DOCUMENT: ("document",), URL: ("url", "format")}


def validate_data_url(value):
    """Accept http(s) URLs and site-relative paths ("/media/data.csv"),
    judged as the browser will see them (see ``spec.normalize_url``)."""
    url = normalize_url(value)
    if url.startswith("/") and not url.startswith("//"):
        return
    URLValidator(schemes=["http", "https"])(url)


class DataURLBlock(blocks.CharBlock):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 2000)
        kwargs.setdefault("validators", [validate_data_url])
        kwargs.setdefault(
            "help_text",
            _("A full URL on an allowed host, or a path on this site such as /media/data.csv."),
        )
        super().__init__(**kwargs)


PASTE_PLACEHOLDER = _("For example:\n\nquarter,requests\nQ1,1120\nQ2,1340")


class PastedDataBlock(blocks.TextBlock):
    """Pasted CSV, TSV or JSON, edited in a code editor that shows tabs, doesn't
    wrap lines, and marks ragged rows and JSON errors."""

    @cached_property
    def field(self):
        attrs = {"rows": self.rows, "placeholder": PASTE_PLACEHOLDER}
        widget = CodeEditor(mode="data", attrs=attrs)
        return forms.CharField(widget=widget, **self.field_options)

    def deconstruct(self):
        # Only the widget differs from TextBlock, so migrations record a
        # TextBlock. Projects that used DatasetBlock before PastedDataBlock
        # existed then don't get a no-op migration.
        _path, args, kwargs = super().deconstruct()
        return "wagtail.blocks.TextBlock", args, kwargs


class DocumentDataBlock(DocumentChooserBlock):
    def clean(self, value):
        value = super().clean(value)
        if value and not value.file.name.lower().endswith(DOCUMENT_SUFFIXES):
            raise ValidationError(_("Choose a .csv, .tsv or .json document."))
        return value


class DatasetBlock(FieldOrderMixin, blocks.StructBlock):
    """A named dataset. Editors pick where the data comes from with a
    Paste / Document / URL toggle; only the matching inputs are shown.

    To add a source of your own, subclass it and:

    - add the source to the ``source_type`` choices (see ``SOURCE_CHOICES``),
      and its fields to ``source_fields``;
    - return its rows from ``get_source_dataset()``, and check its fields in
      ``clean_source()`` if they need it;
    - optionally, name an admin URL that returns its rows in
      ``source_rows_urls`` (see ``wagtail_vega.views.SourceRowsView``), so
      editors see a summary of the data and can build charts from it.

    Set ``field_order`` to show your fields next to the source toggle. See
    "Custom source types for editors" in the docs.
    """

    #: Each source's fields: ``{source: (field name, ...)}``. When a dataset
    #: is saved, the fields of every source but the selected one are reset to
    #: their defaults (except fields the selected source uses too), and the
    #: admin form only shows the selected source's fields.
    source_fields: dict[str, tuple[str, ...]] = SOURCE_FIELDS

    #: Admin URLs that return a source's rows, for the dataset's summary and
    #: the chart editor: ``{source: URL name}``, or a path starting with "/".
    #: URL names are resolved with ``reverse()`` when the form is built. The
    #: built-in sources don't need one.
    source_rows_urls: dict[str, str] = {}

    name = blocks.CharBlock(
        default="source",
        max_length=64,
        validators=[
            RegexValidator(
                r"^[A-Za-z_][\w-]*$",
                _("Use letters, numbers, hyphens and underscores, starting with a letter."),
            )
        ],
        help_text=_('The name the spec uses to refer to this data, e.g. "source".'),
    )
    source_type = blocks.ChoiceBlock(
        choices=SOURCE_CHOICES,
        default=PASTE,
        widget=forms.RadioSelect,
        label=_("Source"),
    )
    paste = PastedDataBlock(
        required=False,
        rows=8,
        label=_("Pasted data"),
        help_text=_(
            "Paste CSV, JSON, or cells copied from a spreadsheet. "
            "The first row must be the column names."
        ),
        form_classname="wagtail-vega-paste",
    )
    document = DocumentDataBlock(
        required=False, help_text=_("A .csv, .tsv or .json file with a header row.")
    )
    url = DataURLBlock(required=False, label=_("URL"))
    format = blocks.ChoiceBlock(
        choices=[
            ("", _("Detect from the URL")),
            ("csv", "CSV"),
            ("tsv", "TSV"),
            ("json", "JSON"),
        ],
        required=False,
    )

    class Meta:
        icon = "table"
        label = _("Dataset")
        form_classname = "wagtail-vega-dataset"

    def get_source(self, value) -> str:
        """The selected source (``"paste"`` if none is)."""
        return value.get("source_type") or PASTE

    def clean(self, value):
        value = super().clean(value)
        source = self.get_source(value)
        errors = self.clean_source(source, value)
        if errors:
            raise StructBlockValidationError(block_errors=errors)

        # Reset the other sources' inputs, so stale data isn't kept
        keep = set(self.source_fields.get(source, ()))
        for other, names in self.source_fields.items():
            if other == source:
                continue
            for name in names:
                if name not in keep and name in self.child_blocks:
                    value[name] = self.child_blocks[name].get_default()
        return value

    def clean_source(self, source: str, value) -> dict[str, ValidationError]:
        """Check the selected ``source``'s inputs, after each field's own
        validation. Returns ``{field name: ValidationError}``, empty if all is
        well; each error is shown on its field.

        The built-in sources require their data (and an allowed host, for a
        URL). Any other source needs no validation unless you add it: override
        this, check your source, and call ``super()`` for the others."""
        errors = {}
        if source == PASTE:
            try:
                if not parse_text(value["paste"]):
                    errors["paste"] = ValidationError(
                        _("Paste a header row followed by data rows.")
                    )
            except (ValidationError, json.JSONDecodeError) as e:
                errors["paste"] = ValidationError(_("Couldn't read this data: %s") % e)
        elif source == DOCUMENT:
            if not value["document"]:
                errors["document"] = ValidationError(_("Select a document to load data from."))
        elif source == URL:
            if not value["url"]:
                errors["url"] = ValidationError(_("Enter a URL."))
            elif not host_allowed(value["url"], get_allowed_hosts()):
                errors["url"] = ValidationError(_("Data can't be loaded from this host."))
        return errors

    def get_dataset(self, value):
        """The dataset for the chart: what ``get_source_dataset()`` returns
        for the selected source."""
        return self.get_source_dataset(self.get_source(value), value)

    def get_source_dataset(self, source: str, value):
        """The data for ``source``: a list of rows, or a remote dataset (see
        "The dataset format" in the docs). Override this to handle your own
        sources, and call ``super()`` for the others.

        A source that nothing handles has no rows, and logs a warning."""
        if source == PASTE:
            return parse_text(value["paste"])
        if source == DOCUMENT:
            return document_rows(value["document"]) if value["document"] else []
        if source == URL:
            return remote_data(value["url"], value["format"] or None)
        logger.warning(
            "wagtail-vega: %s.get_source_dataset() doesn't handle source %r; the dataset is empty.",
            type(self).__name__,
            source,
        )
        return []

    def check(self, **kwargs):
        """System checks: the ``source_type`` choices and ``source_fields``
        name the same sources, and ``source_fields`` and
        ``source_rows_urls`` only name fields and sources the block has."""
        errors = super().check(**kwargs)
        obj = kwargs.get("field", self)
        name = type(self).__name__
        sources = set(self.source_fields)
        choice_block = self.child_blocks.get("source_type")
        if choice_block is not None:
            choices = set()
            for key, label in choice_block.field.choices:
                if isinstance(label, list | tuple):  # an option group
                    choices.update(k for k, _label in label)
                else:
                    choices.add(key)
            choices.discard("")
            if choices != sources:
                details = []
                if missing := sorted(choices - sources):
                    details.append("no source_fields for " + ", ".join(map(repr, missing)))
                if extra := sorted(sources - choices):
                    details.append("no source_type choice for " + ", ".join(map(repr, extra)))
                errors.append(
                    checks.Error(
                        f"{name}'s source_type choices don't match its source_fields: "
                        + "; ".join(details)
                        + ".",
                        hint="Give each source a source_type choice and a source_fields "
                        "entry (an empty tuple if it has no fields).",
                        obj=obj,
                        id="wagtail_vega.E004",
                    )
                )
        for source, names in self.source_fields.items():
            for field_name in names:
                if field_name not in self.child_blocks:
                    errors.append(
                        checks.Error(
                            f"{name}.source_fields[{source!r}] names {field_name!r}, "
                            f"which isn't a field of {name}.",
                            hint="Add the field to the block, or remove it from source_fields.",
                            obj=obj,
                            id="wagtail_vega.E005",
                        )
                    )
        for source in self.source_rows_urls:
            if source not in sources:
                errors.append(
                    checks.Error(
                        f"{name}.source_rows_urls has a URL for {source!r}, "
                        "which isn't in its source_fields.",
                        hint="Remove it, or add the source to source_fields.",
                        obj=obj,
                        id="wagtail_vega.E006",
                    )
                )
        return errors


class DatasetBlockAdapter(StructBlockAdapter):
    """Dataset blocks in the admin (``dataset-block.js``).

    The block's ``source_fields`` and its resolved ``source_rows_urls`` go to
    the form script in ``meta["wagtailVega"]``, so a new source's fields are
    shown and hidden, summarised and previewed with no extra script.

    To load a script of your own for a ``DatasetBlock`` subclass, such as
    one that calls ``wagtailVegaAdmin.registerSource()``, register a
    subclass of this adapter for your block and list the script in
    ``extra_js``, which is loaded after wagtail-vega's scripts::

        class IncidentDatasetBlockAdapter(DatasetBlockAdapter):
            extra_js = ["tracker/admin/incident-source.js"]

        register(IncidentDatasetBlockAdapter(), IncidentDatasetBlock)
    """

    js_constructor = "wagtail_vega.blocks.DatasetBlock"

    #: Scripts (static paths or URLs) loaded after ``dataset-block.js``.
    extra_js: tuple[str, ...] = ()
    #: Stylesheets loaded after ``dataset-block.css``.
    extra_css: tuple[str, ...] = ()

    def js_args(self, block):
        name, children, meta = super().js_args(block)
        meta = {
            **meta,
            "wagtailVega": {
                "sourceFields": {s: list(names) for s, names in block.source_fields.items()},
                "rowsUrls": {
                    s: url if url.startswith("/") else reverse(url)
                    for s, url in block.source_rows_urls.items()
                },
            },
        }
        return [name, children, meta]

    @cached_property
    def media(self):
        # One list, in order. Adding Media objects together wouldn't keep
        # extra_js after dataset-block.js: Django's merge only keeps the
        # relative order of scripts that are in both lists.
        media = super().media
        return forms.Media(
            js=[
                *media._js,
                *admin_js(
                    [
                        "wagtail_vega/admin/json-source.js",
                        "wagtail_vega/admin/data-format.js",
                        "wagtail_vega/admin/sources.js",
                        "wagtail_vega/admin/dataset-block.js",
                    ]
                ),
                *self.extra_js,
            ],
            css={"all": ["wagtail_vega/admin/dataset-block.css", *self.extra_css]},
        )


register(DatasetBlockAdapter(), DatasetBlock)


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------


@dataclass
class Chart:
    """Everything the chart template needs."""

    id: str
    kind: str
    spec: dict
    embed_options: dict
    description: str = ""
    caption: str = ""
    dark_config: dict | None = None
    fallbacks: dict = field(default_factory=dict)
    dark_fallbacks: dict = field(default_factory=dict)
    svg: str | None = None
    tables: list[dict] = field(default_factory=list)

    @property
    def payload_id(self) -> str:
        return f"{self.id}-payload"

    @property
    def payload(self) -> dict:
        return {
            "spec": self.spec,
            "darkConfig": self.dark_config,
            "embed": self.embed_options,
            "fallbacks": self.fallbacks,
            "darkFallbacks": self.dark_fallbacks,
            "allowedHosts": get_allowed_hosts(),
            "cspSafe": bool(get_setting("CSP_SAFE")),
        }

    @property
    def payload_script(self) -> str:
        return json_script(self.payload, self.payload_id, encoder=VegaJSONEncoder)


def build_tables(datasets: dict[str, Any], max_rows: int) -> list[dict]:
    tables = []
    for name, rows in datasets.items():
        if is_remote(rows) or not rows or not all(isinstance(r, dict) for r in rows):
            continue
        columns: list[str] = []
        for row in rows:
            columns.extend(k for k in row if k not in columns)
        shown = [[row.get(c) for c in columns] for row in rows[:max_rows]]
        numeric = [_is_numeric_column([r[i] for r in shown]) for i in range(len(columns))]
        tables.append(
            {
                "name": name,
                "columns": columns,
                "rows": shown,
                # As columns and rows, with whether each column holds numbers
                # (the template right-aligns them, so their digits line up)
                "head": [{"name": c, "numeric": n} for c, n in zip(columns, numeric, strict=True)],
                "cells": [
                    [{"value": v, "numeric": n} for v, n in zip(row, numeric, strict=True)]
                    for row in shown
                ],
                "truncated": len(rows) > max_rows,
                "total": len(rows),
            }
        )
    return tables


def _is_numeric_column(values: list[Any]) -> bool:
    """Whether every value that isn't blank is a number (not a boolean)."""
    present = [v for v in values if v is not None and v != ""]
    return bool(present) and all(
        isinstance(v, int | float | Decimal) and not isinstance(v, bool) for v in present
    )


class BaseChartBlock(FieldOrderMixin, blocks.StructBlock):
    """A chart built from a Vega / Vega-Lite spec.

    Override the ``get_*`` hooks to customise behaviour. ``Meta`` options:

    - ``theme``: theme name, overriding the editor's choice and the default
    - ``ssr``: render an SVG on the server (defaults to the SSR setting)
    - ``fallback_table``: render a data table (defaults to FALLBACK_TABLE)
    - ``embed_options``: extra vega-embed options

    Set ``field_order`` to a tuple of child block names to control the order
    of fields in the editor (unlisted fields follow in declaration order).
    """

    field_order: tuple[str, ...] = ()

    spec = SpecBlock()
    description = blocks.TextBlock(
        required=False,
        rows=2,
        help_text=_(
            "What the chart shows, and what readers should take from it, e.g. "
            '"Requests rose every quarter, from 1,120 to 1,460." '
            "Read out by screen readers; not shown on the page."
        ),
    )
    caption = blocks.CharBlock(
        required=False,
        help_text=_("Shown under the chart: a title, the source of the data, or notes."),
    )

    class Meta:
        icon = "wagtail-vega-chart"
        label = _("Chart")
        description = _("A chart drawn from data, with a description and a caption.")
        template = "wagtail_vega/chart.html"
        theme = None
        ssr = None
        fallback_table = None
        embed_options = None

    # -- hooks --------------------------------------------------------------

    def get_spec_source(self, value) -> dict:
        """The spec before data and theming are applied."""
        return value["spec"]

    def get_datasets(self, value, context=None) -> dict[str, Any]:
        """Return ``{name: rows}`` or ``{name: {"url": ..., "format": {...}}}``."""
        return {}

    def get_theme(self, value, context=None) -> Theme | None:
        return get_theme(self.meta.theme or value.get("theme"))

    def check(self, **kwargs):
        errors = super().check(**kwargs)
        if self.meta.theme and self.meta.theme not in get_setting("THEMES"):
            errors.append(
                checks.Error(
                    f"{type(self).__name__} uses theme {self.meta.theme!r}, "
                    "which isn't in WAGTAIL_VEGA['THEMES'].",
                    hint="Fix Meta.theme, or add the theme to the THEMES setting.",
                    obj=kwargs.get("field", self),
                    id="wagtail_vega.E003",
                )
            )
        return errors

    def get_embed_options(self, value, context=None, theme=None) -> dict:
        """vega-embed options: the defaults, then the ``EMBED_OPTIONS``
        setting, then ``Meta.embed_options``, each merged over the last.

        vega-embed's own styles ship in ``wagtail-vega.css`` rather than being
        injected at runtime (which a strict CSP would block), so
        ``defaultStyle`` is always off. Tooltip options (a dict) are kept,
        with vega-tooltip's style injection turned off for the same reason;
        ``"tooltip": False`` turns tooltips off.
        """
        options = {
            **DEFAULTS["EMBED_OPTIONS"],
            **get_setting("EMBED_OPTIONS"),
            **(self.meta.embed_options or {}),
            "defaultStyle": False,
        }
        tooltip = options.get("tooltip", True)
        if tooltip is not False:
            options["tooltip"] = {
                **(tooltip if isinstance(tooltip, dict) else {}),
                "disableDefaultStyle": True,
            }
        if theme and theme.vega_theme:
            options["theme"] = theme.vega_theme
        return options

    def get_spec(self, value, context=None, datasets=None, theme=None, dark=False):
        """The final spec: datasets injected and theme config merged in. The
        spec's own ``config`` wins over the theme."""
        spec = self.get_spec_source(value)
        if datasets is None:
            datasets = self.get_datasets(value, context)
        spec = inject_datasets(spec, datasets)
        if theme:
            layers = [theme.config, theme.dark if dark else None, spec.get("config")]
            config = deep_merge(*layers)
            if config:
                spec["config"] = config
        return spec

    def use_ssr(self, value) -> bool:
        return get_setting("SSR") if self.meta.ssr is None else self.meta.ssr

    def use_fallback_table(self, value) -> bool:
        if self.meta.fallback_table is None:
            return get_setting("FALLBACK_TABLE")
        return self.meta.fallback_table

    # -- rendering ----------------------------------------------------------

    def build_chart(self, value, context=None, *, for_page=True) -> Chart:
        """Everything needed to render the chart. With ``for_page=False``, the
        page-only extras (server-rendered SVG and fallback tables) are
        skipped."""
        theme = self.get_theme(value, context)
        datasets = self.get_datasets(value, context)
        self.check_remote_datasets(datasets)
        spec = self.get_spec(value, context, datasets=datasets, theme=theme)
        kind = spec_kind(spec)

        chart = Chart(
            id=f"wagtail-vega-{secrets.token_hex(4)}",
            kind=kind,
            spec=spec,
            embed_options=self.get_embed_options(value, context, theme=theme),
            description=value.get("description") or "",
            caption=value.get("caption") or "",
        )
        if theme:
            chart.fallbacks = theme.fallbacks
            chart.dark_fallbacks = theme.dark_fallbacks
            if theme.dark:
                dark = self.get_spec(value, context, datasets, theme, dark=True)
                chart.dark_config = dark.get("config")
        if not for_page:
            return chart
        if self.use_ssr(value):
            fallbacks = theme.fallbacks if theme else {}
            chart.svg = ssr.render_svg(
                resolve_css_vars(spec, fallbacks),
                kind,
                vega_theme=theme.vega_theme if theme else None,
            )
        if self.use_fallback_table(value):
            chart.tables = build_tables(datasets, get_setting("FALLBACK_TABLE_MAX_ROWS"))
        return chart

    def check_remote_datasets(self, datasets) -> None:
        """Warn about remote datasets on hosts that aren't allowed.

        Editors' URLs are checked when they save. URLs that ``get_datasets()``
        returns from code aren't, and would only fail in readers' browsers, so
        log them where the developer will see them.
        """
        allowed = get_allowed_hosts()
        for name, dataset in datasets.items():
            if is_remote(dataset) and not host_allowed(dataset["url"], allowed):
                logger.warning(
                    "wagtail-vega: %s.get_datasets() returned dataset %r with URL %s, "
                    "whose host isn't in ALLOWED_DATA_HOSTS; browsers will refuse to load it.",
                    type(self).__name__,
                    name,
                    dataset["url"],
                )

    def get_api_representation(self, value, context=None):
        """The chart as Wagtail's API returns it: the final spec (datasets
        injected, theme merged) and everything else the page's script gets,
        so a headless frontend can render it with vega-embed."""
        chart = self.build_chart(value, context, for_page=False)
        return json.loads(
            json.dumps(
                {
                    "kind": chart.kind,
                    **chart.payload,
                    "description": chart.description,
                    "caption": chart.caption,
                },
                cls=VegaJSONEncoder,
            )
        )

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)
        context["chart"] = self.build_chart(value, parent_context)
        return context


class ChartBlockAdapter(StructBlockAdapter):
    """Chart blocks in the admin: a collapsed chart is labelled with its
    title, caption or description, and the spec editor warns, as you type,
    about datasets the spec loads that the chart doesn't have."""

    js_constructor = "wagtail_vega.blocks.ChartBlock"

    def js_args(self, block):
        name, children, meta = super().js_args(block)
        meta = {
            **meta,
            "wagtailVega": {
                "missingDataset": missing_dataset_messages(),
                "extraDatasetNames": list(getattr(block, "extra_dataset_names", ())),
            },
        }
        return [name, children, meta]

    @cached_property
    def media(self):
        return super().media + forms.Media(js=["wagtail_vega/admin/chart-block.js"])


register(ChartBlockAdapter(), BaseChartBlock)


def missing_dataset_messages() -> dict[str, str]:
    """The message for a spec that loads a dataset the chart doesn't have,
    with and without other datasets to suggest. ``%(name)s`` is the missing
    name, ``%(names)s`` the chart's dataset names. Also used live, by the
    admin's spec editor (chart-block.js)."""
    return {
        "none": _('This chart has no dataset called "%(name)s". Add one under Data.'),
        "some": _(
            'This chart has no dataset called "%(name)s". Use one of its datasets '
            "(%(names)s), or add one under Data."
        ),
    }


def missing_dataset_problems(spec, names) -> list[SpecProblem]:
    """A problem for each dataset the spec loads by name that isn't in
    ``names``."""
    messages = missing_dataset_messages()
    problems = []
    for path, name in dataset_references(spec):
        if name in names:
            continue
        message = messages["some" if names else "none"] % {
            "name": name,
            "names": ", ".join(names),
        }
        problems.append(SpecProblem(path, message))
    return problems


class ChartBlock(BaseChartBlock):
    """The editor-facing chart block: a spec plus named datasets."""

    field_order = ("data", "spec", "description", "caption", "theme")

    #: Names of datasets a subclass adds in ``get_datasets()`` on top of the
    #: editor's, so specs may load them without failing validation.
    extra_dataset_names: tuple[str, ...] = ()

    data = blocks.ListBlock(
        DatasetBlock(),
        min_num=0,
        help_text=_(
            "The data for this chart. Give each dataset a different name, and use "
            "that name in the spec."
        ),
    )
    theme = blocks.ChoiceBlock(choices=theme_choices, required=False)

    def get_datasets(self, value, context=None):
        dataset_block = self.child_blocks["data"].child_block
        return {item["name"]: dataset_block.get_dataset(item) for item in value["data"]}

    def clean(self, value):
        value = super().clean(value)
        names = [item["name"] for item in value["data"]]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise StructBlockValidationError(
                non_block_errors=ErrorList(
                    [ValidationError(_("Dataset names must be unique: %s") % ", ".join(duplicates))]
                )
            )
        missing = missing_dataset_problems(value["spec"], [*names, *self.extra_dataset_names])
        if missing:
            raise StructBlockValidationError(
                block_errors={"spec": ValidationError([str(p) for p in missing])}
            )
        return value

    class Meta:
        label = _("Chart")
