"""The chart builder's text, translated on the server and passed to the
browser with the builder's settings (see ``widgets.CodeEditor``).

chart-builder.js and chart-spec.js look every string up by key; values use
``%(name)s`` placeholders, filled in by the browser.
tests/test_chart_builder.py checks that every key the scripts use is here.
"""

from django.utils.translation import gettext as _


def builder_strings() -> dict[str, str]:
    strings = {
        # The button's notes
        "note.codeData": _(
            "The chart builder works with datasets added in this form. "
            "This chart's data comes from code."
        ),
        "note.noData": _("Add data to this chart's datasets first, then build the chart from it."),
        "note.written": _("The chart is now in the spec field."),
        "note.unchanged": _("The chart wasn't changed."),
        "note.scripts": _("The chart builder's scripts aren't loaded."),
        # The lightbox
        "title": _("Build a chart from data"),
        "dataset": _("Dataset"),
        "codeDataset": _("%(name)s (from code, can't be previewed here)"),
        "close": _("Close without using the chart"),
        "problem": _("The builder can't open the spec that's in the field: %(problem)s."),
        "problemHelp": _(
            "You can start a new chart from the data instead. The spec in the field is only "
            "replaced if you choose “Use this chart” and confirm."
        ),
        "startFresh": _("Start a new chart"),
        "preview": _("Preview"),
        "colours": _("Colours"),
        "light": _("Light mode"),
        "dark": _("Dark mode"),
        "json": _("Spec (JSON)"),
        "cancel": _("Cancel"),
        "use": _("Use this chart"),
        "confirm": _("This replaces the spec that's in the field now."),
        "keepEditing": _("Keep editing"),
        "replace": _("Replace spec"),
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
            "The builder doesn't edit these parts of the spec. They're kept as they are:"
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
        # Why a spec can't be opened (completes "The builder can't open ...: ")
        "problem.json": _("it isn't valid JSON"),
        "problem.notObject": _("it isn't a JSON object"),
        "problem.vega": _("it's a Vega spec, and the builder makes Vega-Lite charts"),
        "problem.noSchema": _("it has no Vega-Lite $schema"),
        "problem.composite": _(
            "it combines several views (it has “%(key)s”), and the builder makes one view at a time"
        ),
        "problem.mark": _("the builder doesn't offer its mark type, “%(mark)s”"),
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
        "opened": _("Opened the field's chart."),
        "openedMissing": _(
            "Opened the field's chart. It used the dataset “%(missing)s”, which this chart "
            "doesn't have, so it now uses “%(name)s”."
        ),
        "openedCode": _(
            "Opened the field's chart. It uses “%(missing)s”, whose data comes from code and "
            "can't be previewed here, so the builder shows it with “%(name)s”. Using the chart "
            "switches it to “%(name)s”."
        ),
        "started": _("Started from a suggested chart. Change anything below."),
        "startedFresh": _("Started a new chart from a suggestion."),
        "cantOpen": _("The builder can't open this spec."),
        "datasetFields": _(
            "“%(name)s” doesn't have the fields the chart used, so it starts from a suggestion."
        ),
        "datasetNow": _("The chart now uses “%(name)s”."),
        "widthAuto": _(
            "Width set to automatic: charts split into rows or columns can't fill the page width."
        ),
        "swapped": _("Swapped the X and Y axes."),
        "suggestionApplied": _("Chart set to “%(label)s”."),
        "checking": _("Checking the chart…"),
        "invalid": _("This chart can't be used as it is:"),
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
