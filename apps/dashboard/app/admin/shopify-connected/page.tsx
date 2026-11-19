import Link from "next/link";

/** Landing page after the Shopify app install (router.py `_admin_url`);
 * shows the outcome. */
export default async function ShopifyConnected({
  searchParams,
}: {
  searchParams: Promise<{ shopify?: string; message?: string }>;
}) {
  const { shopify, message } = await searchParams;
  const ok = shopify === "connected";
  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-surface-950 light:bg-surface-50">
      <div className="max-w-md w-full panel panel-hover rounded-2xl p-6 space-y-4 text-center">
        <h1 className={`text-lg font-bold ${ok ? "text-success-400" : "text-warn-400"}`}>
          {ok ? "Negozio Shopify collegato" : "Collegamento Shopify non completato"}
        </h1>
        <p className="text-sm text-surface-300 light:text-surface-600">
          {ok
            ? "L'app è installata e la connessione funziona. Ora puoi importare i prodotti da Shop Shopify → Catalogo."
            : message || "Riprova l'installazione dal pannello Shopify."}
        </p>
        <Link href="/admin" className="inline-block px-4 py-2 rounded-xl bg-brand-500 text-white text-sm font-semibold">
          Torna all&apos;amministrazione
        </Link>
      </div>
    </main>
  );
}
