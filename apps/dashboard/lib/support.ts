/*
 * Assistenza via WhatsApp: the only support channel shown for now (the
 * support tickets are hidden, see SHOW_SUPPORT_TICKETS). The number is set
 * once here, international format, digits only (e.g. "393331234567").
 */
export const SUPPORT_WHATSAPP_NUMBER = "351914313866";

/* Same number as the WhatsApp widget of mamify.ai (wa-widget.js): the bot
 * behind it reads which site a chat comes from only from the closing
 * "Rif. <CODE>" line, so the message ends like the widget's (mamify.ai uses
 * MAMIFY). */
const SUPPORT_REF = "MAMIFY";

export const SHOW_SUPPORT_TICKETS = false;

const DEFAULT_TEXT = "Ciao, ho bisogno di assistenza su SOS Affiliate.";

/** wa.me link, or null while no number is set. */
export function supportWhatsAppLink(text: string = DEFAULT_TEXT): string | null {
  const digits = SUPPORT_WHATSAPP_NUMBER.replace(/\D/g, "");
  if (!digits) return null;
  return `https://wa.me/${digits}?text=${encodeURIComponent(`${text}\n\nRif. ${SUPPORT_REF}`)}`;
}
