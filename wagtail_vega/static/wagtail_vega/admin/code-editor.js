/* wagtail-vega admin: a CodeMirror 6 editor for code fields.
 *
 * Enhances <textarea data-wagtail-vega-code-editor="{config}"> (rendered by
 * wagtail_vega.widgets.CodeEditor) with an editor that has line numbers,
 * JSON highlighting, and problems underlined where they are:
 *
 * - "json" mode: JSON syntax errors, live.
 * - "spec" mode: as "json", plus schema and data-host errors, validated
 *   live by the server (the same checks as saving), debounced.
 * - "data" mode (pasted CSV/TSV/JSON): no wrapping, tabs shown, JSON
 *   highlighted when the data is JSON, ragged rows and JSON errors marked.
 *
 * After a failed save, the block's error messages ("encoding.x.type: ...")
 * are underlined at the JSON path they start with.
 *
 * Keyboard: Tab is not captured, so Tab and Shift+Tab move between fields
 * as usual. Indent with Ctrl/Cmd+] and outdent with Ctrl/Cmd+[. F8 moves to
 * the next problem; Ctrl/Cmd+Shift+M lists them all. Ctrl/Cmd+F searches.
 *
 * CONTRACT FOR OTHER ADMIN CODE (e.g. a button that sets the spec):
 *
 *   The <textarea> stays in the form, hidden, and is the source of truth:
 *   it is what gets submitted, and the editor writes every change to it and
 *   then fires a bubbling "input" event on it. To change the value from
 *   outside, set the textarea and fire "input" (or "change"):
 *
 *     const textarea = fieldWrapper.querySelector("textarea");
 *     textarea.value = json;
 *     textarea.dispatchEvent(new Event("input", { bubbles: true }));
 *
 *   The editor then updates itself as a single undoable change. There is
 *   no feedback loop: the editor only writes when its text differs from the
 *   textarea's, and only reads when the textarea's differs from its own.
 *   Setting textarea.value without an event is not noticed.
 *
 *   With the chart builder (config.builder, see chart-builder.js), the
 *   editor isn't shown inline: its element (`editor.host`) starts hidden
 *   and the builder's dialog shows it in its Code tab. Its writes to the
 *   textarea are debounced while typing (WRITE_DELAY), and flushed when
 *   it loses focus, when the form is submitted, before the page unloads
 *   and when `editor.flush()` is called. `editor.onChange(fn)` calls
 *   fn(text) on every change, and `editor.setText(text)` replaces the
 *   text as one undoable change. The problems found are passed to
 *   `onProblems` listeners as [{line, message, severity}].
 *
 *   The editor is inserted right after the textarea, in the same parent,
 *   so the field's [data-contentpath] wrapper keeps Wagtail's structure and
 *   a button can be added next to the field. `textarea.wagtailVegaEditor`
 *   is the editor object (`.focus()`, `.view` for CodeMirror's EditorView).
 *
 *   `editor.addCheck(fn)` adds a check that runs with the others:
 *   `fn(parsedJSON)` returns [{path, message}], and each is underlined at
 *   its path (see chart-block.js). `editor.relint()` runs every check again,
 *   e.g. when something they depend on changes.
 *
 *   The textarea's placeholder attribute is shown while the editor is empty.
 *
 * Needs vendor/codemirror.js, json-source.js and data-format.js.
 */
