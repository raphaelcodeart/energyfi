/** Contract status labels and colors for the pratica screens. Other contract
    screens keep their own copy of this table; the wording must match. */

export const CONTRACT_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata",
  PAYMENT_PENDING: "In attesa di pagamento",
  PAID: "Pagata",
  ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva",
  SUSPENDED: "Sospesa",
  CANCELLED: "Cessata",
  EXPIRED: "Scaduta",
  RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

export function contractStatusBadge(status: string): string {
  switch (status) {
    case "ACTIVE":
    case "RENEWED":
      return "bg-success-500/10 text-success-400 border-success-500/20";
    case "DRAFT":
      return "bg-surface-500/10 light:bg-surface-200/50 text-surface-400 light:text-surface-500 border-surface-500/20 light:border-surface-300";
    case "REJECTED":
    case "CANCELLED":
    case "SUSPENDED":
      return "bg-danger-500/10 text-danger-400 border-danger-500/20";
    case "UNDER_REVIEW":
      return "bg-info-500/10 text-info-400 border-info-500/20";
    default:
      return "bg-warn-500/10 text-warn-400 border-warn-500/20";
  }
}

export const PAYMENT_PLAN_LABELS: Record<string, string> = {
  FULL: "Soluzione unica",
  INSTALMENTS_3: "3 rate mensili",
  MONTHLY_12: "12 rate mensili",
};

export const ENERGY_POINT_LABELS: Record<string, string> = {
  ELECTRICITY: "Luce",
  GAS: "Gas",
};

/** Display name of a supply point: its POD/PDR code when recorded,
    otherwise its position in the pratica ("Contratto 1", "Contratto 2"). */
export function pointCode(point: { pod_code?: string | null; pdr_code?: string | null; position?: number }): string {
  if (point.pod_code) return `POD ${point.pod_code}`;
  if (point.pdr_code) return `PDR ${point.pdr_code}`;
  return point.position ? `Contratto ${point.position}` : "Contratto";
}

export function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString("it-IT") : "—";
}
