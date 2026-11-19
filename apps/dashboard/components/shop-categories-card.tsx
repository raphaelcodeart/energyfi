"use client";

import { useState } from "react";
import { FullScreenPanel } from "@/components/full-screen-panel";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { ShopCategoryRead, ShopKey } from "@/lib/types";
import { Chip, Figure, Orb, RowActions } from "@/components/ui/data-cells";

/** Categories of a shop.
 *
 *  Each shop (the internal catalog sections and each Marketplace) has its
 *  own categories, managed here by admins and used by customers as Shop
 *  filters. A category belongs to exactly one shop, so the card only ever
 *  works on the selected shop. It is mounted next to that shop's product
 *  list. */

async function fetchShopCategories(shop: ShopKey): Promise<ShopCategoryRead[]> {
  const res = await fetch(`/api/proxy/shop-categories?shop=${shop}`);
  if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile caricare le categorie."));
  return res.json();
}

/** A shop's categories by position; one query shared per shop. */
export function useShopCategories(shop: ShopKey, enabled = true) {
  return useQuery({
    queryKey: ["shop-categories", shop],
    queryFn: () => fetchShopCategories(shop),
    enabled,
    staleTime: 60_000,
  });
}

/** Replaces a product's categories within its shop. Product forms call it
    only when the checkboxes actually changed. */
export async function saveProductCategories(
  shop: ShopKey,
  productId: string,
  categoryIds: string[]
): Promise<void> {
  const res = await fetch("/api/proxy/shop-categories/assignments", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ shop, product_id: productId, category_ids: categoryIds }),
  });
  if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile salvare le categorie del prodotto."));
}

/** Order-insensitive comparison: the server stores a set. */
export function sameCategorySelection(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const left = [...a].sort();
  const right = [...b].sort();
  return left.every((id, i) => id === right[i]);
}

const cardClass = "panel rounded-3xl";
const inputClass = "w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500";

export interface ShopCategoriesCardProps {
  /** Shops managed by this card; more than one adds a selector (the internal
      catalog's sections share one admin page). */
  shops: { key: ShopKey; label: string }[];
}

/** "Gestisci Categorie" button at the top of every shop page, opening the
    same category management from any tab. */