(() => {
  "use strict";

  const admin = window.wagtailVegaAdmin;
  const { jsonSource, dataFormat } = admin;
  const LINT_DELAY = 500; // ms after typing stops
  const WRITE_DELAY = 300; // ms; with the chart builder, see the contract above

  // -- Diagnostics: plain functions, no CodeMirror (see tests/js) -----------

  /** A syntax error in JSON text, as a diagnostic. */
  function jsonDiagnostics(text) {
    const { error } = jsonSource.parse(text);
    return error ? [{ from: error.from, to: error.to, severity: "error", message: error.message }] : [];
  }

  /** Diagnostics for problems from the validation endpoint: {path, message}. */
  function pathDiagnostics(text, problems) {
    const { root } = jsonSource.parse(text);
    if (!root) return [];
    return problems.map(({ path, message }) => ({
      ...jsonSource.rangeForPath(root, path || [], message),
      severity: "error",
      message,
    }));
  }

  /** Diagnostics for a failed save's messages, e.g. "encoding.x.type: ...".
   * Messages that don't start with a path are put on the whole spec. */
  function messageDiagnostics(text, messages) {
    const { root } = jsonSource.parse(text);
    if (!root) return [];
    return messages.map((full) => {
      const { path, message } = jsonSource.splitMessage(root, full);
      return { ...jsonSource.rangeForPath(root, path || [], message), severity: "error", message };
    });
  }

  /** The smallest single change turning `a` into `b`, so that an external
   * update keeps the cursor and scroll position where nothing changed. */
  function diff(a, b) {
    let from = 0;
    const max = Math.min(a.length, b.length);
    while (from < max && a.charCodeAt(from) === b.charCodeAt(from)) from++;
    let endA = a.length;
    let endB = b.length;
    while (endA > from && endB > from && a.charCodeAt(endA - 1) === b.charCodeAt(endB - 1)) {
      endA--;
      endB--;
    }
    return { from, to: endA, insert: b.slice(from, endB) };
  }

  function csrfHeaders(form) {
    const config = window.wagtailConfig || {};
    const token =
      config.CSRF_TOKEN ||
      form?.querySelector("input[name=csrfmiddlewaretoken]")?.value ||
      document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1];
    return token ? { [config.CSRF_HEADER_NAME || "X-CSRFToken"]: token } : {};
  }

  // -- The editor ------------------------------------------------------------

  function editorTheme(CM) {
    const tint = (color, percent) => `color-mix(in srgb, ${color} ${percent}%, transparent)`;
    const selection = tint("var(--w-color-secondary-100, #80b3b4)", 40);
    const activeLine = tint("var(--w-color-text-context, #262626)", 5);
    return CM.EditorView.theme({
      "&": {
        color: "var(--w-color-text-context)",
        backgroundColor: "var(--w-color-surface-field)",
        border: "1px solid var(--w-color-border-field-default)",
        borderRadius: "0.3125rem",
        fontSize: "0.875rem",
        maxHeight: "min(70vh, 48rem)",
      },
      "&:hover": { borderColor: "var(--w-color-border-field-hover)" },
      "&.cm-focused": {
        outline: "3px solid var(--w-color-focus)",
        outlineOffset: "1px",
      },
      ".cm-scroller": {
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
        lineHeight: "1.5",
        overflow: "auto",
        borderRadius: "inherit",
      },
      ".cm-content, .cm-gutter": {
        minHeight: "calc(var(--wagtail-vega-code-rows, 8) * 1.5em + 8px)",
      },
      ".cm-content": { caretColor: "var(--w-color-text-context)" },
      ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--w-color-text-context)" },
      "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":
        { backgroundColor: selection },
      ".cm-gutters": {
        color: "var(--w-color-text-placeholder)",
        backgroundColor: "var(--w-color-surface-field)",
        borderRight: "1px solid var(--w-color-border-furniture)",
        borderRadius: "0.3125rem 0 0 0.3125rem",
      },
      ".cm-activeLine": { backgroundColor: activeLine },
      ".cm-activeLineGutter": { backgroundColor: activeLine, color: "var(--w-color-text-meta)" },
      "&.cm-focused .cm-matchingBracket": {
        backgroundColor: tint("var(--w-color-positive-100, #1b8666)", 25),
        outline: `1px solid ${tint("var(--w-color-positive-100, #1b8666)", 60)}`,
      },
      "&.cm-focused .cm-nonmatchingBracket": { backgroundColor: tint("var(--w-color-critical-200, #cd4444)", 30) },
      ".cm-selectionMatch": { backgroundColor: tint("var(--w-color-secondary-100, #80b3b4)", 25) },
      ".cm-searchMatch": {
        backgroundColor: tint("var(--w-color-warning-100, #faa500)", 35),
        outline: `1px solid ${tint("var(--w-color-warning-100, #faa500)", 70)}`,
      },
      ".cm-searchMatch.cm-searchMatch-selected": { backgroundColor: tint("var(--w-color-warning-100, #faa500)", 65) },
      ".cm-foldPlaceholder": {
        color: "var(--w-color-text-meta)",
        backgroundColor: "var(--w-color-surface-field-inactive)",
        border: "1px solid var(--w-color-border-furniture)",
      },
      ".cm-tooltip": {
        color: "var(--w-color-text-context)",
        backgroundColor: "var(--w-color-surface-field)",
        border: "1px solid var(--w-color-border-field-default)",
        borderRadius: "0.3125rem",
        boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
        overflow: "hidden",
      },
      ".cm-tooltip-lint": { padding: "0" },
      ".cm-diagnostic": { padding: "0.375rem 0.625rem", fontFamily: "inherit" },
      ".cm-diagnostic-error": { borderLeft: "4px solid var(--w-color-text-error)" },
      ".cm-diagnostic-warning": { borderLeft: "4px solid var(--w-color-warning-100)" },
      ".cm-panels": {
        color: "var(--w-color-text-context)",
        backgroundColor: "var(--w-color-surface-page)",
      },
      ".cm-panels-top": { borderBottom: "1px solid var(--w-color-border-furniture)" },
      ".cm-panels-bottom": { borderTop: "1px solid var(--w-color-border-furniture)" },
      ".cm-panel.cm-panel-lint ul [aria-selected]": {
        backgroundColor: tint("var(--w-color-secondary-100, #80b3b4)", 30),
      },
      ".cm-panel.cm-panel-lint ul:focus [aria-selected]": {
        color: "var(--w-color-text-button)",
        backgroundColor: "var(--w-color-surface-button-default)",
      },
      ".cm-textfield": {
        color: "var(--w-color-text-context)",
        backgroundColor: "var(--w-color-surface-field)",
        border: "1px solid var(--w-color-border-field-default)",
        borderRadius: "0.25rem",
      },
      ".cm-button": {
        color: "var(--w-color-text-context)",
        backgroundImage: "none",
        backgroundColor: "var(--w-color-surface-field)",
        border: "1px solid var(--w-color-border-field-default)",
        borderRadius: "0.25rem",
      },
      // Pasted data: show tabs as faint arrows, but not spaces
      ".cm-highlightSpace": { backgroundImage: "none" },
      ".cm-highlightTab": {
        backgroundImage: `url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="20"><path stroke="%23888" stroke-opacity=".55" stroke-dasharray="2 3" fill="none" d="M1 10H195"/><path stroke="%23888" fill="none" d="M190 5L196 10L190 15M197 4V16"/></svg>')`,
      },
    });
  }

  const editors = new WeakMap();

  class CodeEditor {
    constructor(textarea, config, CM) {
      this.textarea = textarea;
      this.mode = config.mode || "json";
      this.validateUrl = config.validateUrl || null;
      this.CM = CM;
      this.request = null;
      this.checks = [];
      this.validated = { text: null, problems: [] };
      this.placeholder = textarea.getAttribute("placeholder") || "";
      this.builder = Boolean(config.builder);
      this.writeDelay = this.builder ? WRITE_DELAY : 0;
      this.pendingWrite = null;
      this.changeListeners = new Set();
      this.problemListeners = new Set();
      this.problems = [];
      this.focusTarget = null; // e.g. the builder's button, when not inline

      const required = textarea.required;
      // A hidden required field would block submission with no visible
      // message; Wagtail validates on the server anyway.
      textarea.required = false;
      textarea.hidden = true;

      this.host = document.createElement("div");
      this.host.className = `wagtail-vega-code wagtail-vega-code--${this.mode}`;
      this.host.style.setProperty("--wagtail-vega-code-rows", String(config.rows || textarea.rows || 8));
      // Shown by the chart builder's dialog rather than inline
      if (this.builder) this.host.hidden = true;
      textarea.after(this.host);

      this.refresh = CM.StateEffect.define();
      const contentAttributes = { "aria-multiline": "true", autocapitalize: "off", autocorrect: "off" };
      if (required) contentAttributes["aria-required"] = "true";
      const describedBy = textarea.getAttribute("aria-describedby");
      if (describedBy) contentAttributes["aria-describedby"] = describedBy;

      this.view = new CM.EditorView({
        parent: this.host,
        state: CM.EditorState.create({
          doc: textarea.value,
          extensions: [...this.extensions(CM), CM.EditorView.contentAttributes.of(contentAttributes)],
        }),
      });

      // Server errors apply to the text they were reported for (none yet)
      this.saved = { doc: this.view.state.doc, diagnostics: [] };

      if (this.mode !== "data") {
        this.status = document.createElement("p");
        this.status.className = "wagtail-vega-code__status";
        this.status.setAttribute("aria-live", "polite");
        this.status.hidden = true;
        this.host.append(this.status);
      }

      if (this.writeDelay) {
        // Never lose the last edit: write it before the form is used
        textarea.form?.addEventListener("submit", () => this.flush(), true);
        window.addEventListener("beforeunload", () => this.flush());
      }
      const pull = () => this.pull();
      textarea.addEventListener("input", pull);
      textarea.addEventListener("change", pull);
      // The label may not be in the document yet when telepath renders
      if (!this.linkLabel()) requestAnimationFrame(() => this.linkLabel());
      textarea.wagtailVegaEditor = this;
    }

    extensions(CM) {
      const jsonLanguage = CM.json();
      const language = new CM.Compartment();
      const isJSON = (text) => this.mode !== "data" || dataFormat.detectFormat(text) === "json";

      return [
        CM.lineNumbers(),
        CM.foldGutter(),
        CM.lintGutter(),
        CM.highlightActiveLineGutter(),
        CM.highlightSpecialChars(),
        CM.history(),
        CM.drawSelection(),
        CM.indentOnInput(),
        CM.bracketMatching(),
        CM.highlightActiveLine(),
        CM.highlightSelectionMatches(),
        CM.search({ top: true }),
        CM.syntaxHighlighting(CM.classHighlighter),
        // Tab is deliberately not bound, so it never traps keyboard focus
        CM.keymap.of([
          ...CM.lintKeymap,
          ...CM.searchKeymap,
          ...CM.foldKeymap,
          ...CM.historyKeymap,
          ...CM.defaultKeymap,
        ]),
        language.of(isJSON(this.textarea.value.slice(0, 1000)) ? jsonLanguage : []),
        // Pasted data switches between JSON highlighting and none as it changes
        CM.EditorState.transactionExtender.of((tr) => {
          if (!tr.docChanged || this.mode !== "data") return null;
          const want = isJSON(tr.newDoc.sliceString(0, 1000));
          if (want === (language.get(tr.startState) === jsonLanguage)) return null;
          return { effects: language.reconfigure(want ? jsonLanguage : []) };
        }),
        this.mode === "data" ? [CM.highlightWhitespace(), CM.EditorState.tabSize.of(12)] : [],
        // The textarea's placeholder, e.g. an example spec, while it's empty
        this.placeholder && CM.placeholder ? CM.placeholder(this.placeholder) : [],
        CM.linter((view) => this.lint(view), {
          delay: LINT_DELAY,
          needsRefresh: (update) =>
            update.transactions.some((tr) => tr.effects.some((e) => e.is(this.refresh))),
        }),
        CM.EditorView.updateListener.of((update) => this.onUpdate(update)),
        CM.EditorView.domEventHandlers({ blur: () => void this.flush() }),
        editorTheme(CM),
      ];
    }

    onUpdate(update) {
      if (update.docChanged) {
        const text = update.state.doc.toString();
        if (this.writeDelay) {
          clearTimeout(this.pendingWrite);
          this.pendingWrite = setTimeout(() => this.flush(), this.writeDelay);
        } else {
          this.write(text);
        }
        for (const listener of this.changeListeners) listener(text, update);
      }
      const linted = update.transactions.some((tr) =>
        tr.effects.some((e) => e.is(this.CM.setDiagnosticsEffect)),
      );
      if (linted) {
        this.updateStatus(update.state);
        this.updateProblems(update.state);
      }
    }

    write(text) {
      if (text === this.textarea.value) return;
      this.textarea.value = text;
      this.textarea.dispatchEvent(new Event("input", { bubbles: true }));
    }

    /** Write a debounced change to the textarea now. */
    flush() {
      if (this.pendingWrite === null) return;
      clearTimeout(this.pendingWrite);
      this.pendingWrite = null;
      this.write(this.view.state.doc.toString());
    }

    /** Call fn(text, update) whenever the text changes. Returns an
     * unsubscribe function. */
    onChange(fn) {
      this.changeListeners.add(fn);
      return () => this.changeListeners.delete(fn);
    }

    /** Call fn(problems) whenever the problems change, and now. */
    onProblems(fn) {
      this.problemListeners.add(fn);
      fn(this.problems);
      return () => this.problemListeners.delete(fn);
    }

    /** Replace the text as one undoable change, with the cursor at the
     * start of what changed. */
    setText(text, { userEvent = "input.replace" } = {}) {
      const current = this.view.state.doc.toString();
      if (text === current) return;
      const change = diff(current, text);
      this.view.dispatch({
        changes: change,
        selection: { anchor: change.from },
        scrollIntoView: true,
        userEvent,
      });
    }

    updateProblems(state) {
      const found = [];
      this.CM.forEachDiagnostic(state, (d, from) =>
        found.push({ from, line: state.doc.lineAt(from).number, message: d.message, severity: d.severity }),
      );
      found.sort((a, b) => a.from - b.from);
      const problems = found.map(({ line, message, severity }) => ({ line, message, severity }));
      if (JSON.stringify(problems) === JSON.stringify(this.problems)) return;
      this.problems = problems;
      for (const listener of this.problemListeners) listener(problems);
    }

    /** Take a change made to the textarea from outside the editor. */
    pull() {
      // A change from outside wins over one still waiting to be written
      clearTimeout(this.pendingWrite);
      this.pendingWrite = null;
      const text = this.textarea.value;
      const current = this.view.state.doc.toString();
      if (text !== current) this.view.dispatch({ changes: diff(current, text) });
    }

    async lint(view) {
      const { doc } = view.state;
      const text = doc.toString();
      if (!text.trim()) return [];
      if (this.mode === "data") return dataFormat.diagnose(text);
      const syntax = jsonDiagnostics(text);
      if (syntax.length) return syntax;
      let found;
      if (doc === this.saved.doc) {
        // Unchanged since it was loaded or saved: show the server's errors,
        // rather than asking it again
        found = this.saved.diagnostics;
      } else if (this.mode === "spec" && this.validateUrl) {
        found = pathDiagnostics(text, await this.validate(text));
      } else {
        found = [];
      }
      // Other admin code's checks (see addCheck), unless the server already
      // reported the same problem
      const extra = pathDiagnostics(text, this.runChecks(text)).filter(
        (d) => !found.some((f) => f.from === d.from && f.message === d.message),
      );
      return [...found, ...extra];
    }

    /** Add a check of the parsed JSON, run with the others as you type:
     * `check(value)` returns [{path, message}] (see chart-block.js). */
    addCheck(check) {
      this.checks.push(check);
      this.relint();
    }

    runChecks(text) {
      if (!this.checks.length) return [];
      let value;
      try {
        value = JSON.parse(text);
      } catch {
        return [];
      }
      return this.checks.flatMap((check) => {
        try {
          return check(value) || [];
        } catch (error) {
          console.error("wagtail-vega:", error);
          return [];
        }
      });
    }

    /** Check the text again now, e.g. because something it's checked
     * against has changed. */
    relint() {
      this.view.dispatch({ effects: this.refresh.of(null) });
      this.CM.forceLinting(this.view);
    }

    /** Ask the server to validate a spec; [{path, message}]. Best effort:
     * if it fails, the spec is still validated when the page is saved. The
     * last answer is reused while the text is the same. */
    async validate(text) {
      if (this.validated.text === text) return this.validated.problems;
      const problems = await this.fetchProblems(text);
      if (problems) this.validated = { text, problems };
      return problems || [];
    }

    async fetchProblems(text) {
      this.request?.abort();
      const request = new AbortController();
      this.request = request;
      try {
        const response = await fetch(this.validateUrl, {
          method: "POST",
          body: text,
          credentials: "same-origin",
          signal: request.signal,
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            ...csrfHeaders(this.textarea.form),
          },
        });
        if (!response.ok) return null;
        const { errors } = await response.json();
        return Array.isArray(errors) ? errors : [];
      } catch {
        return null; // not remembered, so it's asked again next time
      } finally {
        if (this.request === request) this.request = null;
      }
    }

    /** Highlight the errors from a failed save, until the text is edited. */
    setServerErrors(messages) {
      const { doc } = this.view.state;
      this.saved = { doc, diagnostics: messageDiagnostics(doc.toString(), messages || []) };
      this.relint();
    }

    setInvalid(invalid) {
      this.host.classList.toggle("is-invalid", Boolean(invalid));
      if (invalid) this.view.contentDOM.setAttribute("aria-invalid", "true");
      else this.view.contentDOM.removeAttribute("aria-invalid");
    }

    updateStatus(state) {
      if (!this.status) return;
      const found = [];
      this.CM.forEachDiagnostic(state, (d, from) => found.push({ d, from }));
      found.sort((a, b) => a.from - b.from);
      const first = found[0];
      const more = found.length > 1 ? ` (and ${found.length - 1} more)` : "";
      const text = first
        ? `Line ${state.doc.lineAt(first.from).number}: ${first.d.message}${more}`
        : "";
      // Only touch the live region when the text changes, so screen readers
      // aren't told the same thing after every pause in typing
      if (text === this.status.textContent) return;
      this.status.hidden = !first;
      this.status.classList.toggle("is-warning", Boolean(first) && first.d.severity !== "error");
      this.status.textContent = text;
    }

    linkLabel() {
      const { id } = this.textarea;
      const label =
        this.textarea.labels?.[0] ||
        (id && this.textarea.getRootNode().querySelector?.(`label[for="${CSS.escape(id)}"]`));
      if (!label) return false;
      if (!label.id) label.id = `${id}-label`;
      this.view.contentDOM.setAttribute("aria-labelledby", label.id);
      // Clicking the label would focus the hidden textarea
      label.addEventListener("click", (event) => {
        event.preventDefault();
        this.focus();
      });
      return true;
    }

    focus() {
      if (this.focusTarget) this.focusTarget.focus();
      else this.view.focus();
    }
  }

  /** Enhance a textarea (once). Returns the editor, or null if it can't. */
  function attach(textarea) {
    if (editors.has(textarea)) return editors.get(textarea);
    const CM = window.wagtailVegaCodeMirror;
    if (!CM || !textarea) return null;
    let config = {};
    try {
      config = JSON.parse(textarea.dataset.wagtailVegaCodeEditor || "{}");
    } catch {
      // use the defaults
    }
    const editor = new CodeEditor(textarea, config, CM);
    editors.set(textarea, editor);
    return editor;
  }

  /** Make a Wagtail bound widget drive the editor instead of the textarea. */
  function enhance(bound) {
    const editor = attach(bound?.input);
    if (!editor) return bound;
    const { setState, setInvalid } = bound;
    bound.setState = function (state) {
      setState.call(this, state);
      editor.pull();
    };
    bound.setInvalid = function (invalid) {
      setInvalid?.call(this, invalid);
      editor.setInvalid(invalid);
    };
    bound.focus = () => editor.focus();
    bound.setServerErrors = (messages) => editor.setServerErrors(messages);
    bound.codeEditor = editor;
    return bound;
  }

  // -- Wagtail integration ----------------------------------------------------

  const { telepath } = window;

  // The widget: Wagtail's own Widget, plus the editor
  const Widget = telepath?.constructors?.["wagtail.widgets.Widget"];
  if (Widget) {
    class CodeEditorWidget extends Widget {
      render(...args) {
        return enhance(super.render(...args));
      }

      getByName(...args) {
        return enhance(super.getByName(...args));
      }
    }
    telepath.register("wagtail_vega.widgets.CodeEditor", CodeEditorWidget);
  }

  // JSONBlock / SpecBlock: pass the block's errors on to its editor
  const FieldBlockDefinition = window.wagtailStreamField?.blocks?.FieldBlockDefinition;
  if (telepath && FieldBlockDefinition) {
    class CodeFieldBlockDefinition extends FieldBlockDefinition {
      render(placeholder, prefix, initialState, initialError, ...rest) {
        const block = super.render(placeholder, prefix, initialState, initialError, ...rest);
        const forward = (error) => block.widget?.setServerErrors?.(error?.messages || []);
        const setError = block.setError;
        block.setError = function (error) {
          setError.call(this, error);
          forward(error);
        };
        forward(initialError);
        return block;
      }
    }
    telepath.register("wagtail_vega.blocks.CodeFieldBlock", CodeFieldBlockDefinition);
  }

  // Code editors in ordinary (non-StreamField) forms
  if (typeof document !== "undefined" && document.querySelectorAll) {
    const attachAll = () => {
      for (const textarea of document.querySelectorAll("textarea[data-wagtail-vega-code-editor]")) {
        attach(textarea);
      }
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", attachAll);
    else attachAll();
  }

  admin.codeEditor = {
    attach,
    _internal: { jsonDiagnostics, pathDiagnostics, messageDiagnostics, diff },
  };
})();
