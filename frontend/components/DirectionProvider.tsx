"use client";

import { useEffect } from "react";
import { getTextDirection, getBrowserLanguage } from "@/lib/direction";

const STORAGE_KEY = "app-lang";

/**
 * Reads preferred language: localStorage (user override) or browser language.
 */
function getPreferredLanguage(): string {
  if (typeof window === "undefined") return "en";
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) return stored;
  return getBrowserLanguage();
}

/**
 * Sets document direction and lang from detected/configured language.
 * Call setPreferredLanguage(lang) from settings if you add a language selector.
 */
export function DirectionProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const lang = getPreferredLanguage();
    const dir = getTextDirection(lang);
    const root = document.documentElement;
    root.setAttribute("dir", dir);
    root.setAttribute("lang", lang);
  }, []);

  return <>{children}</>;
}

/**
 * Use from settings to persist user language and update direction.
 */
export function setPreferredLanguage(lang: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, lang);
  const dir = getTextDirection(lang);
  document.documentElement.setAttribute("dir", dir);
  document.documentElement.setAttribute("lang", lang);
}
