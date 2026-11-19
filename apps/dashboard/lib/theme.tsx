"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

/**
 * "dark" is the red scene with dark cards (the default); "light" keeps the
 * same scene and turns the content cards white (globals.css §14). Applied as
 * `data-surface` on <html>; `data-theme` always stays "dark", so the old
 * `light:` utilities never switch on.
 */
type Theme = "dark" | "light";

const ThemeContext = createContext<{ theme: Theme; toggleTheme: () => void } | null>(null);

const STORAGE_KEY = "sosnet-surface";

/**
 * Inline script run before hydration (app/layout.tsx) so the stored choice
 * applies on first paint without a flash.
 */
export const themeInitScript = `
(function () {
  var surface = "dark";
  try {
    // Choices stored under the old key belong to a theme that no longer exists.
    localStorage.removeItem("sosnet-theme");
    if (localStorage.getItem("${STORAGE_KEY}") === "light") surface = "light";
  } catch (e) {}
  document.documentElement.setAttribute("data-theme", "dark");
  document.documentElement.setAttribute("data-surface", surface);
})();
`;

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    // Sync with the attribute set before hydration; reading the DOM during
    // render would cause a hydration mismatch.
    const current = document.documentElement.getAttribute("data-surface");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (current === "light" || current === "dark") setTheme(current);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-surface", next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // localStorage unavailable (private browsing): the choice lasts for this visit only.
      }
      return next;
    });
  }, []);

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
