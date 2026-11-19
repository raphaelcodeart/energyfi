"use client";

import { useEffect } from "react";

/** Root error boundary: an uncaught client exception shows a message and a
    retry button instead of leaving a blank page. */
export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-md w-full panel panel-hover rounded-2xl p-8 border-white/10 light:border-surface-300 bg-surface-950 light:bg-white text-center">
        <svg className="w-12 h-12 text-danger-400 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h1 className="text-lg font-bold text-white light:text-surface-900 mb-2">Qualcosa è andato storto</h1>
        <p className="text-sm text-surface-400 light:text-surface-500 mb-6">
          Si è verificato un errore imprevisto in questa schermata. Riprova -- se il problema
          persiste, contatta l&apos;assistenza tecnica.
        </p>
        <button
          onClick={reset}
          className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 hover:from-brand-500 hover:to-accent-400 text-sm font-semibold text-white shadow-lg transition cursor-pointer"
        >
          Riprova
        </button>
      </div>
    </div>
  );
}
