/* wagtail-vega: load the chart scripts once, in order.
 *
 * Used when a chart is rendered without a request in the template context
 * (e.g. `{{ page.body }}`), so the server can't tell whether the scripts
 * were already output. Each chart includes this small file; only the first
 * copy to run loads anything.
 */
(() => {
  "use strict";
  const script = document.currentScript;
  if (!script || window.wagtailVegaLoaderStarted) return;
  window.wagtailVegaLoaderStarted = true;
  for (const src of JSON.parse(script.dataset.scripts)) {
    const el = document.createElement("script");
    el.src = src;
    el.async = false; // execute in insertion order
    document.head.append(el);
  }
})();
