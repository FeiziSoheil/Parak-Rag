export const ACCENT_STORAGE_KEY = "parak-accent-theme";

export type AccentTheme = "zinc" | "blue" | "rose" | "emerald" | "violet";

export const ACCENT_OPTIONS: { value: AccentTheme; label: string }[] = [
  { value: "zinc", label: "Zinc" },
  { value: "blue", label: "Blue" },
  { value: "rose", label: "Rose" },
  { value: "emerald", label: "Emerald" },
  { value: "violet", label: "Violet" },
];

export function getStoredAccent(): AccentTheme {
  if (typeof window === "undefined") return "zinc";
  const stored = localStorage.getItem(ACCENT_STORAGE_KEY);
  if (stored && ACCENT_OPTIONS.some((o) => o.value === stored)) return stored as AccentTheme;
  return "zinc";
}

export function setStoredAccent(accent: AccentTheme): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCENT_STORAGE_KEY, accent);
  const html = document.documentElement;
  if (accent === "zinc") html.removeAttribute("data-accent");
  else html.setAttribute("data-accent", accent);
}
