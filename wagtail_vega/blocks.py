"""StreamField blocks for Vega / Vega-Lite charts.

``ChartBlock`` is the editor-facing block: editors paste a spec and attach
named datasets (pasted CSV/TSV/JSON, a document, or an allowlisted URL).

``BaseChartBlock`` is the extension point for developers. Subclass it and
override ``get_datasets()`` to supply data from anywhere, e.g. the database::

    class DonationsChartBlock(BaseChartBlock):
        def get_datasets(self, value, context=None):
            return {"source": list(Donation.objects.values("month", "total"))}

The spec refers to datasets by name: ``{"data": {"name": "source"}}``.
"""

from __future__ import annotations

import collections
import json
import logging
import secrets
from dataclasses import dataclass, field
from typing import Any

from django import forms
from django.core import checks
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, URLValidator
from django.forms.fields import InvalidJSONInput
from django.forms.utils import ErrorList
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
    deep_merge,
    host_allowed,
    inject_datasets,
    is_remote,
    normalize_url,
    remote_data,
    spec_kind,
)
from .themes import Theme, get_theme, resolve_css_vars, theme_choices
from .validation import spec_problems
from .widgets import EDITOR_JS, CodeEditor

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# JSON input
# --------------------------------------------------------------------------


class PrettyJSONField(forms.JSONField):
    def prepare_value(self, value):
        if isinstance(value, InvalidJSONInput):
            return value
        return json.dumps(value, indent=2, ensure_ascii=False, cls=self.encoder)


class JSONBlock(blocks.FieldBlock):
    """JSON in a code editor, stored as native JSON in the StreamField."""

    editor_mode = "json"
    voyager = False

    def __init__(self, required=True, help_text=None, rows=16, validators=(), **kwargs):
        self.field = PrettyJSONField(
            required=required,
            help_text=help_text,
            validators=validators,
            encoder=VegaJSONEncoder,
            widget=CodeEditor(
                mode=self.editor_mode,
                attrs={"rows": rows, "class": "wagtail-vega-json"},
                voyager=self.voyager,
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
    """A Vega or Vega-Lite specification, validated on save (and live, in the
    editor)."""

    editor_mode = "spec"

    def __init__(self, voyager=True, **kwargs):
        # A "Build chart with Voyager" button above the editor (see
        # widgets.CodeEditor); voyager=False leaves it out.
        self.voyager = voyager
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
        return super().media + forms.Media(js=EDITOR_JS)


register(CodeFieldBlockAdapter(), JSONBlock)


# --------------------------------------------------------------------------
# Data sources
# --------------------------------------------------------------------------

PASTE, DOCUMENT, URL = "paste", "document", "url"
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


class PastedDataBlock(blocks.TextBlock):
    """Pasted CSV, TSV or JSON, edited in a code editor that shows tabs, doesn't
    wrap lines, and marks ragged rows and JSON errors."""

    @cached_property
    def field(self):
        widget = CodeEditor(mode="data", attrs={"rows": self.rows})
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


class DatasetBlock(blocks.StructBlock):
    """A named dataset. Editors pick where the data comes from with a
    Paste / Document / URL toggle; only the matching inputs are shown."""

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
        choices=[(PASTE, _("Paste")), (DOCUMENT, _("Document")), (URL, _("URL"))],
        default=PASTE,
        widget=forms.RadioSelect,
        label=_("Source"),
    )
    paste = PastedDataBlock(
        required=False,
        rows=8,
        label=_("Data"),
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

    def clean(self, value):
        value = super().clean(value)
        source = value["source_type"] or PASTE
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
        if errors:
            raise StructBlockValidationError(block_errors=errors)

        # Drop inputs for the other source types so stale data isn't kept
        for other, names in SOURCE_FIELDS.items():
            if other != source:
                for name in names:
                    value[name] = self.child_blocks[name].get_default()
        return value

    def get_dataset(self, value):
        source = value["source_type"] or PASTE
        if source == DOCUMENT:
            return document_rows(value["document"]) if value["document"] else []
        if source == URL:
            return remote_data(value["url"], value["format"] or None)
        return parse_text(value["paste"])


class DatasetBlockAdapter(StructBlockAdapter):
    js_constructor = "wagtail_vega.blocks.DatasetBlock"

    @cached_property
    def media(self):
        media = super().media
        return forms.Media(
            js=[
                *media._js,
                "wagtail_vega/admin/json-source.js",
                "wagtail_vega/admin/data-format.js",
                "wagtail_vega/admin/dataset-block.js",
            ],
            css={"all": ["wagtail_vega/admin/dataset-block.css"]},
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

    Set ``field_order`` to a tuple of child block names to control the order
    of fields in the editor (unlisted fields follow in declaration order).
    """

    field_order: tuple[str, ...] = ()

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

    def __init__(self, *args, **kwargs):
        if self.field_order:
            # StructBlock.__init__ copies base_blocks, so an instance attribute
            # set here decides the order on all supported Wagtail versions.
            declared = type(self).base_blocks
            names = [n for n in self.field_order if n in declared]
            names += [n for n in declared if n not in names]
            self.base_blocks = collections.OrderedDict((n, declared[n]) for n in names)
        super().__init__(*args, **kwargs)

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


class ChartBlock(BaseChartBlock):
    """The editor-facing chart block: a spec plus named datasets."""

    field_order = ("data", "spec", "description", "caption", "theme")

    data = blocks.ListBlock(
        DatasetBlock(),
        min_num=0,
        help_text=_("Datasets the spec can refer to by name."),
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
        return value

    class Meta:
        label = _("Chart")
