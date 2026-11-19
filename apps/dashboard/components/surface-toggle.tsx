"use client";

import { useTheme } from "@/lib/theme";

/** Moon/sun switch in the command deck: dark cards (default) or white cards. */
export function SurfaceToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const light = theme === "light";
  return (
    <button
      onClick={toggleTheme}
      aria-label={light ? "Passa alla modalità notte" : "Passa alla modalità chiara"}
      title={light ? "Modalità notte" : "Modalità chiara"}
      className={`relative h-10 w-10 cursor-pointer place-items-center rounded-xl bg-white/10 text-white transition hover:bg-white/20 ${className || "grid"}`}
    >
      {light ? (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
        </svg>
      ) : (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      )}
    </button>
  );
}
