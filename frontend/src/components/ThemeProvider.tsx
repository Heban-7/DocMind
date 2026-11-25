"use client";

import { createContext, useCallback, useContext, useEffect, useSyncExternalStore } from "react";

type Theme = "light" | "dark";

interface ThemeCtx {
  theme: Theme;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeCtx>({ theme: "light", toggle: () => {} });
const CHANGED = "docmind-theme";

export function useTheme() {
  return useContext(ThemeContext);
}

function readTheme(): Theme {
  try {
    const saved = localStorage.getItem("theme");
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    // storage blocked: follow the system
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGED, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGED, onChange);
  };
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // the saved theme (or the system's), shared by every tab
  const theme = useSyncExternalStore<Theme>(subscribe, readTheme, () => "light");

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.classList.toggle("light", theme !== "dark");
  }, [theme]);

  const toggle = useCallback(() => {
    try {
      localStorage.setItem("theme", readTheme() === "light" ? "dark" : "light");
    } catch {
      // storage blocked: the change lasts for this page only
    }
    window.dispatchEvent(new Event(CHANGED));
  }, []);

  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}
