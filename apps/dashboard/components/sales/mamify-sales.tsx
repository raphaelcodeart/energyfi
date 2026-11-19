"use client";

import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Chip, KpiTile } from "@/components/ui/data-cells";
import { Empty, ErrorNote, OkNote } from "@/components/affiliate/shared";
import { Pagination, serverPagination } from "@/components/pagination";
import { eur, mamifyGet, mamifySend, num, shortDate } from "@/lib/affiliate";

/*
 * Vendite → Ordini and Vendite → Clienti on the data read from Mamify
 * (apps/api/app/modules/mamify): pages of 25 served by the server, search
 * on the server, never the whole list in the browser.
 */

export const ORDER_STATES: Record<string, { label: string; tone: "ok" | "warn" | "bad" | "muted" | "info" }> = {
  APPLIED: { label: "Applicato", tone: "ok" },
  RECEIVED: { label: "In attesa di pagamento", tone: "info" },
  IGNORED: { label: "Prodotto non abbinato", tone: "muted" },
  UNMATCHED: { label: "Acquirente non in rete", tone: "warn" },
  CANCELLED: { label: "Annullato", tone: "muted" },
  ERROR: { label: "Da verificare", tone: "bad" },
};

type Money = string | number;
type Coverage = { people: number; checked_once: number; oldest_check: string | null };

type OrderItem = {
  id: string; mamify_order_id: string; state: string; message: string | null; status: string | null;
  total: Money | null; ordered_at: string | null; received_at: string; source: string; operations: number;
  buyer: { mamify_id: string | null; agent_id: string | null; name: string | null; email: string | null };
  lines: { name: string | null; app: string | null; quantity: number | null; price: Money | null }[];
};
type OrdersPage = {
  items: OrderItem[]; total: number; page: number; page_size: number; pages: number;
  counts: Record<string, number>; applied_total: Money; coverage: Coverage;
};

type CustomerItem = {
  mamify_id: string; agent_id: string; name: string; email: string | null; phone: string | null;
  registered_at: string | null; present: boolean; sponsor: { mamify_id: string; name: string } | null;
  direct_count: number; orders: number; paid_total: Money; last_order_at: string | null; orders_checked_at: string | null;
};
type CustomersPage = {
  items: CustomerItem[]; total: number; page: number; page_size: number; pages: number; buyers: number; coverage: Coverage;
};

function useDebounced(value: string, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value.trim()), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

/** How far the order reader has gone: Mamify gives orders one person at a time. */
export function CoverageNote({ c }: { c?: Coverage }) {
  if (!c || !c.people) return null;
  const pct = Math.round((c.checked_once / c.people) * 100);
  const done = c.checked_once >= c.people;
  return (
    <div className="panel rounded-2xl p-4 text-xs text-surface-300">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span>
          {done
            ? <>Ordini letti per tutte le <b className="text-white">{num(c.people)}</b> persone. Si rileggono di continuo, prima chi ha una rete sotto.</>
            : <>Lettura degli ordini da Mamify: <b className="text-white">{num(c.checked_once)}</b> persone su {num(c.people)} ({pct}%). Mamify dà gli ordini una persona alla volta, 30 al minuto: gli ordini compaiono man mano.</>}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full" style={{ width: `${Math.max(2, pct)}%`, background: "linear-gradient(90deg, var(--brand, #4488ff), #a855f7)" }} />
      </div>
    </div>
  );
}

function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      aria-label={placeholder} className="field w-full rounded-xl px-3 py-2 text-sm sm:w-80" />
  );
}

function SkeletonRows({ cols, rows = 6 }: { cols: number; rows?: number }) {
  return <>{Array.from({ length: rows }, (_, i) => (
    <tr key={i}><td colSpan={cols} className="px-4 py-3"><div className="h-8 animate-pulse rounded-xl bg-white/5" /></td></tr>
  ))}</>;
}

// --- Ordini ----------------------------------------------------------------------

