/* wagtail-vega admin: Vega Voyager's sandboxed iframe, for the chart
 * editor's Voyager mode (chart-builder.js).
 *
 * Voyager (React 15, vega 4, vega-lite 2: vendor/voyager, about 2.6 MB) runs
 * in a sandboxed iframe on an admin-only page (views.voyager), created the
 * first time the Voyager mode is shown. The iframe has sandbox="allow-scripts"
 * and no allow-same-origin, so the page has an opaque origin, and its CSP
 * gives it no network access: this page loads the data and passes it in.
 *
 * Every message is an object {channel: "wagtail-vega-voyager", type, ...}:
 *
 *   frame -> admin  ready                     Voyager has started
 *                   loaded {generation, seeded, warning}
 *                                             data (and spec, if seeded) loaded
 *                   spec {generation, spec, user, flush?}
 *                                             the current chart, or null; `user`
 *                                             once the editor has clicked, typed
 *                                             or dropped something since the load
 *                   close                     Escape pressed inside the frame
 *                   error {message}
 *   admin -> frame  load {generation, values, spec}
 *                                             data rows, plus a spec to open
 *                   flush {id}                report the chart now
 *
 * The frame has an opaque origin, so messages from it arrive with origin
 * "null"; they're accepted only from this iframe's window. Messages to it
 * have to use targetOrigin "*", and are only sent once the frame has said
 * it's ready. The frame accepts messages only from its parent at this
 * page's origin, and sends only to that origin (voyager-frame.js).
 *
 * Voyager reports changes a little after they happen (the frame waits
 * 100 ms for its state to settle), so flush() asks for the chart now, e.g.
 * before the editor closes.
 *
 * Exposed as window.wagtailVegaAdmin.VoyagerFrame.
 */
(() => {
  "use strict";

  const admin = (window.wagtailVegaAdmin = window.wagtailVegaAdmin || {});
  const CHANNEL = "wagtail-vega-voyager";
  const FLUSH_TIMEOUT = 1000; // ms

  const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

  class VoyagerFrame {
    /** `onMessage(data)` gets every message from the frame, checked. */
    constructor({ url, title, onMessage }) {
      this.url = url;
      this.title = title;
      this.onMessage = onMessage;
      this.iframe = null;
      this.ready = false;
      this.queue = [];
      this.flushes = new Map();
      this.flushId = 0;
      this.listener = (event) => this.receive(event);
    }

    /** The iframe, created (and Voyager started) on first use. */
    element() {
      if (!this.iframe) {
        window.addEventListener("message", this.listener);
        const iframe = document.createElement("iframe");
        iframe.className = "wagtail-vega-builder__voyager-frame";
        iframe.title = this.title;
        // No allow-same-origin: Voyager gets an opaque origin (see views.py)
        iframe.setAttribute("sandbox", "allow-scripts");
        iframe.src = this.url;
        this.iframe = iframe;
      }
      return this.iframe;
    }

    receive(event) {
      if (!this.iframe || event.source !== this.iframe.contentWindow) return;
      if (event.origin !== "null") return; // must be the sandboxed frame
      const data = event.data;
      if (!isObject(data) || data.channel !== CHANNEL || typeof data.type !== "string") return;
      if (data.type === "ready") {
        this.ready = true;
        for (const message of this.queue.splice(0)) this.post(message);
      }
      if (data.type === "spec" && data.flush !== undefined && this.flushes.has(data.flush)) {
        const resolve = this.flushes.get(data.flush);
        this.flushes.delete(data.flush);
        resolve(data);
      }
      this.onMessage(data);
    }

    post(message) {
      // The frame's origin is opaque, so "*" is the only targetOrigin that
      // reaches it; it's only used after the frame has said it's ready.
      if (!this.ready) {
        this.queue.push(message);
        return;
      }
      this.iframe?.contentWindow?.postMessage({ channel: CHANNEL, ...message }, "*");
    }

    /** Open `values` (data rows) in Voyager, with `spec` (Vega-Lite 2) if
     * it's given. Replaces any load still waiting for the frame. */
    load({ generation, values, spec }) {
      this.queue = this.queue.filter((m) => m.type !== "load");
      this.post({ type: "load", generation, values, spec: spec || null });
    }

    /** The frame's current chart, as a "spec" message; null if the frame
     * isn't running or doesn't answer in time. */
    flush() {
      if (!this.iframe || !this.ready) return Promise.resolve(null);
      const id = ++this.flushId;
      return new Promise((resolve) => {
        this.flushes.set(id, resolve);
        this.post({ type: "flush", id });
        setTimeout(() => {
          if (this.flushes.delete(id)) resolve(null);
        }, FLUSH_TIMEOUT);
      });
    }

    destroy() {
      window.removeEventListener("message", this.listener);
      for (const resolve of this.flushes.values()) resolve(null);
      this.flushes.clear();
      this.iframe?.remove();
      this.iframe = null;
      this.ready = false;
    }
  }

  admin.VoyagerFrame = VoyagerFrame;
})();
