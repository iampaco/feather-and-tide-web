export type Language = "en" | "zh-CN";

export const languageKey = "feather-tide-language";
let language: Language = "en";

export function isLanguage(value: unknown): value is Language {
  return value === "en" || value === "zh-CN";
}

export function setLanguage(value: Language): void {
  language = value;
}

export function isEnglish(): boolean {
  return language === "en";
}

export function copy(chinese: string, english: string): string {
  return isEnglish() ? english : chinese;
}

export function levelTitle(entry: { title: string; titleEn?: string }): string {
  return copy(entry.title, entry.titleEn ?? entry.title);
}

export function levelLabel(entry: { label: string; labelEn?: string }): string {
  return copy(entry.label, entry.labelEn ?? entry.label);
}