export function MamifyOrdersPanel({ buyer }: { buyer?: string } = {}) {
  const [state, setStateRaw] = useState("ALL");
  const [search, setSearchRaw] = useState(buyer ?? "");
  const q = useDebounced(search);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [open, setOpen] = useState<string | null>(null);
  // A new filter starts again from page 1.
  const setState = (v: string) => { setStateRaw(v); setPage(1); };
  const setSearch = (v: string) => { setSearchRaw(v); setPage(1); };
  const { data, error, isFetching } = useQuery({
    queryKey: ["mamify", "orders-page", { page, pageSize, state, q }],
    queryFn: () => {
      const p = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (state !== "ALL") p.set("state", state);
      if (q) p.set("search", q);
      return mamifyGet<OrdersPage>(`/orders/page?${p}`);
    },
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });
  const counts = data?.counts ?? {};
  const pagination = serverPagination(data?.total ?? 0, page, pageSize, setPage, setPageSize);
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiTile label="Ordini SOS" value={num(counts.ALL ?? 0)} hint="letti da Mamify" active={state === "ALL"} onClick={() => setState("ALL")} />
        <KpiTile label="Applicati" value={num(counts.APPLIED ?? 0)} hint={`${eur(data?.applied_total ?? 0)} pagati`} active={state === "APPLIED"} onClick={() => setState("APPLIED")} />
        <KpiTile label="In attesa" value={num((counts.RECEIVED ?? 0) + (counts.UNMATCHED ?? 0))} hint="pagamento o acquirente" active={state === "RECEIVED"} onClick={() => setState("RECEIVED")} />
        <KpiTile label="Da guardare" value={num((counts.IGNORED ?? 0) + (counts.ERROR ?? 0))} hint="prodotto non abbinato o errore" active={state === "IGNORED"} onClick={() => setState("IGNORED")} />
      </div>
      <CoverageNote c={data?.coverage} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchBox value={search} onChange={setSearch} placeholder="Cerca acquirente, email o numero d'ordine" />
        <div className="subnav flex-wrap">
          {([["ALL", "Tutti"], ...Object.entries(ORDER_STATES).map(([k, v]) => [k, v.label])] as [string, string][]).map(([k, l]) => (
            <button key={k} type="button" onClick={() => setState(k)} className="subnav-pill" data-active={state === k || undefined}>
              {l}{counts[k] ? ` · ${num(counts[k])}` : ""}
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-surface-400">Si salvano solo gli ordini con prodotti delle app SOS (sos-affiliate, digitalambassador): il resto di ciò che si compra su Mamify non viene registrato.</p>
      {error ? <ErrorNote message={(error as Error).message} /> : (
        <div className="panel rounded-3xl p-2 md:p-4">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr>
                <th className="px-4 py-3">Ordine</th><th className="px-4 py-3">Acquirente</th><th className="px-4 py-3">Prodotti</th>
                <th className="px-4 py-3 text-right">Totale</th><th className="px-4 py-3">Esito in SOS</th><th className="px-4 py-3"><span className="sr-only">Dettagli</span></th>
              </tr></thead>
              <tbody className={isFetching && data ? "opacity-60 transition-opacity" : ""}>
                {!data ? <SkeletonRows cols={6} /> : data.items.length === 0 ? (
                  <tr><td colSpan={6} className="px-4 py-10"><Empty>{q || state !== "ALL" ? "Nessun ordine con questi filtri." : "Nessun ordine SOS letto finora: compaiono man mano che la lettura avanza."}</Empty></td></tr>
                ) : data.items.map((o) => (
                  <tr key={o.id} className="align-top">
                    <td className="px-4 py-3">
                      <p className="font-semibold text-white">#{o.mamify_order_id}</p>
                      <p className="text-xs text-surface-400">{shortDate(o.ordered_at || o.received_at)} · {o.status ?? "—"}</p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-white">{o.buyer.name ?? "—"}</p>
                      <p className="text-xs text-surface-400">{o.buyer.email ?? `cliente ${o.buyer.mamify_id ?? "?"}`}</p>
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {o.lines.length === 0 ? "—" : o.lines.map((l, i) => (
                        <p key={i}><span className="text-white">{l.quantity && l.quantity > 1 ? `${l.quantity}× ` : ""}{l.name}</span> <span className="text-surface-400">· {l.price != null ? eur(l.price) : "—"}</span></p>
                      ))}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{o.total != null ? eur(o.total) : "—"}</td>
                    <td className="max-w-xs px-4 py-3">
                      <Chip tone={ORDER_STATES[o.state]?.tone ?? "muted"}>{ORDER_STATES[o.state]?.label ?? o.state}</Chip>
                      {o.operations > 0 && <span className="ml-2 text-xs text-surface-300">{o.operations} operazioni</span>}
                      {o.message && <p className="mt-1 text-xs text-surface-300">{o.message}</p>}
                    </td>
                    <td className="px-4 py-3">
                      <button type="button" className="act" onClick={() => setOpen(open === o.id ? null : o.id)}>{open === o.id ? "Chiudi" : "Dettagli"}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {open && data && (() => {
            const o = data.items.find((x) => x.id === open);
            return o ? (
              <div className="mx-2 mt-3 grid gap-2 rounded-2xl bg-white/5 p-4 text-xs text-surface-200 sm:grid-cols-2">
                <p>Ordine Mamify: <b className="text-white">#{o.mamify_order_id}</b></p>
                <p>Letto con: <b className="text-white">{o.source === "webhook" ? "avviso di Mamify" : "lettura periodica"}</b> il {shortDate(o.received_at)}</p>
                <p>Cliente Mamify: <b className="text-white">{o.buyer.mamify_id ?? "—"}</b></p>
                <p>Operazioni create in SOS: <b className="text-white">{o.operations}</b></p>
              </div>
            ) : null;
          })()}
          <div className="px-2 pt-3"><Pagination {...pagination} label="ordini" /></div>
        </div>
      )}
    </div>
  );
}

// --- Clienti -----------------------------------------------------------------------

export function MamifyCustomersPanel() {
  const qc = useQueryClient();
  const [buyersOnly, setBuyersOnlyRaw] = useState(true);
  const [search, setSearchRaw] = useState("");
  const q = useDebounced(search);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [ok, setOk] = useState<string | null>(null);
  const setBuyersOnly = (v: boolean) => { setBuyersOnlyRaw(v); setPage(1); };
  const setSearch = (v: string) => { setSearchRaw(v); setPage(1); };
  const { data, error, isFetching } = useQuery({
    queryKey: ["mamify", "customers-page", { page, pageSize, q, buyersOnly }],
    queryFn: () => {
      const p = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (q) p.set("search", q);
      if (buyersOnly) p.set("buyers_only", "true");
      return mamifyGet<CustomersPage>(`/customers/page?${p}`);
    },
    placeholderData: keepPreviousData,
  });
  const read = useMutation({
    mutationFn: (id: string) => mamifySend<{ found: number }>(`/customers/${id}/read-orders`),
    onSuccess: (r) => {
      setOk(r.found ? `Letti ${r.found} ordini SOS da Mamify.` : "Nessun ordine SOS per questo cliente su Mamify.");
      void qc.invalidateQueries({ queryKey: ["mamify"] });
    },
  });
  const pagination = serverPagination(data?.total ?? 0, page, pageSize, setPage, setPageSize);
  return (
    <div className="space-y-5">
      <CoverageNote c={data?.coverage} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchBox value={search} onChange={setSearch} placeholder="Cerca nome, email, telefono o id Mamify" />
        <div className="subnav">
          <button type="button" className="subnav-pill" data-active={buyersOnly || undefined} onClick={() => setBuyersOnly(true)}>
            Con ordini SOS{data ? ` · ${num(data.buyers)}` : ""}
          </button>
          <button type="button" className="subnav-pill" data-active={!buyersOnly || undefined} onClick={() => setBuyersOnly(false)}>
            Tutti i clienti Mamify{data?.coverage ? ` · ${num(data.coverage.people)}` : ""}
          </button>
        </div>
      </div>
      <OkNote message={ok} />
      <ErrorNote message={(read.error as Error | null)?.message ?? (error as Error | null)?.message} />
      <div className="panel rounded-3xl p-2 md:p-4">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr>
              <th className="px-4 py-3">Cliente</th><th className="px-4 py-3">Contatti</th><th className="px-4 py-3">Sponsor</th>
              <th className="px-4 py-3 text-right">Ordini SOS</th><th className="px-4 py-3 text-right">Pagato</th><th className="px-4 py-3">Ordini letti</th>
              <th className="px-4 py-3"><span className="sr-only">Azioni</span></th>
            </tr></thead>
            <tbody className={isFetching && data ? "opacity-60 transition-opacity" : ""}>
              {!data ? <SkeletonRows cols={7} /> : data.items.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-10"><Empty>{buyersOnly && !q ? "Nessun cliente con ordini SOS finora: compaiono man mano che la lettura avanza. Scegli «Tutti i clienti Mamify» per vederli tutti." : "Nessun cliente trovato."}</Empty></td></tr>
              ) : data.items.map((c) => (
                <tr key={c.mamify_id} className="align-top">
                  <td className="px-4 py-3">
                    <p className="font-semibold text-white">{c.name}</p>
                    <p className="text-xs text-surface-400">id Mamify {c.mamify_id}{c.registered_at ? ` · dal ${shortDate(c.registered_at)}` : ""}{!c.present ? " · uscito" : ""}</p>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {c.email ? <a className="block underline decoration-white/30" href={`mailto:${c.email}`}>{c.email}</a> : "—"}
                    {c.phone && <a className="block text-surface-400" href={`tel:${c.phone}`}>{c.phone}</a>}
                  </td>
                  <td className="px-4 py-3 text-xs">{c.sponsor ? c.sponsor.name || `id ${c.sponsor.mamify_id}` : <span className="text-surface-400">Condividiamo</span>}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{num(c.orders)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{eur(c.paid_total)}</td>
                  <td className="px-4 py-3 text-xs text-surface-400">{c.orders_checked_at ? shortDate(c.orders_checked_at) : "non ancora"}</td>
                  <td className="px-4 py-3">
                    <button type="button" className="act whitespace-nowrap disabled:opacity-50" disabled={read.isPending}
                      onClick={() => { setOk(null); read.mutate(c.mamify_id); }} title="Legge subito da Mamify gli ultimi ordini di questo cliente (solo lettura)">
                      {read.isPending && read.variables === c.mamify_id ? "Leggo…" : "Leggi ordini ora"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-2 pt-3"><Pagination {...pagination} label="clienti" /></div>
      </div>
    </div>
  );
}
