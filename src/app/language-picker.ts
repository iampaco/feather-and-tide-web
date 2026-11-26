import { isLanguage, languageKey, setLanguage } from "../i18n/language";

export function setupLanguagePicker(
  picker: HTMLSelectElement,
  onChange: () => void,
): void {
  const entries: {
    node: Element;
    attribute?: "aria-label" | "title";
    english: string;
    chinese: string;
  }[] = [];
  for (const node of document.querySelectorAll("[data-zh]")) {
    entries.push({
      node,
      english: node.textContent ?? "",
      chinese: node.getAttribute("data-zh") ?? "",
    });
  }
  for (const [attribute, translation] of [
    ["aria-label", "data-zh-aria"],
    ["title", "data-zh-title"],
  ] as const) {
    for (const node of document.querySelectorAll(`[${translation}]`)) {
      entries.push({
        node,
        attribute,
        english: node.getAttribute(attribute) ?? "",
        chinese: node.getAttribute(translation) ?? "",
      });
    }
  }

  let saved: string | null = null;
  try {
    saved = localStorage.getItem(languageKey);
  } catch {
    // Storage can be unavailable in private or embedded browsers.
  }
  function apply(value: "en" | "zh-CN"): void {
    setLanguage(value);
    document.documentElement.lang = value;
    document.title =
      value === "en" ? "Feather & Tide" : "羽与潮 · Feather & Tide";
    picker.value = value;
    for (const { node, attribute, english, chinese } of entries) {
      const text = value === "en" ? english : chinese;
      if (attribute) node.setAttribute(attribute, text);
      else node.textContent = text;
    }
    onChange();
  }
  apply(isLanguage(saved) ? saved : "en");
  picker.addEventListener("change", () => {
    const value = picker.value;
    if (!isLanguage(value)) return;
    apply(value);
    try {
      localStorage.setItem(languageKey, value);
    } catch {
      // The selection still applies to this session.
    }
  });
}
