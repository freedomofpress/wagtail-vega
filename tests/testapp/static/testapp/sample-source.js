/* The test project's "sample" dataset source (DonationsDatasetBlock): its
 * rows are made in the browser, so the chart editor gets them from this
 * registered source rather than a rows URL. Loaded after wagtail-vega's
 * scripts by DonationsDatasetBlockAdapter.extra_js. Must match
 * tests.testapp.models.sample_rows. */
(() => {
  "use strict";

  const { registerSource, sources } = window.wagtailVegaAdmin;
  const points = (datasetEl) => Number(sources.readFields(datasetEl, ["points"]).points[0]);

  registerSource("sample", {
    hasData: (datasetEl) => points(datasetEl) > 0,
    loadRows(datasetEl) {
      const count = points(datasetEl);
      if (!(count > 0 && count <= 50)) throw new Error("Enter a number of points from 1 to 50.");
      return Array.from({ length: count }, (_, i) => ({ x: i + 1, y: (i + 1) ** 2 }));
    },
  });
})();
