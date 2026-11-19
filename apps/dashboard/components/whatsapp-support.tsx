"use client";

import { supportWhatsAppLink } from "@/lib/support";

/* Assistenza via WhatsApp: the support page and the round button that sits
 * bottom right on every page (app-frame). Site blue, WhatsApp glyph. */

function WhatsAppGlyph({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M17.47 14.38c-.3-.15-1.75-.86-2.02-.96-.27-.1-.47-.15-.67.15-.2.3-.77.96-.94 1.16-.17.2-.35.22-.64.07-.3-.15-1.25-.46-2.38-1.47-.88-.79-1.47-1.76-1.65-2.05-.17-.3-.02-.46.13-.6.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.03-.52-.07-.15-.67-1.61-.92-2.2-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.79.37-.27.3-1.04 1.02-1.04 2.48s1.06 2.88 1.21 3.08c.15.2 2.1 3.2 5.08 4.48.71.31 1.26.49 1.69.63.71.22 1.36.19 1.87.12.57-.09 1.75-.72 2-1.41.25-.69.25-1.29.17-1.41-.07-.13-.27-.2-.57-.35zM12.04 21.5h-.01a9.43 9.43 0 01-4.8-1.32l-.35-.2-3.57.93.95-3.48-.22-.36a9.4 9.4 0 01-1.44-5.02c0-5.2 4.24-9.43 9.45-9.43a9.38 9.38 0 016.68 2.77 9.38 9.38 0 012.76 6.68c0 5.2-4.24 9.43-9.45 9.43zm8.04-17.47A11.3 11.3 0 0012.04.7C5.78.7.68 5.8.68 12.06c0 2 .52 3.96 1.52 5.68L.58 23.7l6.1-1.6a11.33 11.33 0 005.36 1.37h.01c6.26 0 11.36-5.1 11.36-11.37 0-3.03-1.18-5.89-3.33-8.03z" />
    </svg>
  );
}

const BLUE = "linear-gradient(135deg,#216eff,#47e2ff)";

export function WhatsAppSupportPage() {
  const link = supportWhatsAppLink();
  return (
    <div className="panel relative overflow-hidden rounded-3xl p-6 sm:p-8">
      <div className="flex flex-col items-start gap-5 sm:flex-row sm:items-center">
        <span className="grid h-16 w-16 shrink-0 place-items-center rounded-3xl text-white shadow-lg" style={{ background: BLUE }}>
          <WhatsAppGlyph className="h-9 w-9" />
        </span>
        <div className="min-w-0">
          <h2 className="text-2xl font-black tracking-tight text-white">Assistenza su WhatsApp</h2>
          <p className="mt-1 text-sm text-surface-200">
            Per qualsiasi domanda su account, ordini, punti, licenze o pagamenti scrivici su WhatsApp: ti risponde direttamente il nostro team.
          </p>
        </div>
      </div>
      <ul className="mt-6 space-y-2 text-sm text-surface-200">
        <li>1. Tocca il pulsante qui sotto: si apre WhatsApp con un messaggio già pronto.</li>
        <li>2. Scrivi in breve cosa ti serve e, se riguarda un ordine, il numero dell&apos;ordine Mamify.</li>
        <li>3. Ti rispondiamo in chat il prima possibile, nei giorni lavorativi.</li>
      </ul>
      {link ? (
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-7 inline-flex w-full items-center justify-center gap-3 rounded-2xl px-6 py-4 text-lg font-black text-white shadow-xl shadow-black/30 transition hover:brightness-110 sm:w-auto"
          style={{ background: BLUE }}
        >
          <WhatsAppGlyph />
          Apri qui l&apos;assistenza WhatsApp
        </a>
      ) : (
        <p className="mt-7 rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-sm text-surface-200">
          Il numero WhatsApp dell&apos;assistenza sarà disponibile a breve.
        </p>
      )}
    </div>
  );
}

/** Round button, bottom right, on every page; above the phone dock. */
export function WhatsAppFab() {
  const link = supportWhatsAppLink();
  if (!link) return null;
  return (
    <a
      href={link}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Assistenza su WhatsApp"
      title="Assistenza su WhatsApp"
      className="fixed right-4 z-40 grid h-14 w-14 place-items-center rounded-full text-white shadow-xl shadow-black/40 ring-2 ring-white/30 transition hover:scale-105 bottom-[calc(96px+env(safe-area-inset-bottom))] xl:bottom-6 xl:right-6"
      style={{ background: BLUE }}
    >
      <WhatsAppGlyph />
    </a>
  );
}
