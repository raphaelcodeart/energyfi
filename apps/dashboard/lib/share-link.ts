/** Shares a link through the device's native share sheet
 * (`navigator.share()`), which lists the apps the user actually has.
 *
 * Where that is unavailable it copies to the clipboard instead; `result`
 * says which happened so the button can show the right feedback.
 */

export type ShareResult = "shared" | "copied" | "failed";

type ShareInput = {
  url: string;
  /** Share sheet title, where the platform shows one. */
  title?: string;
  /** Message pre-filled next to the link. */
  text?: string;
  /** Copy straight to the clipboard, skipping the sheet (the explicit
      "Copia link" button in share-buttons.tsx). */
  preferClipboard?: boolean;
};

export async function shareOrCopyLink({ url, title, text, preferClipboard = false }: ShareInput): Promise<ShareResult> {
  if (typeof navigator === "undefined") return "failed";

  // share() can still throw (insecure context, no user gesture) and canShare()
  // is not universal, so detect loosely and let the catch handle the rest.
  if (!preferClipboard && typeof navigator.share === "function") {
    try {
      await navigator.share({ url, title, text });
      return "shared";
    } catch (err) {
      // Dismissing the sheet is a deliberate "no": do not copy behind their back.
      if (err instanceof DOMException && err.name === "AbortError") return "failed";
      // Any other failure falls back to the clipboard.
    }
  }

  try {
    await navigator.clipboard.writeText(url);
    return "copied";
  } catch {
    return "failed";
  }
}
