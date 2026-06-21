"use client";

import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";

function readStoredTheme(): Theme {
  const stored = localStorage.getItem("openrole_theme") as Theme | null;
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

const ThemeCtx = createContext<{ theme: Theme; ready: boolean; toggle: () => void }>({
  theme: "light",
  ready: false,
  toggle: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Stable SSR + hydration default — never read localStorage in useState initializer.
  const [theme, setTheme] = useState<Theme>("light");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = readStoredTheme();
    document.documentElement.classList.toggle("dark", stored === "dark");
    queueMicrotask(() => {
      setTheme(stored);
      setReady(true);
    });
  }, []);

  useEffect(() => {
    if (!ready) return;
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme, ready]);

  const toggle = () => {
    setTheme((prev) => {
      const next = prev === "light" ? "dark" : "light";
      localStorage.setItem("openrole_theme", next);
      return next;
    });
  };

  return <ThemeCtx.Provider value={{ theme, ready, toggle }}>{children}</ThemeCtx.Provider>;
}

export function useTheme() {
  return useContext(ThemeCtx);
}
