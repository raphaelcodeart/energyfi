/** UI labels for commissions. Labels only: every amount comes from the server. */

export const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  DIRECT: "Provvigione diretta",
  INDIRECT: "Provvigione indiretta",
  PROMOTER_FEE: "Fee segnalazione",
  COMPANY_SHARE: "Quota azienda",
  REVERSAL: "Storno",
  // Legacy token-engine movements, still shown in history.
  PERSONAL_TOKEN: "Gettone personale (storico)",
  ENTREPRENEURIAL_DIFFERENCE: "Differenza imprenditoriale (storico)",
  FIRST_REFERRER_BONUS: "Bonus primo invito (storico)",
};

export const MOVEMENT_STATUS_LABELS: Record<string, string> = {
  PENDING: "Da approvare",
  ACCRUED: "Da approvare",
  APPROVED: "Approvata",
  PAYABLE: "Pagabile",
  SCHEDULED: "Programmata",
  PAID: "Pagata",
  CANCELLED: "Annullata",
  REVERSED: "Stornata",
  RETAINED: "Quota azienda",
};

export function movementStatusClass(status: string): string {
  switch (status) {
    case "PAID":
      return "bg-success-500/10 text-success-400 border-success-500/20";
    case "APPROVED":
    case "PAYABLE":
      return "bg-warn-500/10 text-warn-400 border-warn-500/20";
    case "CANCELLED":
    case "REVERSED":
      return "bg-danger-500/10 text-danger-400 border-danger-500/20";
    case "RETAINED":
      return "bg-white/5 text-surface-400 border-white/10";
    default:
      return "bg-info-500/10 text-info-400 border-info-500/20";
  }
}

export const BENEFICIARY_LABELS: Record<string, string> = {
  SELLER: "Venditore",
  UPLINE_LEVEL: "Sponsor a un livello",
  ROLE_IN_UPLINE: "Primo con un ruolo, sopra",
  INFLUENCER: "Influencer del delegato",
  PROMOTER: "Promoter (segnalatore)",
  COMPANY: "Azienda",
};

export const BENEFICIARY_HELP: Record<string, string> = {
  SELLER: "Chi ha chiuso la vendita.",
  UPLINE_LEVEL: "La persona a N livelli sopra il venditore (1 = sponsor diretto).",
  ROLE_IN_UPLINE: "Il primo, salendo, che ha il ruolo indicato (es. il Direttore commerciale).",
  INFLUENCER: "L'influencer di cui il venditore è delegato (delega esplicita o primo sopra che può avere delegati).",
  PROMOTER: "Chi ha portato la segnalazione da cui è nata la vendita.",
  COMPANY: "Una quota esplicita per l'azienda.",
};

export const CALCULATION_LABELS: Record<string, string> = {
  PERCENTAGE: "Percentuale del margine",
  FIXED_AMOUNT: "Importo fisso",
  MINIMUM_GUARANTEE: "Percentuale con minimo garantito",
  REMAINDER: "Residuo del margine",
};

export const FALLBACK_LABELS: Record<string, string> = {
  COMPANY: "La quota resta all'azienda",
  NEXT_AVAILABLE: "Passa al primo idoneo più in alto",
  STOP: "Non viene distribuita",
};

export const ACCRUAL_LABELS: Record<string, string> = {
  PER_INSTALMENT: "Una quota a ogni rata incassata",
  ON_ACTIVATION: "Tutto all'attivazione del contratto",
};

export const DISTRIBUTION_LABELS: Record<string, string> = {
  FULL: "Distribuisce tutto il margine",
  PARTIAL: "Distribuisce solo le quote indicate (il resto all'azienda)",
};

export const PLAN_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  ACTIVE: "Attivo",
  RETIRED: "Ritirato",
};

export const COMMISSION_MODE_LABELS: Record<string, string> = {
  PERCENTAGE: "Percentuale",
  FIXED: "Importo fisso",
  MIXED: "Misto",
  REFERRAL_FEE: "Fee su segnalazione",
  CUSTOM: "Personalizzato",
};

export const LEAD_STATUS_LABELS: Record<string, string> = {
  NEW: "Nuova",
  QUALIFIED: "In lavorazione",
  CONVERTED: "Convertita",
  LOST: "Persa",
  EXPIRED: "Scaduta",
};

export function pctLabel(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  return `${n.toLocaleString("it-IT", { maximumFractionDigits: 4 })}%`;
}
