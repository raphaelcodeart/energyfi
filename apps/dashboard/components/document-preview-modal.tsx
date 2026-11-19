"use client";

import { useEffect, useState } from "react";

/**
 * Opens a document over the page instead of in a new tab, so the reviewer
 * keeps their place.
 * The file is fetched from its short-lived presigned URL and shown via a
 * blob: URL, because the server sends `X-Frame-Options: DENY`, which would
 * block a PDF in this popup. Photos zoom to full size on click; PDFs use the
 * browser's viewer.
 */
export function DocumentPreviewModal({
  title,
  filename,
  contentType,
  loadUrl,
  onClose,
}: {
  title: string;
  filename: string;
  contentType: string;
  /** Resolves the presigned URL, requested only when the popup opens. */
  loadUrl: () => Promise<string>;
  onClose: () => void;
}) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const isImage = contentType.startsWith("image/");

  useEffect(() => {
    let revoked = false;
    let created: string | null = null;
    (async () => {
      try {
        const url = await loadUrl();
        const res = await fetch(url);
        if (!res.ok) throw new Error();
        const blob = await res.blob();
        created = URL.createObjectURL(new Blob([blob], { type: contentType }));
        if (!revoked) setObjectUrl(created);
      } catch {
        if (!revoked) setError("Impossibile aprire il documento. Riprova tra un momento.");
      }
    })();
    return () => {
      revoked = true;
      if (created) URL.revokeObjectURL(created);
    };
    // Loaded once per opening; the popup is remounted for another document.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[70] flex flex-col bg-black/85 backdrop-blur-sm animate-fade-in" onClick={onClose}>
      <div
        className="flex items-center justify-between gap-3 px-4 py-3 bg-surface-950/90 border-b border-white/10"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="min-w-0">
          <p className="text-sm font-bold text-white truncate">{title}</p>
          <p className="text-[11px] text-surface-400 truncate">{filename}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {isImage && objectUrl && (
            <button
              onClick={() => setZoomed((z) => !z)}
              className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-semibold text-white cursor-pointer"
            >
              {zoomed ? "Adatta allo schermo" : "Dimensione reale"}
            </button>
          )}
          {objectUrl && (
            <a
              href={objectUrl}
              download={filename}
              className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-semibold text-white"
            >
              Scarica
            </a>
          )}
          <button
            onClick={onClose}
            aria-label="Chiudi"
            className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <div
        className={`flex-1 min-h-0 ${zoomed ? "overflow-auto" : "overflow-hidden flex items-center justify-center"} p-3 sm:p-6`}
        onClick={(e) => e.stopPropagation()}
      >
        {error ? (
          <p className="text-sm text-danger-300 text-center">{error}</p>
        ) : !objectUrl ? (
          <div className="flex items-center gap-2 text-surface-300 text-sm">
            <svg className="animate-spin h-5 w-5 text-brand-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Apertura del documento...
          </div>
        ) : isImage ? (
          // eslint-disable-next-line @next/next/no-img-element -- a private blob, not an optimizable asset
          <img
            src={objectUrl}
            alt={title}
            onClick={() => setZoomed((z) => !z)}
            className={
              zoomed
                ? "max-w-none mx-auto cursor-zoom-out"
                : "max-w-full max-h-full object-contain rounded-lg shadow-2xl cursor-zoom-in"
            }
          />
        ) : (
          <iframe src={objectUrl} title={title} className="w-full h-full rounded-lg bg-white" />
        )}
      </div>
    </div>
  );
}
