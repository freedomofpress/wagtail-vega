// The parts of CodeMirror 6 that wagtail-vega's admin editor uses, bundled
// by scripts/build-codemirror.mjs into a classic script that sets
// window.wagtailVegaCodeMirror. Only re-export what code-editor.js needs, to
// keep the bundle small.
export { Compartment, EditorState, StateEffect } from "@codemirror/state";
export {
  EditorView,
  drawSelection,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  highlightWhitespace,
  keymap,
  lineNumbers,
  placeholder,
} from "@codemirror/view";
export { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
export {
  bracketMatching,
  foldGutter,
  foldKeymap,
  indentOnInput,
  syntaxHighlighting,
} from "@codemirror/language";
export { classHighlighter } from "@lezer/highlight";
export {
  forEachDiagnostic,
  forceLinting,
  lintGutter,
  lintKeymap,
  linter,
  setDiagnosticsEffect,
} from "@codemirror/lint";
export { highlightSelectionMatches, search, searchKeymap } from "@codemirror/search";
export { json } from "@codemirror/lang-json";
