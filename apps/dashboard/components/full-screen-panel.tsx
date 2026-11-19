"use client";

import { useEffect } from "react";

/**
 * Full-viewport working surface for multi-step tasks (activating or
 * completing a contract: address, codes, documents, payment plan): one
 * column, one scrollbar, a fixed header so "torna indietro" is always reachable.
 * A component rather than a route because the caller already holds the
 * product or contract; a route would re-fetch and re-authorize it.
 */
export function FullScreenPanel({
  eyebrow,
  title,
  subtitle,
  onClose,
  children,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
}) {
  // Lock page scroll underneath; two scrollbars on a phone make the form look frozen.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-surface-950 light:bg-surface-50 animate-fade-in">
      <div className="sticky top-0 z-10 border-b border-white/10 light:border-surface-200 bg-surface-950/95 light:bg-white/95 backdrop-blur-sm">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 py-3 flex items-center gap-3">
          <button
            onClick={onClose}
            aria-label="Torna indietro"
            className="p-2 -ml-2 rounded-xl hover:bg-white/10 light:hover:bg-surface-900/5 text-surface-400 hover:text-white light:hover:text-surface-900 transition cursor-pointer shrink-0"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="min-w-0 flex-1">
            {eyebrow && (
              <p className="text-[10px] font-semibold text-brand-400 uppercase tracking-wide">{eyebrow}</p>
            )}
            <h2 className="text-base sm:text-lg font-bold text-white light:text-surface-900 truncate">{title}</h2>
          </div>
        </div>
        {subtitle && (
          <div className="mx-auto max-w-3xl px-4 sm:px-6 pb-3 -mt-1">{subtitle}</div>
        )}
      </div>

      {/* Bottom padding keeps the last rows clear of the phone browser's toolbar. */}
      <div className="mx-auto max-w-3xl px-4 sm:px-6 py-6 pb-28">{children}</div>
    </div>
  );
}

/** Numbered "sei qui" step strip. `current` indexes `steps`; earlier steps show as done. */
export function FullScreenSteps({ steps, current }: { steps: string[]; current: number }) {
  return (
    <div className="flex items-center gap-1.5 sm:gap-2">
      {steps.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <div key={label} className="flex items-center gap-1.5 sm:gap-2 min-w-0">
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0 ${
                active
                  ? "bg-brand-600 text-white"
                  : done
                    ? "bg-success-500/80 text-white"
                    : "bg-white/10 light:bg-surface-900/10 text-surface-400"
              }`}
            >
              {done ? "✓" : i + 1}
            </div>
            <span
              className={`text-[11px] font-semibold truncate ${
                active ? "text-white light:text-surface-900" : "text-surface-500"
              }`}
            >
              {label}
            </span>
            {i < steps.length - 1 && <div className="w-4 sm:w-8 h-px bg-white/10 light:bg-surface-300 shrink-0" />}
          </div>
        );
      })}
    </div>
  );
}
