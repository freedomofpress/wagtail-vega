"""The chart builder's and code editor's text, translated on the server and
passed to the browser with their settings (see ``widgets.CodeEditor``).

chart-builder.js and chart-spec.js look every string up by key; values use
``%(name)s`` placeholders, filled in by the browser.
tests/test_chart_builder.py checks that every key the scripts use is here.
"""

from django.utils.translation import gettext as _


def builder_strings() -> dict[str, str]:
    strings = {
        # The spec field
        "note.scripts": _("The chart editor's scripts aren't loaded."),
        "field.loading": _("Drawing the chart…"),
        "field.invalid": _("The spec isn't valid JSON, so the chart can't be drawn."),
        "field.error": _("The chart can't be drawn: %(error)s"),
        "field.problem": _("Line %(line)s: %(message)s"),
        "field.codeData": _("This chart's data comes from code, so the preview has no data."),
        # The dialog
        "title": _("Edit chart"),
        "close": _("Close"),
        "closeLabel": _("Close the chart editor"),
        "autosaveNote": _("Changes go into the page as you make them."),
        "undo": _("Undo changes since opening"),
        "undone": _("Undid the changes made since the editor opened."),
        "tabs": _("Edit the chart"),
        "tab.visual": _("Visual"),
        "tab.code": _("Code"),
        "tab.codeProblems": _("has problems"),
        "codeHelp": _(
            "The Vega or Vega-Lite spec, in JSON. Changes here update the visual controls "
            "and the preview, and changes there update this."
        ),
        "dataset": _("Dataset"),
        "codeDataset": _("%(name)s (from code, can't be previewed here)"),
        "controls": _("Chart settings"),
        "frozen": _(
            "The code isn't valid JSON (line %(line)s: %(error)s). The settings and preview "
            "show the last valid chart until it's fixed."
        ),
        "unrepresentable": _(
            "The visual settings can't show this spec: %(problem)s. Keep editing it in the "
            "code, or start a new chart from the data."
        ),
        "noData": _(
            "The visual settings need a dataset with data in this form. Add data to the "
            "chart, or edit the spec in the code."
        ),
        "codeData": _(
            "This chart's data comes from code, so the visual settings aren't available. "
            "Edit the spec in the code."
        ),
        "pending": _(
            "This suggested chart isn't in the page yet: change a setting or pick a "
            "suggestion to add it."
        ),
        "startFresh": _("Start a new chart"),
        "preview": _("Preview"),
        "colours": _("Colours"),
        "light": _("Light mode"),
        "dark": _("Dark mode"),
        # The controls
        "suggestions": _("Suggested charts"),
        "suggestionsHelp": _(
            "Start from a chart that suits the data's columns. "
            "It replaces the chart type and fields below."
        ),
        "chart": _("Chart"),
        "chartType": _("Chart type"),
        "arrangement": _("Bars or areas that share a position"),
        "arrangementHint.bar": _("Choose a colour field to split the bars into parts."),
        "arrangementHint.area": _("Choose a colour field to split the areas into parts."),
        "point": _("Show a point for each value"),
        "donut": _("Donut (leave a hole in the middle)"),
        "tooltip": _("Show values in a tooltip on hover or focus"),
        "field": _("Field"),
        "type": _("Type"),
        "aggregate": _("Combine rows"),
        "bin": _("Bins"),
        "timeUnit": _("Time unit"),
        "sort": _("Sort"),
        "swap": _("Swap X and Y"),
        "layout": _("Title and size"),
        "chartTitle": _("Chart title"),
        "width": _("Width"),
        "widthValue": _("Width in pixels"),
        "height": _("Height in pixels"),
        "heightHint": _("Leave blank for the default."),
        "keptTitle": _("From the current spec"),
        "keptIntro": _(
            "The settings don't edit these parts of the spec. They're kept as they are:"
        ),
        "droppedIntro": _("Your changes remove these parts of the spec:"),
        # Options
        "none": _("None"),
        "count": _("Count of rows"),
        "column": _("%(name)s (%(type)s)"),
        "specField": _("%(name)s (from the spec)"),
        "columnType.quantitative": _("number"),
        "columnType.nominal": _("category"),
        "columnType.ordinal": _("ordered"),
        "columnType.temporal": _("date"),
        "aggregate.none": _("No (one mark per row)"),
        "bin.none": _("No"),
        "bin.bin": _("Group into ranges (bins)"),
        "timeUnit.none": _("None (exact values)"),
        "sort.default": _("Default"),
        "sort.ascending": _("Ascending (A to Z, low to high)"),
        "sort.descending": _("Descending (Z to A, high to low)"),
        "sort.none": _("Order in the data"),
        "sort.byAscending": _("By %(channel)s, ascending"),
        "sort.byDescending": _("By %(channel)s, descending"),
        "width.container": _("Fill the page width"),
        "width.auto": _("Automatic"),
        "width.fixed": _("Fixed"),
        "custom": _("Custom: %(value)s"),
        "kept": _("%(value)s (kept from the spec)"),
        "keptNone": _("None (kept from the spec)"),
        "titleDefault": _("Default: the field name"),
        # Marks, types and the other choices (chart-spec.js)
        "mark.bar": _("Bar"),
        "mark.line": _("Line"),
        "mark.area": _("Area"),
        "mark.point": _("Point (scatter plot)"),
        "mark.circle": _("Circle"),
        "mark.square": _("Square"),
        "mark.tick": _("Tick (strip plot)"),
        "mark.arc": _("Arc (pie or donut)"),
        "mark.rect": _("Rectangle (heatmap)"),
        "mark.rule": _("Rule"),
        "type.quantitative": _("Number (quantitative)"),
        "type.nominal": _("Category (nominal)"),
        "type.ordinal": _("Ordered category (ordinal)"),
        "type.temporal": _("Date or time (temporal)"),
        "aggregate.sum": _("Sum"),
        "aggregate.mean": _("Mean (average)"),
        "aggregate.median": _("Median"),
        "aggregate.min": _("Minimum"),
        "aggregate.max": _("Maximum"),
        "aggregate.count": _("Count"),
        "aggregate.distinct": _("Count of distinct values"),
        "timeUnit.year": _("Year"),
        "timeUnit.yearquarter": _("Year and quarter"),
        "timeUnit.yearmonth": _("Year and month"),
        "timeUnit.yearmonthdate": _("Date"),
        "timeUnit.yearmonthdatehours": _("Date and hour"),
        "timeUnit.quarter": _("Quarter (all years together)"),
        "timeUnit.month": _("Month (all years together)"),
        "timeUnit.date": _("Day of the month"),
        "timeUnit.day": _("Day of the week"),
        "timeUnit.hours": _("Hour of the day"),
        "arrangement.stacked": _("Stacked"),
        "arrangement.normalize": _("Stacked to 100%"),
        "arrangement.center": _("Stacked around the centre (streamgraph)"),
        "arrangement.grouped": _("Side by side (grouped)"),
        "arrangement.none": _("Overlapping"),
        "channel.x": _("X axis (horizontal)"),
        "channel.y": _("Y axis (vertical)"),
        "channel.theta": _("Slice size"),
        "channel.color": _("Colour"),
        "channel.size": _("Size"),
        "channel.column": _("Columns (a small chart for each value)"),
        "channel.row": _("Rows (a small chart for each value)"),
        "channelShort.x": _("X axis"),
        "channelShort.y": _("Y axis"),
        "channelShort.theta": _("slice size"),
        "channelShort.color": _("colour"),
        "channelShort.size": _("size"),
        "channelTitle.x": _("Axis title"),
        "channelTitle.y": _("Axis title"),
        "channelTitle.theta": _("Legend title"),
        "channelTitle.color": _("Legend title"),
        "channelTitle.size": _("Legend title"),
        "channelTitle.column": _("Heading"),
        "channelTitle.row": _("Heading"),
        # Why the visual settings can't show a spec (see "unrepresentable")
        "problem.json": _("it isn't valid JSON"),
        "problem.notObject": _("it isn't a JSON object"),
        "problem.vega": _("it's a Vega spec, and the settings make Vega-Lite charts"),
        "problem.noSchema": _("it has no Vega-Lite $schema"),
        "problem.composite": _(
            "it combines several views (it has “%(key)s”), and the settings make one view at a time"
        ),
        "problem.mark": _("they don't offer its mark type, “%(mark)s”"),
        "problem.noMark": _("it has no mark"),
        "problem.data": _("it doesn't load its data from one of the chart's datasets by name"),
        "problem.encoding": _("its encoding isn't an object"),
        # Suggested charts
        "suggest.line": _("Line: %(y)s over time (%(x)s)"),
        "suggest.lines": _("Lines: %(y)s over time, one for each %(color)s"),
        "suggest.areas": _("Stacked areas: %(y)s over time by %(color)s"),
        "suggest.bars": _("Bars: %(y)s by %(x)s"),
        "suggest.grouped": _("Grouped bars: %(y)s by %(x)s and %(color)s"),
        "suggest.stacked": _("Stacked bars: %(y)s by %(x)s and %(color)s"),
        "suggest.heatmap": _("Heatmap: %(color)s by %(x)s and %(y)s"),
        "suggest.pie": _("Pie: share of %(theta)s by %(color)s"),
        "suggest.scatter": _("Scatter plot: %(y)s against %(x)s"),
        "suggest.perMonth": _("Bars: rows per month (%(x)s)"),
        "suggest.count": _("Bars: number of rows by %(x)s"),
        "suggest.histogram": _("Histogram of %(x)s"),
        # Status and errors
        "loading": _("Loading “%(name)s”…"),
        "noRows": _("“%(name)s” has no rows yet."),
        "unreadable": _("Couldn't read “%(name)s”."),
        "missingDataset": _(
            "The spec uses the dataset “%(missing)s”, which this chart doesn't have. "
            "The settings show “%(name)s”; changing one switches the spec to it."
        ),
        "codeDatasetUsed": _(
            "The spec uses “%(missing)s”, whose data comes from code and can't be previewed "
            "here. The settings show “%(name)s”; changing one switches the spec to it."
        ),
        "startedFresh": _("Started a new chart from a suggestion."),
        "datasetFields": _(
            "“%(name)s” doesn't have the fields the chart used, so it starts from a suggestion."
        ),
        "datasetNow": _("The chart now uses “%(name)s”."),
        "widthAuto": _(
            "Width set to automatic: charts split into rows or columns can't fill the page width."
        ),
        "swapped": _("Swapped the X and Y axes."),
        "suggestionApplied": _("Chart set to “%(label)s”."),
        "previewUnavailable": _("The preview isn't available: %(error)s"),
        "previewError": _("The preview can't be drawn yet: %(error)s"),
        "previewNote": _("Note: %(message)s"),
        "sampled": _(
            "The preview shows the first %(shown)s of %(total)s rows. "
            "The chart on the page uses them all."
        ),
        "error.scripts": _("The data editor's scripts aren't loaded."),
        "error.document": _("Couldn't load the document (%(status)s)."),
        "error.host": _("Data can't be loaded from %(url)s."),
        "error.url": _("Couldn't load %(url)s (%(status)s)."),
        "error.check": _("Couldn't check the spec (%(status)s)."),
        "error.library": _("Couldn't load %(src)s."),
    }
    return strings


def code_editor_strings() -> dict[str, str]:
    """The code editor's own text (code-editor.js), for every code field:
    the status line under the editor that names the first problem."""
    return {
        "status": _("Line %(line)s: %(message)s"),
        "statusMore": _("Line %(line)s: %(message)s (and %(count)s more)"),
    }
