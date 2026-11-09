"""StreamField blocks for Vega / Vega-Lite charts.

``ChartBlock`` is the editor-facing block: editors paste a spec and attach
named datasets (CSV, JSON, a document, or an allowlisted URL).

``BaseChartBlock`` is the extension point for developers. Subclass it and
override ``get_datasets()`` to supply data from anywhere, e.g. the database::

    class DonationsChartBlock(BaseChartBlock):
        def get_datasets(self, value, context=None):
            return {"source": list(Donation.objects.values("month", "total"))}

The spec refers to datasets by name: ``{"data": {"name": "source"}}``.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.forms.fields import InvalidJSONInput
from django.forms.utils import ErrorList
from django.utils.html import json_script
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.documents.blocks import DocumentChooserBlock

from . import ssr
from .conf import get_setting
from .data import DOCUMENT_SUFFIXES, document_rows, parse_delimited, parse_json
from .encoders import VegaJSONEncoder
from .spec import (
    SpecError,
    deep_merge,
    disallowed_urls,
    host_allowed,
    inject_datasets,
    is_remote,
    remote_data,
    spec_kind,
)
from .themes import Theme, get_theme, resolve_css_vars, theme_choices
from .validation import validate_spec

# --------------------------------------------------------------------------
# JSON input
# --------------------------------------------------------------------------


class PrettyJSONField(forms.JSONField):
    def prepare_value(self, value):
        if isinstance(value, InvalidJSONInput):
            return value
        return json.dumps(value, indent=2, ensure_ascii=False, cls=self.encoder)


class JSONBlock(blocks.FieldBlock):
    """A textarea holding JSON, stored as native JSON in the StreamField."""

    def __init__(self, required=True, help_text=None, rows=16, validators=(), **kwargs):
        self.field = PrettyJSONField(
            required=required,
            help_text=help_text,
            validators=validators,
            encoder=VegaJSONEncoder,
            widget=forms.Textarea(
                attrs={
                    "rows": rows,
                    "class": "wagtail-vega-json",
                    "spellcheck": "false",
                    "autocomplete": "off",
                    "style": "font-family: monospace;",
                }
            ),
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


class SpecBlock(JSONBlock):
    """A Vega or Vega-Lite specification, validated on save."""

    def __init__(self, **kwargs):
        kwargs.setdefault(
            "help_text",
            _(
                "A Vega or Vega-Lite spec in JSON. Refer to datasets by name, e.g. "
                '"data": {"name": "source"}.'
            ),
        )
        super().__init__(**kwargs)

    def clean(self, value):
        value = super().clean(value)
        if value is None:
            return value
        if not isinstance(value, dict):
            raise ValidationError(_("The spec must be a JSON object."))
        try:
            spec_kind(value)
            errors = validate_spec(value) if get_setting("VALIDATE_SCHEMA") else []
        except SpecError as e:
            raise ValidationError(str(e)) from e
        blocked = disallowed_urls(value, get_setting("ALLOWED_DATA_HOSTS"))
        errors += [_("Loading data from %s is not allowed.") % url for url in blocked]
        if errors:
            raise ValidationError(errors)
        return value


# --------------------------------------------------------------------------
# Data sources
# --------------------------------------------------------------------------


class CSVDataBlock(blocks.TextBlock):
    def __init__(self, delimiter=",", **kwargs):
        self.delimiter = delimiter
        kwargs.setdefault("rows", 8)
        super().__init__(**kwargs)

    def clean(self, value):
        value = super().clean(value)
        if value and not parse_delimited(value, self.delimiter):
            raise ValidationError(_("Enter a header row followed by data rows."))
        return value

    def get_dataset(self, value):
        return parse_delimited(value or "", self.delimiter)

    class Meta:
        icon = "table"
        label = _("CSV")
        help_text = _("Comma-separated values with a header row.")


class JSONDataBlock(JSONBlock):
    def clean(self, value):
        value = super().clean(value)
        parse_json(value or [])
        return value

    def get_dataset(self, value):
        return parse_json(value or [])

    class Meta:
        icon = "code"
        label = _("JSON")


class DocumentDataBlock(DocumentChooserBlock):
    def clean(self, value):
        value = super().clean(value)
        if value and not value.file.name.lower().endswith(DOCUMENT_SUFFIXES):
            raise ValidationError(_("Choose a .csv, .tsv or .json document."))
        return value

    def get_dataset(self, value):
        return document_rows(value) if value else []

    class Meta:
        icon = "doc-full"
        label = _("Document")


class URLDataBlock(blocks.StructBlock):
    url = blocks.URLBlock()
    format = blocks.ChoiceBlock(
        choices=[("csv", "CSV"), ("tsv", "TSV"), ("json", "JSON")],
        required=False,
        help_text=_("Leave blank to infer from the URL."),
    )

    def clean(self, value):
        value = super().clean(value)
        if value["url"] and not host_allowed(value["url"], get_setting("ALLOWED_DATA_HOSTS")):
            raise StructBlockValidationError(
                block_errors={"url": ValidationError(_("Data can't be loaded from this host."))}
            )
        return value

    def get_dataset(self, value):
        return remote_data(value["url"], value["format"] or None)

    class Meta:
        icon = "link"
        label = _("URL")


class DataSourceBlock(blocks.StreamBlock):
    csv = CSVDataBlock()
    json = JSONDataBlock(rows=8)
    document = DocumentDataBlock()
    url = URLDataBlock()

    def get_dataset(self, value):
        for child in value:
            return child.block.get_dataset(child.value)
        return []

    class Meta:
        min_num = 1
        max_num = 1


class DatasetBlock(blocks.StructBlock):
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
    source = DataSourceBlock()

    def get_dataset(self, value):
        return self.child_blocks["source"].get_dataset(value["source"])

    class Meta:
        icon = "table"
        label = _("Dataset")


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
            "allowedHosts": list(get_setting("ALLOWED_DATA_HOSTS")),
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
        tables.append(
            {
                "name": name,
                "columns": columns,
                "rows": [[row.get(c) for c in columns] for row in rows[:max_rows]],
                "truncated": len(rows) > max_rows,
                "total": len(rows),
            }
        )
    return tables


class BaseChartBlock(blocks.StructBlock):
    """A chart built from a Vega / Vega-Lite spec.

    Override the ``get_*`` hooks to customise behaviour. ``Meta`` options:

    - ``theme``: theme name, overriding the editor's choice and the default
    - ``ssr``: render an SVG on the server (defaults to the SSR setting)
    - ``fallback_table``: render a data table (defaults to FALLBACK_TABLE)
    - ``embed_options``: extra vega-embed options
    """

    spec = SpecBlock()
    description = blocks.TextBlock(
        required=False,
        rows=2,
        help_text=_("Describe what the chart shows, for people using screen readers."),
    )
    caption = blocks.CharBlock(required=False)

    class Meta:
        icon = "wagtail-vega-chart"
        label = _("Chart")
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

    def get_embed_options(self, value, context=None, theme=None) -> dict:
        options = {
            **get_setting("EMBED_OPTIONS"),
            **(self.meta.embed_options or {}),
            # Styles ship in wagtail-vega.css, so nothing is injected
            # (keeps strict CSP happy)
            "defaultStyle": False,
            "tooltip": {"disableDefaultStyle": True},
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

    def build_chart(self, value, context=None) -> Chart:
        theme = self.get_theme(value, context)
        datasets = self.get_datasets(value, context)
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
            if theme.dark:
                dark = self.get_spec(value, context, datasets, theme, dark=True)
                chart.dark_config = dark.get("config")
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

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)
        context["chart"] = self.build_chart(value, parent_context)
        return context


class ChartBlock(BaseChartBlock):
    """The editor-facing chart block: a spec plus named datasets."""

    data = blocks.ListBlock(
        DatasetBlock(),
        min_num=0,
        help_text=_("Datasets the spec can refer to by name."),
    )
    theme = blocks.ChoiceBlock(
        choices=theme_choices,
        required=False,
        help_text=_("Leave blank to use the site's default theme."),
    )

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
        return value

    class Meta:
        label = _("Chart")