export function ManageCategoriesButton({ shops }: ShopCategoriesCardProps) {
  const [open, setOpen] = useState(false);
  const [selectedShop, setSelectedShop] = useState<ShopKey | null>(null);
  const shop: ShopKey = shops.some((s) => s.key === selectedShop)
    ? (selectedShop as ShopKey)
    : shops[0]?.key ?? "internal";
  const { data: categories, error } = useShopCategories(shop, open);
  const current = shops.find((s) => s.key === shop);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-brand-600 to-accent-500 hover:from-brand-500 hover:to-accent-400 text-white text-xs font-bold shadow-lg shadow-brand-500/20 transition-all duration-200 cursor-pointer active:scale-[0.98]"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h10" />
        </svg>
        Gestisci Categorie
      </button>
      {open && (
        <FullScreenPanel
          title="Categorie dello shop"
          subtitle={`Con queste il cliente filtra i prodotti${current ? ` di ${current.label}` : ""}. Eliminare una categoria non elimina i prodotti.`}
          onClose={() => setOpen(false)}
        >
          <div className="space-y-4">
            {shops.length > 1 && (
              <div className="subnav">
                {shops.map((s) => (
                  <button
                    key={s.key}
                    type="button"
                    onClick={() => setSelectedShop(s.key)}
                    data-active={shop === s.key}
                    className="subnav-pill"
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            )}
            {error && <p className="text-xs text-danger-400">{(error as Error).message}</p>}
            <CategoryList key={shop} shop={shop} categories={categories} />
            <BulkAssign key={`bulk-${shop}`} shop={shop} categories={categories} />
          </div>
        </FullScreenPanel>
      )}
    </>
  );
}

export function ShopCategoriesCard({ shops }: ShopCategoriesCardProps) {
  const [open, setOpen] = useState(false);
  const [selectedShop, setSelectedShop] = useState<ShopKey | null>(null);
  // Derived, not synced: stays valid across label renames while the shop exists.
  const shop: ShopKey = shops.some((s) => s.key === selectedShop)
    ? (selectedShop as ShopKey)
    : shops[0]?.key ?? "internal";

  const { data: categories, error } = useShopCategories(shop, open);

  return (
    <div className={cardClass}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex flex-wrap items-center justify-between gap-3 px-6 py-5 text-left cursor-pointer"
      >
        <span className="min-w-0">
          <span className="kpi-label block">Filtri del cliente</span>
          <span className="block text-xl font-black tracking-tight text-white mt-1">Categorie dello shop</span>
          <span className="block text-xs text-surface-300 mt-1">
            Le categorie con cui il cliente filtra i prodotti di questo shop, sotto il pulsante dello shop.
          </span>
        </span>
        <span className={open ? "act act-primary" : "act"}>{open ? "Chiudi" : "Gestisci"}</span>
      </button>

      {open && (
        <div className="pop px-6 pb-6 pt-5 border-t border-white/10 space-y-4">
          {shops.length > 1 && (
            <div className="subnav">
              {shops.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => setSelectedShop(s.key)}
                  data-active={shop === s.key}
                  className="subnav-pill"
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}

          {error && <p className="text-xs text-danger-400">{(error as Error).message}</p>}

          {/* Keyed by shop so drafts reset on switch. */}
          <CategoryList key={shop} shop={shop} categories={categories} />

          <BulkAssign key={`bulk-${shop}`} shop={shop} categories={categories} />
        </div>
      )}
    </div>
  );
}

function CategoryList({ shop, categories }: { shop: ShopKey; categories: ShopCategoryRead[] | undefined }) {
  const queryClient = useQueryClient();
  // Drafts by id; the draft wins over the server value, no sync effect.
  const [drafts, setDrafts] = useState<Record<string, { name?: string; position?: string }>>({});
  const [newName, setNewName] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<ShopCategoryRead | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["shop-categories", shop] });
  }

  async function patch(category: ShopCategoryRead, body: Record<string, unknown>) {
    setBusyId(category.id);
    setActionError(null);
    try {
      const res = await fetch(`/api/proxy/shop-categories/${category.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile salvare la categoria."));
      setDrafts((d) => {
        const next = { ...d };
        delete next[category.id];
        return next;
      });
      await refresh();
    } catch (err: any) {
      setActionError(err.message || "Impossibile salvare la categoria.");
    } finally {
      setBusyId(null);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setActionError(null);
    try {
      const res = await fetch("/api/proxy/shop-categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // New categories go last, after the ones customers already know.
        body: JSON.stringify({
          shop,
          name: newName.trim(),
          position: categories?.length ? Math.max(...categories.map((c) => c.position)) + 1 : 0,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile creare la categoria."));
      setNewName("");
      await refresh();
    } catch (err: any) {
      setActionError(err.message || "Impossibile creare la categoria.");
    } finally {
      setCreating(false);
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/proxy/shop-categories/${deleting.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile eliminare la categoria."));
      setDeleting(null);
      await refresh();
    } catch (err: any) {
      setDeleteError(err.message || "Impossibile eliminare la categoria.");
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {actionError && (
        <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{actionError}</div>
      )}

      {categories === undefined ? (
        <p className="text-xs text-surface-400 py-2">Caricamento categorie...</p>
      ) : categories.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-white/15 px-6 py-8 text-center">
          <span className="orb float-soft" aria-hidden="true">#</span>
          <p className="text-sm text-surface-300 max-w-md">
            Nessuna categoria per questo shop. Aggiungine una qui sotto: finché non ce n&apos;è nessuna, il cliente vede
            tutti i prodotti senza filtri.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3 text-left">Categoria</th>
                <th className="px-4 py-3 text-left">Posto</th>
                <th className="px-4 py-3 text-right">Articoli</th>
                <th className="px-4 py-3 text-left">Per il cliente</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
          {categories.map((c) => {
            const draft = drafts[c.id] ?? {};
            const name = draft.name ?? c.name;
            const position = draft.position ?? String(c.position);
            const changed = name.trim() !== c.name || position.trim() !== String(c.position);
            return (
              <tr key={c.id}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3 min-w-[200px]">
                    <Orb name={c.name} />
                    <input
                      className="flex-1 min-w-[140px] rounded-xl field px-3 py-1.5 text-sm font-semibold"
                      maxLength={120}
                      value={name}
                      onChange={(e) => setDrafts({ ...drafts, [c.id]: { ...draft, name: e.target.value } })}
                    />
                  </div>
                </td>
                <td className="px-4 py-3">
                  <input
                    className="w-16 rounded-xl field px-2 py-1.5 text-xs text-center tabular-nums"
                    inputMode="numeric"
                    title="Ordine di comparsa"
                    value={position}
                    onChange={(e) => setDrafts({ ...drafts, [c.id]: { ...draft, position: e.target.value } })}
                  />
                </td>
                <td className="px-4 py-3 text-right">
                  <Figure value={c.product_count} detail={c.product_count === 1 ? "prodotto" : "prodotti"} />
                </td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    className="cursor-pointer rounded-full disabled:opacity-50"
                    disabled={busyId === c.id}
                    onClick={() => patch(c, { active: !c.active })}
                    title={c.active ? "Nascondila al cliente" : "Rendila visibile al cliente"}
                  >
                    <Chip tone={c.active ? "ok" : "muted"}>{c.active ? "Visibile" : "Nascosta"}</Chip>
                  </button>
                </td>
                <td className="px-4 py-3">
                <RowActions>
                {changed && (
                  <button
                    type="button"
                    className="act act-primary"
                    disabled={busyId === c.id || !name.trim()}
                    onClick={() =>
                      patch(c, {
                        name: name.trim(),
                        position: Number.isFinite(parseInt(position, 10)) ? parseInt(position, 10) : c.position,
                      })
                    }
                  >
                    {busyId === c.id ? "..." : "Salva"}
                  </button>
                )}
                <button
                  type="button"
                  className="act"
                  onClick={() => { setDeleting(c); setDeleteError(null); }}
                >
                  Elimina
                </button>
                </RowActions>
                </td>
              </tr>
            );
          })}
            </tbody>
          </table>
        </div>
      )}

      <form onSubmit={create} className="flex flex-wrap items-end gap-2">
        <label className="flex-1 min-w-[180px]">
          <span className="kpi-label block mb-1">
            Nuova categoria
          </span>
          <input
            className={inputClass}
            maxLength={120}
            value={newName}
            placeholder="Es. Casa, Elettronica, Regali"
            onChange={(e) => setNewName(e.target.value)}
          />
        </label>
        <button
          type="submit"
          disabled={creating || !newName.trim()}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white transition cursor-pointer disabled:opacity-50"
        >
          {creating ? "..." : "Aggiungi categoria"}
        </button>
      </form>

      <p className="text-[11px] text-surface-400">
        Il numero nella colonna &ldquo;Posto&rdquo; è l&apos;ordine in cui le categorie compaiono al cliente. Una categoria nascosta sparisce
        dai filtri dello Shop ma resta qui, con i suoi prodotti: i prodotti tornano semplicemente visibili senza filtro.
      </p>

      {deleting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md panel rounded-3xl p-7 bg-surface-950 pop">
            <h3 className="text-xl font-black tracking-tight text-white mb-2">Elimina categoria</h3>
            <p className="text-xs text-surface-300 mb-4">
              Stai per eliminare la categoria{" "}
              <span className="font-semibold text-white">&quot;{deleting.name}&quot;</span>.{" "}
              <strong className="text-surface-200">
                I {deleting.product_count} prodotti che contiene non vengono eliminati
              </strong>
              : restano in vendita e semplicemente non appartengono più a nessuna categoria, finché non li assegni a
              un&apos;altra. Se ti serve solo toglierla dai filtri del cliente, usa &ldquo;Visibile / Nascosta&rdquo;.
            </p>
            {deleteError && <p className="text-xs text-danger-400 mb-3">{deleteError}</p>}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => { setDeleting(null); setDeleteError(null); }}
                className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-surface-300 border border-white/10 transition cursor-pointer"
              >
                Annulla
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleteBusy}
                className="px-4 py-2 rounded-xl bg-danger-600 hover:bg-danger-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
              >
                {deleteBusy ? "Eliminazione..." : "Elimina categoria"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Category checkboxes in a product form: zero or more, from its own shop. */
export function ProductCategoriesField({
  shop,
  value,
  onChange,
}: {
  shop: ShopKey;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const { data: categories, error } = useShopCategories(shop);

  function toggle(id: string) {
    onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  }

  return (
    <div>
      <span className="kpi-label block mb-1">
        Categorie nello Shop
      </span>
      {error ? (
        <p className="text-[11px] text-danger-400">{(error as Error).message}</p>
      ) : categories === undefined ? (
        <p className="text-[11px] text-surface-400">Caricamento categorie...</p>
      ) : categories.length === 0 ? (
        <p className="text-[11px] text-surface-400">
          Nessuna categoria per questo shop: creale nella card &ldquo;Categorie dello shop&rdquo;.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {categories.map((c) => {
            const checked = value.includes(c.id);
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => toggle(c.id)}
                data-active={checked}
                className={`subnav-pill ${c.active ? "" : "opacity-60"}`}
              >
                {checked ? "✓ " : ""}
                {c.name}
                {!c.active && " (nascosta)"}
              </button>
            );
          })}
        </div>
      )}
      <p className="text-[10px] text-surface-400 mt-1">
        Un prodotto può stare in più categorie o in nessuna. Le categorie non cambiano prezzo né disponibilità: servono
        solo al cliente per trovarlo.
      </p>
    </div>
  );
}


// --- Bulk assignment ---

/** Where each shop's products live for admins. Manually added products
    belong to the AliExpress Marketplace and share its categories. */
const PRODUCTS_ENDPOINT: Record<ShopKey, string[]> = {
  internal: ["/api/proxy/products"],
  partner: ["/api/proxy/products"],
  dropshipping: ["/api/proxy/products"],
  cj: ["/api/proxy/cj/products"],
  shopify: ["/api/proxy/shopify/products"],
  aliexpress: ["/api/proxy/aliexpress/products", "/api/proxy/imported-products/products"],
  sosnet_market: ["/api/proxy/sosnet-market/products"],
};

type AssignableProduct = { id: string; name: string; category_ids?: string[]; category?: string };

async function fetchAssignableProducts(shop: ShopKey): Promise<AssignableProduct[]> {
  const lists = await Promise.all(
    PRODUCTS_ENDPOINT[shop].map(async (url) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile caricare i prodotti."));
      return (await res.json()) as AssignableProduct[];
    })
  );
  const all = lists.flat();
  // The internal catalog is one list; keep the selected section only.
  if (shop === "internal" || shop === "partner" || shop === "dropshipping") {
    return all.filter((p) => (p.category ?? "").toLowerCase() === shop);
  }
  return all;
}

/** Adds or removes many products to/from a category at once, e.g. after a
    bulk import. */
function BulkAssign({ shop, categories }: { shop: ShopKey; categories: ShopCategoryRead[] | undefined }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [categoryId, setCategoryId] = useState("");
  const [search, setSearch] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const { data: products, error } = useQuery({
    queryKey: ["shop-categories", "assignable", shop],
    queryFn: () => fetchAssignableProducts(shop),
    enabled: open,
  });

  const category = (categories ?? []).find((c) => c.id === categoryId) ?? null;
  const visible = (products ?? []).filter(
    (p) => !search.trim() || p.name.toLowerCase().includes(search.trim().toLowerCase())
  );

  function toggle(id: string) {
    const next = new Set(picked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setPicked(next);
  }

  /** `add` false removes. The server replaces a product's whole category
      set, so union/difference is computed here from the current set. */
  async function apply(add: boolean) {
    if (!category || picked.size === 0) return;
    setBusy(true);
    setMessage(null);
    try {
      for (const product of (products ?? []).filter((p) => picked.has(p.id))) {
        const current = product.category_ids ?? [];
        const next = add
          ? Array.from(new Set([...current, category.id]))
          : current.filter((id) => id !== category.id);
        if (next.length === current.length && add) continue;
        await saveProductCategories(shop, product.id, next);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["shop-categories", shop] }),
        queryClient.invalidateQueries({ queryKey: ["shop-categories", "assignable", shop] }),
        queryClient.invalidateQueries({ queryKey: ["admin"] }),
      ]);
      setPicked(new Set());
      setMessage({
        ok: true,
        text: add
          ? `Aggiunti a “${category.name}”.`
          : `Tolti da “${category.name}”.`,
      });
    } catch (err: any) {
      setMessage({ ok: false, text: err.message || "Operazione non riuscita." });
    } finally {
      setBusy(false);
    }
  }

  if (!categories || categories.length === 0) return null;

  return (
    <div className="pt-5 border-t border-white/10 space-y-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={open ? "act act-primary" : "act"}
      >
        {open ? "Chiudi assegnazione in blocco" : "Assegna più prodotti a una categoria"}
      </button>
      {open && (
        <div className="space-y-3">
          {error && <p className="text-xs text-danger-400">{(error as Error).message}</p>}
          <div className="flex flex-wrap gap-2">
            <select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className="rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
            >
              <option value="">Scegli la categoria...</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.product_count})
                </option>
              ))}
            </select>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filtra i prodotti per nome..."
              className="flex-1 min-w-[180px] rounded-xl field px-3 py-2 text-sm focus:border-brand-500"
            />
          </div>
          {!products ? (
            <p className="text-xs text-surface-400">Caricamento dei prodotti...</p>
          ) : visible.length === 0 ? (
            <p className="text-xs text-surface-400">Nessun prodotto da assegnare.</p>
          ) : (
            <div className="max-h-72 overflow-y-auto space-y-1.5 pr-1">
              {visible.map((p) => (
                <label
                  key={p.id}
                  className={`flex items-center gap-3 rounded-2xl border px-3 py-2 text-xs cursor-pointer transition ${
                    picked.has(p.id) ? "border-white/40 bg-white/10" : "border-white/10 bg-white/[0.03] hover:bg-white/[0.07]"
                  }`}
                >
                  <input type="checkbox" checked={picked.has(p.id)} onChange={() => toggle(p.id)} />
                  <Orb name={p.name} />
                  <span className="flex-1 truncate font-semibold text-white">{p.name}</span>
                  {category && (p.category_ids ?? []).includes(category.id) && (
                    <Chip tone="ok">già dentro</Chip>
                  )}
                </label>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy || !category || picked.size === 0}
              onClick={() => apply(true)}
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? "Attendi..." : `Aggiungi alla categoria (${picked.size})`}
            </button>
            <button
              type="button"
              disabled={busy || !category || picked.size === 0}
              onClick={() => apply(false)}
              className="px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-surface-300 hover:bg-white/10 text-xs font-semibold cursor-pointer disabled:opacity-50"
            >
              Togli dalla categoria
            </button>
            {message && <span className={`text-xs ${message.ok ? "text-success-400" : "text-danger-400"}`}>{message.text}</span>}
          </div>
        </div>
      )}
    </div>
  );
}
