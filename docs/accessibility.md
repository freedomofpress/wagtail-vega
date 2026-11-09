# Accessibility

Charts are hard to make accessible, and a chart on its own isn't usable by everyone. wagtail-vega gives each chart a text description and a data table. Editors still need to write good descriptions.

## What each chart has

**A description.** The block's **Description** field is output as a visually hidden paragraph, and linked to the chart's `<figure>` with `aria-describedby`, so screen readers announce it with the figure. Encourage editors to say what the chart shows and what the reader should take from it, not just its type: "Requests rose every quarter, from 1,120 in Q1 to 1,460 in Q4", rather than "Bar chart of requests".

**A caption.** The **Caption** field is the figure's visible `<figcaption>`, for titles, sources and notes.

**A data table.** Unless `FALLBACK_TABLE` is off, a collapsible `<details>` element under the chart, labelled "Chart data", holds a table of each inline dataset. It helps screen reader users, keyboard users and anyone who wants the numbers.

- Each column is a `<th scope="col">`. Columns of numbers are right-aligned, with digits of equal width, so they're easy to compare.
- Wide tables scroll sideways inside their own box, rather than making the page scroll.
- When a chart has more than one dataset, each table has a `<caption>` with the dataset's name.
- Tables show at most `FALLBACK_TABLE_MAX_ROWS` rows (100 by default), followed by a note such as "Showing 100 of 2000 rows."
- Only datasets supplied as inline rows of objects are included. Data loaded from URLs and `values` written into the spec aren't.
- The table shows the data as supplied, before any transforms in the spec, such as filters or aggregates.

Turn it off for one kind of block with `fallback_table=False`, for example when the chart's data is already shown in a table nearby.

**Interactivity stays reachable.** The figure doesn't have `role="img"`, which would hide its contents from assistive technology, so inputs bound to signals, such as sliders and dropdowns, can still be used.

**Without JavaScript.** With {doc}`server-side rendering <ssr>`, readers without JavaScript see an SVG of the chart. Without it, they see "This chart needs JavaScript to display.", followed by "Its data is under “Chart data” below." when there's a data table. In both cases, the description, caption and data table are part of the HTML.

**When a chart fails.** If a chart can't be drawn, or its data doesn't load, readers see "Sorry, this chart couldn't be displayed." (pointing to the data table, when there is one), rather than an empty space. While a chart is loading, its element has `aria-busy="true"`.

## Vega's own accessibility features

Vega's SVG renderer, which is the default, adds ARIA attributes to the chart: the chart's container gets `role="graphics-document"`, and a spec's top-level `description` becomes its accessible name. Vega-Lite also adds descriptions to marks and axes. Editors can control these with the `description` and `aria` properties of the spec and its marks: see Vega-Lite's [mark properties](https://vega.github.io/vega-lite/docs/mark.html) and [ARIA config](https://vega.github.io/vega-lite/docs/config.html#aria-config).

Keep the default `"renderer": "svg"`. The canvas renderer has no accessible content.

## Colour and contrast

Themes control colours, so check them for contrast and for colour-blind readers, in both light and dark mode. Prefer charts that don't rely on colour alone, for example by labelling lines directly.

## Language

The chart template's own text ("This chart needs JavaScript to display.", "Sorry, this chart couldn't be displayed.", "Chart data" and "Showing … of … rows.") is marked for translation, so it follows the page's active language once translations exist. To change the wording, override the template (see [](frontend.md#overriding-the-template)).
