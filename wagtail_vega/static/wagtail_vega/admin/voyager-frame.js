/* wagtail-vega: the Voyager side of the admin's chart builder.
 *
 * Runs inside a sandboxed iframe (opaque origin) and talks to the admin
 * page with postMessage. See voyager-launcher.js for the protocol.
 *
 * The sandbox gives this document the origin "null", but location.origin
 * still reports the URL's origin, which is the admin's. Messages go only to
 * that origin and are only accepted from the parent window at that origin.
 */
(() => {
  "use strict";

  const CHANNEL = "wagtail-vega-voyager";
  const ADMIN_ORIGIN = window.location.origin;
  const container = document.getElementById("voyager");

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
    fail("Voyager didn't load.");
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
    fail(`Voyager couldn't start: ${(e && e.message) || e}`);
    return;
  }

  // Report the current chart whenever it changes; null while there isn't
  // one (e.g. empty shelves, or wildcards that match several charts).
  let lastSent;
  let timer;
  instance.onStateChange(() => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      let spec = null;
      try {
        spec = instance.getSpec(false) || null;
      } catch {
        spec = null;
      }
      const json = JSON.stringify(spec);
      if (json !== lastSent) {
        lastSent = json;
        send("spec", { spec });
      }
    }, 100);
  });

  function load({ values, spec }) {
    if (!Array.isArray(values)) {
      fail("No data was sent to Voyager.");
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
    send("loaded", { seeded, warning });
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window.parent || event.origin !== ADMIN_ORIGIN) return;
    const data = event.data;
    if (!data || data.channel !== CHANNEL) return;
    if (data.type === "load") load(data);
  });

  // Keyboard events don't leave the iframe, so pass Escape on for the
  // lightbox to close, unless Voyager used it (e.g. to close a popup).
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !event.defaultPrevented) send("close");
  });

  window.addEventListener("error", (event) => send("error", { message: String(event.message) }));

  send("ready");
})();
