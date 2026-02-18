"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  ACCENT_OPTIONS,
  getStoredAccent,
  setStoredAccent,
  type AccentTheme,
} from "@/lib/theme";

type AccentThemeContextValue = {
  accent: AccentTheme;
  setAccent: (accent: AccentTheme) => void;
};

const AccentThemeContext = createContext<AccentThemeContextValue | null>(null);

export function AccentThemeProvider({ children }: { children: React.ReactNode }) {
  const [accent, setAccentState] = useState<AccentTheme>("zinc");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    const stored = getStoredAccent();
    setAccentState(stored);
    if (stored === "zinc") document.documentElement.removeAttribute("data-accent");
    else document.documentElement.setAttribute("data-accent", stored);
  }, [mounted]);

  const setAccent = useCallback((value: AccentTheme) => {
    setAccentState(value);
    setStoredAccent(value);
  }, []);

  return (
    <AccentThemeContext.Provider value={{ accent, setAccent }}>
      {children}
    </AccentThemeContext.Provider>
  );
}

export function useAccentTheme() {
  const ctx = useContext(AccentThemeContext);
  if (!ctx) {
    return {
      accent: "zinc" as AccentTheme,
      setAccent: () => {},
      options: ACCENT_OPTIONS,
    };
  }
  return { ...ctx, options: ACCENT_OPTIONS };
}
