// Just enough of a dataset block's DOM for sources.js and the chart
// builder's readDataset(): field wrappers ([data-contentpath]) holding form
// controls. The real thing is tested in the browser (tests/e2e/).

/** A form control: {name, type, tagName, value, checked, options, label}. */
export function control(props) {
  const { label, ...rest } = props;
  return {
    name: "field",
    type: "text",
    tagName: "INPUT",
    value: "",
    disabled: false,
    closest: (selector) => (selector === "label" && label ? { textContent: ` ${label} ` } : null),
    ...rest,
  };
}

export const radio = (value, checked = false, label = value) =>
  control({ type: "radio", value, checked, label });
export const checkbox = (value, checked = false) => control({ type: "checkbox", value, checked });
export const select = (values, selected = [], multiple = false) =>
  control({
    tagName: "SELECT",
    type: multiple ? "select-multiple" : "select-one",
    value: selected[0] ?? "",
    options: values.map((value) => ({ value, selected: selected.includes(value) })),
  });
export const textarea = (value) => control({ tagName: "TEXTAREA", type: "textarea", value });

const is = {
  input: (c) => c.tagName === "INPUT",
  textarea: (c) => c.tagName === "TEXTAREA",
  select: (c) => c.tagName === "SELECT",
};

/** A field's wrapper around `controls`. */
export function wrapper(controls) {
  return {
    querySelectorAll(selector) {
      if (selector === "input, select, textarea") return controls;
      if (selector === "input[type=radio]") return controls.filter((c) => c.type === "radio");
      throw new Error(`fake-dom: unsupported selector ${selector}`);
    },
    querySelector(selector) {
      const find = (test) => controls.find(test) || null;
      if (selector === "input[type=radio]:checked") return find((c) => c.type === "radio" && c.checked);
      if (selector === 'input[type="hidden"]') return find((c) => is.input(c) && c.type === "hidden");
      if (is[selector]) return find(is[selector]);
      throw new Error(`fake-dom: unsupported selector ${selector}`);
    },
  };
}

/** A dataset block: {field name: [controls]}, and its data- attributes. */
export function datasetElement(fields, data = {}) {
  return {
    dataset: data,
    querySelector(selector) {
      const match = selector.match(/^\[data-contentpath="(.+)"\]$/);
      if (!match) throw new Error(`fake-dom: unsupported selector ${selector}`);
      return fields[match[1]] ? wrapper(fields[match[1]]) : null;
    },
  };
}

/** A dataset with the sources settings dataset-block.js puts on it. */
export function customDataset({ name = "d", source, fields = {}, sourceFields = {}, rowsUrls = {} }) {
  const sources = ["paste", "document", "url", ...Object.keys(sourceFields)];
  return datasetElement(
    {
      name: [control({ name: "name", value: name })],
      source_type: sources.map((s) => radio(s, s === source, s === source ? `${s[0].toUpperCase()}${s.slice(1)}` : s)),
      paste: [textarea("a\n1")], // must never be read for another source
      ...fields,
    },
    {
      wagtailVegaSources: JSON.stringify({
        sourceFields: { paste: ["paste"], document: ["document"], url: ["url", "format"], ...sourceFields },
        rowsUrls,
      }),
    },
  );
}
