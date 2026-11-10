/* wagtail-vega: the Voyager side of the chart editor's Voyager mode.
 *
 * Runs inside a sandboxed iframe (opaque origin; see views.py) and talks to
 * the admin page with postMessage. See voyager-editor.js for the protocol.
 *
 * The sandbox gives this document the origin "null", but location.origin
 * still reports the URL's origin, which is the admin's. Messages go only to
 * that origin and are only accepted from the parent window at that origin.
 *
 * Its text comes translated from the page (data-strings on #voyager).
 */
(() => {
  "use strict";

  const CHANNEL = "wagtail-vega-voyager";
  const ADMIN_ORIGIN = window.location.origin;
  const REPORT_DELAY = 100; // ms: Voyager changes its state in bursts
  const container = document.getElementById("voyager");
  let strings = {};
  try {
    strings = JSON.parse(container.dataset.strings || "{}");
  } catch {
    strings = {};
  }
  const t = (key, detail = "") => (strings[key] || key).replace("%(error)s", detail);

  function send(type, payload = {}) {
    window.parent.postMessage({ channel: CHANNEL, type, ...payload }, ADMIN_ORIGIN);
  }

  function fail(message) {
    container.replaceChildren();
    const p = document.createElement("p");
    p.className = "wagtail-vega-voyager-error";
    p.textContent = message;
    container.append(p);
    send("error", { message });
  }

  if (!window.voyager || typeof window.voyager.CreateVoyager !== "function") {
    fail(t("notLoaded"));
    return;
  }

  let instance;
  try {
    instance = window.voyager.CreateVoyager(
      container,
      {
        showDataSourceSelector: false,
        hideHeader: false, // keeps Undo/Redo; also dropped by setSpec()
        hideFooter: true,
        relatedViews: "initiallyShown",
        wildcards: "enabled",
      },
      undefined,
    );
  } catch (e) {
    fail(t("notStarted", String((e && e.message) || e)));
    return;
  }

  // Each load from the admin has a number, sent back with every report, so
  // the admin can tell reports about an earlier load from current ones.
  let generation = 0;
  // Whether the editor has clicked, typed or dropped anything in Voyager
  // since the last load. The admin only writes changes the editor made, not
  // Voyager settling on the chart it was given (see voyager-spec.js).
  let user = false;
  for (const type of ["pointerdown", "mousedown", "keydown", "dragstart", "drop", "input", "change", "touchstart"]) {
    window.addEventListener(type, () => (user = true), true);
  }

  function currentSpec() {
    try {
      return instance.getSpec(false) || null;
    } catch {
      return null;
    }
  }

  // Report the current chart whenever it changes; null while there isn't
  // one (e.g. empty shelves, or wildcards that match several charts).
  let lastSent;
  let timer;
  function report() {
    clearTimeout(timer);
    timer = null;
    const spec = currentSpec();
    const json = JSON.stringify([spec, user]);
    if (json === lastSent) return;
    lastSent = json;
    send("spec", { generation, spec, user });
  }
  instance.onStateChange(() => {
    clearTimeout(timer);
    timer = setTimeout(report, REPORT_DELAY);
  });

  function load(data) {
    const { values, spec } = data;
    clearTimeout(timer);
    generation = Number(data.generation) || 0;
    user = false;
    lastSent = undefined;
    if (!Array.isArray(values)) {
      fail(t("noData"));
      return;
    }
    let seeded = false;
    let warning = "";
    if (spec && typeof spec === "object") {
      try {
        instance.setSpec({ ...spec, data: { values } });
        seeded = true;
      } catch (e) {
        warning = String((e && e.message) || e).slice(0, 300);
      }
    }
    if (!seeded) instance.updateData({ values });
    send("loaded", { generation, seeded, warning });
    // Always report once after a load, even if the chart is the same as
    // before: it's the admin's baseline
    timer = setTimeout(report, REPORT_DELAY);
  }

  /** Report the chart now, whether or not it has changed, e.g. before the
   * editor closes. Voyager has already applied what the editor did; only
   * this frame's own delay is skipped. */
  function flush(id) {
    clearTimeout(timer);
    timer = null;
    const spec = currentSpec();
    lastSent = JSON.stringify([spec, user]);
    send("spec", { generation, spec, user, flush: id });
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window.parent || event.origin !== ADMIN_ORIGIN) return;
    const data = event.data;
    if (!data || data.channel !== CHANNEL) return;
    if (data.type === "load") load(data);
    else if (data.type === "flush") flush(data.id);
  });

  // Keyboard events don't leave the iframe, so pass Escape on for the
  // editor to close, unless Voyager used it (e.g. to close a popup).
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !event.defaultPrevented) send("close");
  });

  window.addEventListener("error", (event) => send("error", { message: String(event.message) }));

  send("ready");
})();
