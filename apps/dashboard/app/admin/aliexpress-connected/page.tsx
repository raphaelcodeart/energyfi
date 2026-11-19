import Link from "next/link";

/** Landing page after authorizing the AliExpress account. */
export default async function AliexpressConnected({
  searchParams,
}: {
  searchParams: Promise<{ aliexpress?: string; message?: string }>;
}) {
  const { aliexpress, message } = await searchParams;
  const ok = aliexpress === "connected";
  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-surface-950 light:bg-surface-50">
      <div className="max-w-md w-full panel panel-hover rounded-2xl p-6 space-y-4 text-center">
        <h1 className={`text-lg font-bold ${ok ? "text-success-400" : "text-warn-400"}`}>
          {ok ? "Account AliExpress collegato" : "Collegamento AliExpress non riuscito"}
        </h1>
        <p className="text-sm text-surface-300 light:text-surface-600">
          {ok
            ? "L'autorizzazione è salvata. Torna in Shop AliExpress e premi “Verifica connessione”."
            : message || "Riprova dal pannello Shop AliExpress."}
        </p>
        <Link href="/admin" className="inline-block px-4 py-2 rounded-xl bg-brand-500 text-white text-sm font-semibold">
          Torna all&apos;amministrazione
        </Link>
      </div>
    </main>
  );
}
