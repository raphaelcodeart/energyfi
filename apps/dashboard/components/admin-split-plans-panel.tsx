"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CommissionSimulator } from "@/components/commission-simulator";
import { Chip, type ChipTone, Figure, Identity, Orb, RowActions, Stack } from "@/components/ui/data-cells";
import { friendlyApiError } from "@/lib/api-error";
import { formatEuroCents as euro } from "@/lib/product-audience";
import {
  ACCRUAL_LABELS,
  BENEFICIARY_HELP,
  BENEFICIARY_LABELS,
  CALCULATION_LABELS,
  DISTRIBUTION_LABELS,
  FALLBACK_LABELS,
  PLAN_STATUS_LABELS,
  pctLabel,
} from "@/lib/commission-labels";
import type {
  CommercialRoleRead,
  PlanValidationRead,
  ProductCatalogRead,
  ProductCategoryRead,
  SplitPlanRead,
  SplitRuleInput,
} from "@/lib/types";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** A form row: values stay text as typed and become numbers only when sent. */
type RuleRow = {
  key: string;
  label: string;
  beneficiary_type: string;
  network_level: string;
  required_role_id: string;
  calculation_type: string;
  percentage: string;
  amount: string;
  min_amount: string;
  max_amount: string;
  fallback_strategy: string;
};

type PlanForm = {
  name: string;
  scope: "product" | "category";
  product_id: string;
  category_id: string;
  seller_role_id: string;
  valid_from: string;
  valid_to: string;
  fallback_strategy: string;
  distribution_mode: string;
  accrual_trigger: string;
  notes: string;
  rules: RuleRow[];
};

let rowSeq = 0;
const newKey = () => `r${++rowSeq}`;

function emptyRule(): RuleRow {
  return {
    key: newKey(), label: "", beneficiary_type: "SELLER", network_level: "", required_role_id: "",
    calculation_type: "PERCENTAGE", percentage: "", amount: "", min_amount: "", max_amount: "", fallback_strategy: "",
  };
}

function toEuroText(cents: number | null | undefined): string {
  return cents === null || cents === undefined ? "" : (cents / 100).toFixed(2).replace(".", ",");
}

function toCents(text: string): number | null {
  const t = text.trim().replace(",", ".");
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? Math.round(n * 100) : null;
}

function emptyForm(): PlanForm {
  return {
    name: "", scope: "product", product_id: "", category_id: "", seller_role_id: "",
    valid_from: new Date().toISOString().slice(0, 10), valid_to: "", fallback_strategy: "COMPANY",
    distribution_mode: "FULL", accrual_trigger: "PER_INSTALMENT", notes: "",
    rules: [
      { ...emptyRule(), beneficiary_type: "SELLER" },
      { ...emptyRule(), beneficiary_type: "COMPANY", calculation_type: "REMAINDER" },
    ],
  };
}

function formFromPlan(plan: SplitPlanRead): PlanForm {
  return {
    name: plan.name ?? "",
    scope: plan.product_id ? "product" : "category",
    product_id: plan.product_id ?? "",
    category_id: plan.category_id ?? "",
    seller_role_id: plan.seller_role_id ?? "",
    valid_from: plan.valid_from.slice(0, 10),
    valid_to: plan.valid_to ? plan.valid_to.slice(0, 10) : "",
    fallback_strategy: plan.fallback_strategy,
    distribution_mode: plan.distribution_mode,
    accrual_trigger: plan.accrual_trigger,
    notes: plan.notes,
    rules: plan.rules.map((r) => ({
      key: newKey(),
      label: r.label ?? "",
      beneficiary_type: r.beneficiary_type,
      network_level: r.network_level != null ? String(r.network_level) : "",
      required_role_id: r.required_role_id ?? "",
      calculation_type: r.calculation_type,
      percentage: r.percentage != null ? String(Number(r.percentage)).replace(".", ",") : "",
      amount: toEuroText(r.amount_cents),
      min_amount: toEuroText(r.min_amount_cents),
      max_amount: toEuroText(r.max_amount_cents),
      fallback_strategy: r.fallback_strategy ?? "",
    })),
  };
}

function payloadFrom(form: PlanForm) {
  const isPct = (t: string) => t === "PERCENTAGE" || t === "MINIMUM_GUARANTEE";
  const rules: SplitRuleInput[] = form.rules.map((r, i) => ({
    sequence: (i + 1) * 10,
    label: r.label.trim() || null,
    beneficiary_type: r.beneficiary_type,
    network_level: r.network_level.trim() ? Number(r.network_level) : null,
    required_role_id: r.required_role_id || null,
    calculation_type: r.calculation_type,
    percentage: isPct(r.calculation_type) && r.percentage.trim() ? r.percentage.trim().replace(",", ".") : null,
    amount_cents: r.calculation_type === "FIXED_AMOUNT" ? toCents(r.amount) : null,
    min_amount_cents: isPct(r.calculation_type) ? toCents(r.min_amount) : null,
    max_amount_cents: isPct(r.calculation_type) ? toCents(r.max_amount) : null,
    fallback_strategy: r.fallback_strategy || null,
  }));
  return {
    name: form.name.trim() || "Piano senza nome",
    product_id: form.scope === "product" ? form.product_id || null : null,
    category_id: form.scope === "category" ? form.category_id || null : null,
    seller_role_id: form.seller_role_id,
    valid_from: form.valid_from ? new Date(`${form.valid_from}T00:00:00`).toISOString() : null,
    valid_to: form.valid_to ? new Date(`${form.valid_to}T00:00:00`).toISOString() : null,
    fallback_strategy: form.fallback_strategy,
    distribution_mode: form.distribution_mode,
    accrual_trigger: form.accrual_trigger,
    notes: form.notes,
    rules,
  };
}

function statusTone(status: string): ChipTone {
  if (status === "ACTIVE") return "ok";
  if (status === "DRAFT") return "muted";
  return "info";
}

const PLAN_FILTERS: { value: string; label: string }[] = [
  { value: "ALL", label: "Tutti i piani" },
  { value: "ACTIVE", label: "Attivi" },
  { value: "DRAFT", label: "Bozze" },
  { value: "RETIRED", label: "Ritirati" },
];

function calcTone(type: string): ChipTone {
  if (type === "PERCENTAGE" || type === "MINIMUM_GUARANTEE") return "accent";
  if (type === "FIXED_AMOUNT") return "info";
  return "muted";
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

/** Parses a typed percentage ("12,5") into 0..1 for the rule meter. */
function pctRatio(text: string): number | null {
  const n = Number(text.trim().replace(",", "."));
  return text.trim() && Number.isFinite(n) ? Math.max(0, Math.min(1, n / 100)) : null;
}

export function AdminSplitPlansPanel() {
  const queryClient = useQueryClient();
  const { data: plans, isLoading } = useQuery({
    queryKey: ["admin", "split-plans"],
    queryFn: () => getJson<SplitPlanRead[]>("/api/proxy/commissions/plans"),
  });
  const { data: roles } = useQuery({
    queryKey: ["commercial", "roles"],
    queryFn: () => getJson<CommercialRoleRead[]>("/api/proxy/commercial/roles"),
  });
  const { data: categories } = useQuery({
    queryKey: ["commercial", "categories"],
    queryFn: () => getJson<ProductCategoryRead[]>("/api/proxy/commercial/categories"),
  });
  const { data: products } = useQuery({
    queryKey: ["admin", "products"],
    queryFn: () => getJson<ProductCatalogRead[]>("/api/proxy/products"),
  });

  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PlanForm | null>(null);
  const [readOnly, setReadOnly] = useState(false);
  const [validation, setValidation] = useState<PlanValidationRead | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string; details?: string[] } | null>(null);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [showSimulator, setShowSimulator] = useState(false);

  const closeRoles = useMemo(() => (roles ?? []).filter((r) => r.is_active && r.can_close_sales), [roles]);

  // Debounced server validation while typing: totals, remainder and errors come
  // from the engine, not this page.
  useEffect(() => {
    if (!form || readOnly || !form.seller_role_id) return;
    const handle = setTimeout(async () => {
      try {
        const res = await fetch("/api/proxy/commissions/plans/validate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payloadFrom(form)),
        });
        if (res.ok) setValidation(await res.json());
      } catch {
        /* live validation is a convenience; saving validates again */
      }
    }, 400);
    return () => clearTimeout(handle);
  }, [form, readOnly]);

  function openNew() {
    setEditingId(null);
    setReadOnly(false);
    setForm(emptyForm());
    setValidation(null);
    setMessage(null);
    setShowSimulator(false);
  }

  function openPlan(plan: SplitPlanRead) {
    setEditingId(plan.id);
    setReadOnly(plan.status !== "DRAFT");
    setForm(formFromPlan(plan));
    setValidation(plan.validation);
    setMessage(null);
    setShowSimulator(false);
  }

  function updateRule(key: string, patch: Partial<RuleRow>) {
    setForm((f) => (f ? { ...f, rules: f.rules.map((r) => (r.key === key ? { ...r, ...patch } : r)) } : f));
  }

  function moveRule(index: number, delta: number) {
    setForm((f) => {
      if (!f) return f;
      const rules = [...f.rules];
      const target = index + delta;
      if (target < 0 || target >= rules.length) return f;
      const [moved] = rules.splice(index, 1);
      rules.splice(target, 0, moved!);
      return { ...f, rules };
    });
  }

  async function call(url: string, method: string, body?: unknown): Promise<SplitPlanRead | null> {
    const res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let details: string[] | undefined;
      try {
        const data = await res.clone().json();
        if (data?.detail?.errors) details = data.detail.errors;
        if (data?.detail?.message) throw Object.assign(new Error(data.detail.message), { details });
      } catch (e: any) {
        if (e?.details) throw e;
      }
      throw Object.assign(new Error(await friendlyApiError(res)), { details });
    }
    return res.status === 204 ? null : res.json();
  }

  async function run(action: () => Promise<SplitPlanRead | null>, ok: string) {
    setBusy(true);
    setMessage(null);
    try {
      const plan = await action();
      await queryClient.invalidateQueries({ queryKey: ["admin", "split-plans"] });
      if (plan) openPlan(plan);
      setMessage({ kind: "ok", text: ok });
    } catch (err: any) {
      setMessage({ kind: "error", text: err.message || "Operazione non riuscita.", details: err.details });
    } finally {
      setBusy(false);
    }
  }

  const save = () =>
    run(
      () => (editingId
        ? call(`/api/proxy/commissions/plans/${editingId}`, "PATCH", payloadFrom(form!))
        : call("/api/proxy/commissions/plans", "POST", payloadFrom(form!))),
      "Bozza salvata.",
    );

  const filteredPlans = (plans ?? []).filter((p) => statusFilter === "ALL" || p.status === statusFilter);
  const field = "field w-full rounded-xl px-3 py-2 text-sm disabled:opacity-60";
  const small = "field w-full rounded-lg px-2 py-1.5 text-xs disabled:opacity-60";

  return (
    <div className="space-y-6">
      <section className="panel rounded-3xl p-6 text-xs text-surface-300">
        <p className="kpi-label">Come funziona</p>
        <h3 className="mt-1 text-xl font-black tracking-tight text-white">Split Plan: chi prende cosa</h3>
        <div className="mt-3 space-y-1.5">
          <p>
            Uno <strong className="text-white">Split Plan</strong> dice come si divide il <strong className="text-white">margine</strong> di una vendita, per un prodotto (o
            un&apos;intera categoria) e il <strong className="text-white">ruolo di chi vende</strong>. La rete resta una sola: il piano decide solo chi
            prende cosa.
          </p>
          <p>
            Un piano attivo non si modifica: si crea la <strong className="text-white">versione successiva</strong> con la sua data di inizio. Le
            vendite già calcolate restano legate alla versione con cui sono nate.
          </p>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <div className="subnav" role="tablist" aria-label="Filtra i piani">
          {PLAN_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              role="tab"
              aria-selected={statusFilter === f.value}
              data-active={statusFilter === f.value}
              onClick={() => setStatusFilter(f.value)}
              className="subnav-pill"
            >
              {f.label}
            </button>
          ))}
        </div>
        <button onClick={openNew} className="act act-primary ml-auto">
          + Nuovo piano
        </button>
      </div>

      <section className="panel rounded-3xl p-6">
        <div className="mb-4">
          <p className="kpi-label">Catalogo</p>
          <h3 className="mt-1 text-xl font-black tracking-tight text-white">Piani di ripartizione</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr>
                <th className="px-4 py-3">Piano</th>
                <th className="px-4 py-3">Si applica a</th>
                <th className="px-4 py-3">Quote del margine</th>
                <th className="px-4 py-3">In vigore</th>
                <th className="px-4 py-3">Situazione</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {isLoading && <tr><td colSpan={6} className="px-4 py-10 text-center text-surface-400">Caricamento…</td></tr>}
              {!isLoading && filteredPlans.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12">
                    <div className="mx-auto flex max-w-md flex-col items-center gap-2 text-center text-surface-400">
                      <Orb name="piani" icon={<span className="text-sm">%</span>} />
                      <span className="text-sm">Nessun piano. Senza un piano attivo, le vendite di quel prodotto e ruolo non possono essere approvate.</span>
                    </div>
                  </td>
                </tr>
              )}
              {filteredPlans.map((p) => {
                const pctTotal = p.validation ? Number(p.validation.percentage_total) : null;
                return (
                  <tr key={p.id} onClick={() => openPlan(p)} className={`cursor-pointer ${editingId === p.id ? "[&>td]:bg-white/10" : ""}`}>
                    <td className="px-4 py-3">
                      <Identity name={p.name ?? "—"} detail={`versione ${p.version} · ${p.rules.length} regole`} />
                    </td>
                    <td className="px-4 py-3">
                      <Stack
                        title={p.product_code ? `Prodotto ${p.product_code}` : `Categoria ${p.category_name ?? "—"}`}
                        detail={`chi vende: ${p.seller_role_name ?? "—"}`}
                      />
                    </td>
                    <td className="px-4 py-3">
                      {pctTotal != null && Number.isFinite(pctTotal) ? (
                        <div className="w-fit">
                          <Figure
                            value={pctLabel(p.validation?.percentage_total)}
                            detail={p.validation && p.validation.fixed_total_cents > 0 ? `+ ${euro(p.validation.fixed_total_cents)} fissi` : "in percentuale"}
                            ratio={Math.min(1, pctTotal / 100)}
                          />
                        </div>
                      ) : (
                        <span className="text-surface-400">{p.rules.length} regole</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Stack title={`dal ${shortDate(p.valid_from)}`} detail={p.valid_to ? `al ${shortDate(p.valid_to)}` : "senza scadenza"} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Chip tone={statusTone(p.status)}>{PLAN_STATUS_LABELS[p.status] ?? p.status}</Chip>
                        {p.status === "DRAFT" && p.validation && !p.validation.ok && <Chip tone="bad">da completare</Chip>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <RowActions>
                        <button type="button" onClick={(e) => { e.stopPropagation(); openPlan(p); }} className="act">
                          {p.status === "DRAFT" ? "Modifica" : "Apri"}
                        </button>
                      </RowActions>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {form && (
        <section className="panel rise space-y-6 rounded-3xl p-6">
          <div className="flex flex-wrap items-center gap-2">
            <div className="mr-auto">
              <p className="kpi-label">{editingId ? "Piano" : "Bozza"}</p>
              <h3 className="mt-1 text-xl font-black tracking-tight text-white">
                {editingId ? (readOnly ? "Piano (sola lettura)" : "Modifica bozza") : "Nuovo piano"}
              </h3>
            </div>
            {!readOnly && (
              <button onClick={save} disabled={busy} className="act">
                Salva bozza
              </button>
            )}
            {editingId && !readOnly && (
              <button
                onClick={() => run(async () => { await call(`/api/proxy/commissions/plans/${editingId}`, "PATCH", payloadFrom(form)); return call(`/api/proxy/commissions/plans/${editingId}/activate`, "POST"); }, "Piano attivato.")}
                disabled={busy || (validation !== null && !validation.ok)}
                title={validation && !validation.ok ? "Correggi gli errori prima di attivare" : undefined}
                className="act act-primary"
              >
                Attiva
              </button>
            )}
            {editingId && readOnly && (
              <button
                onClick={() => run(() => call(`/api/proxy/commissions/plans/${editingId}/new-version`, "POST", {}), "Creata la bozza della versione successiva: modificala e attivala.")}
                disabled={busy}
                className="act act-primary"
              >
                Nuova versione
              </button>
            )}
            {editingId && readOnly && plans?.find((p) => p.id === editingId)?.status === "ACTIVE" && (
              <button
                onClick={() => { if (confirm("Ritirare il piano da adesso? Le vendite già calcolate non cambiano, le nuove non potranno usarlo.")) run(() => call(`/api/proxy/commissions/plans/${editingId}/retire`, "POST", {}), "Piano ritirato."); }}
                disabled={busy}
                className="act !text-danger-300"
              >
                Ritira
              </button>
            )}
            {editingId && !readOnly && (
              <button
                onClick={() => { if (confirm("Eliminare questa bozza?")) run(async () => { await call(`/api/proxy/commissions/plans/${editingId}`, "DELETE"); setForm(null); setEditingId(null); return null; }, "Bozza eliminata."); }}
                disabled={busy}
                className="act !text-danger-300"
              >
                Elimina bozza
              </button>
            )}
            <button onClick={() => { setForm(null); setEditingId(null); }} className="act">Chiudi</button>
          </div>

          {message && (
            <div className={`pop rounded-2xl border p-3 text-xs ${message.kind === "ok" ? "border-success-500/30 bg-success-500/15 text-success-300" : "border-danger-500/30 bg-danger-500/15 text-danger-300"}`}>
              {message.text}
              {message.details && <ul className="list-disc ml-4 mt-1">{message.details.map((d) => <li key={d}>{d}</li>)}</ul>}
            </div>
          )}

          <fieldset disabled={readOnly} className="grid grid-cols-1 gap-3 text-xs text-surface-300 md:grid-cols-3">
            <label className="space-y-1 md:col-span-3"><span>Nome</span>
              <input className={field} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="es. Fibra 100 – Networker" />
            </label>
            <label className="space-y-1"><span>Vale per</span>
              <select className={field} value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value as "product" | "category" })}>
                <option value="product">Un prodotto</option>
                <option value="category">Tutta una categoria</option>
              </select>
            </label>
            {form.scope === "product" ? (
              <label className="space-y-1"><span>Prodotto</span>
                <select className={field} value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })}>
                  <option value="">Scegli…</option>
                  {(products ?? []).map((p) => <option key={p.id} value={p.id}>{p.code} – {p.current_version?.name ?? ""}</option>)}
                </select>
              </label>
            ) : (
              <label className="space-y-1"><span>Categoria</span>
                <select className={field} value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
                  <option value="">Scegli…</option>
                  {(categories ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
            )}
            <label className="space-y-1"><span>Quando vende un…</span>
              <select className={field} value={form.seller_role_id} onChange={(e) => setForm({ ...form, seller_role_id: e.target.value })}>
                <option value="">Scegli il ruolo…</option>
                {closeRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </label>
            <label className="space-y-1"><span>Valido dal</span>
              <input type="date" className={field} value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
            </label>
            <label className="space-y-1"><span>Valido fino al (escluso, facoltativo)</span>
              <input type="date" className={field} value={form.valid_to} onChange={(e) => setForm({ ...form, valid_to: e.target.value })} />
            </label>
            <label className="space-y-1"><span>Distribuzione</span>
              <select className={field} value={form.distribution_mode} onChange={(e) => setForm({ ...form, distribution_mode: e.target.value })}>
                {Object.entries(DISTRIBUTION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="space-y-1"><span>Se manca un livello nella rete</span>
              <select className={field} value={form.fallback_strategy} onChange={(e) => setForm({ ...form, fallback_strategy: e.target.value })}>
                {Object.entries(FALLBACK_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="space-y-1"><span>Quando maturano le provvigioni</span>
              <select className={field} value={form.accrual_trigger} onChange={(e) => setForm({ ...form, accrual_trigger: e.target.value })}>
                {Object.entries(ACCRUAL_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="space-y-1 md:col-span-3"><span>Note</span>
              <input className={field} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </label>
          </fieldset>

          <div>
            <div className="mb-3 flex items-end justify-between gap-2">
              <div>
                <p className="kpi-label">Regole di distribuzione</p>
                <p className="mt-1 text-lg font-black tracking-tight text-white">Come si divide il margine</p>
              </div>
              <Chip tone="info">{form.rules.length} regole</Chip>
            </div>
            <div className="space-y-3">
              {form.rules.map((r, i) => {
                const pct = r.calculation_type === "PERCENTAGE" || r.calculation_type === "MINIMUM_GUARANTEE";
                const needsLevel = r.beneficiary_type === "UPLINE_LEVEL";
                const canLevel = ["UPLINE_LEVEL", "ROLE_IN_UPLINE", "INFLUENCER"].includes(r.beneficiary_type);
                const canRole = ["UPLINE_LEVEL", "ROLE_IN_UPLINE", "INFLUENCER"].includes(r.beneficiary_type);
                const share = pct ? pctRatio(r.percentage) : null;
                return (
                  <fieldset key={r.key} disabled={readOnly} className="grid grid-cols-2 items-end gap-2 rounded-2xl border border-white/10 bg-black/15 p-4 text-[11px] text-surface-300 md:grid-cols-12">
                    <div className="col-span-2 flex flex-wrap items-center gap-3 md:col-span-12">
                      <Identity
                        name={r.label.trim() || BENEFICIARY_LABELS[r.beneficiary_type] || r.beneficiary_type}
                        detail={`regola ${i + 1} · ${BENEFICIARY_HELP[r.beneficiary_type] ?? ""}`}
                        icon={<span className="text-sm font-black">{i + 1}</span>}
                      />
                      <div className="ml-auto flex flex-wrap items-center gap-2">
                        <Chip tone={r.beneficiary_type === "COMPANY" ? "muted" : "accent"}>{BENEFICIARY_LABELS[r.beneficiary_type] ?? r.beneficiary_type}</Chip>
                        <Chip tone={calcTone(r.calculation_type)}>{CALCULATION_LABELS[r.calculation_type] ?? r.calculation_type}</Chip>
                      </div>
                      {share != null && (
                        <div className="flex w-full items-center gap-3">
                          <div className="meter flex-1"><i style={{ width: `${Math.max(3, share * 100)}%` }} /></div>
                          <span className="text-sm font-black tabular-nums text-white">{pctLabel(r.percentage.replace(",", "."))}</span>
                          <span className="text-[10.5px] text-surface-400">del margine</span>
                        </div>
                      )}
                    </div>
                    <label className="md:col-span-3 space-y-1"><span>A chi</span>
                      <select className={small} value={r.beneficiary_type} title={BENEFICIARY_HELP[r.beneficiary_type]} onChange={(e) => updateRule(r.key, { beneficiary_type: e.target.value })}>
                        {Object.entries(BENEFICIARY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                    </label>
                    <label className="md:col-span-1 space-y-1"><span>{needsLevel ? "Livello" : "Fino al liv."}</span>
                      <input className={small} disabled={!canLevel || readOnly} inputMode="numeric" value={r.network_level} onChange={(e) => updateRule(r.key, { network_level: e.target.value.replace(/\D/g, "") })} placeholder={needsLevel ? "1" : "—"} />
                    </label>
                    <label className="md:col-span-2 space-y-1"><span>Con ruolo</span>
                      <select className={small} disabled={!canRole || readOnly} value={r.required_role_id} onChange={(e) => updateRule(r.key, { required_role_id: e.target.value })}>
                        <option value="">{r.beneficiary_type === "ROLE_IN_UPLINE" ? "Scegli…" : "Qualsiasi"}</option>
                        {(roles ?? []).map((ro) => <option key={ro.id} value={ro.id}>{ro.name}</option>)}
                      </select>
                    </label>
                    <label className="md:col-span-2 space-y-1"><span>Quanto</span>
                      <select className={small} value={r.calculation_type} onChange={(e) => updateRule(r.key, { calculation_type: e.target.value })}>
                        {Object.entries(CALCULATION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                    </label>
                    <label className="md:col-span-1 space-y-1"><span>{pct ? "%" : r.calculation_type === "FIXED_AMOUNT" ? "€" : ""}</span>
                      {pct ? (
                        <input className={small} inputMode="decimal" value={r.percentage} onChange={(e) => updateRule(r.key, { percentage: e.target.value })} placeholder="0" />
                      ) : r.calculation_type === "FIXED_AMOUNT" ? (
                        <input className={small} inputMode="decimal" value={r.amount} onChange={(e) => updateRule(r.key, { amount: e.target.value })} placeholder="0,00" />
                      ) : (
                        <span className="block py-1.5 text-surface-400">resto</span>
                      )}
                    </label>
                    <label className="md:col-span-1 space-y-1"><span>Min €</span>
                      <input className={small} disabled={!pct || readOnly} inputMode="decimal" value={r.min_amount} onChange={(e) => updateRule(r.key, { min_amount: e.target.value })} />
                    </label>
                    <label className="md:col-span-1 space-y-1"><span>Max €</span>
                      <input className={small} disabled={!pct || readOnly} inputMode="decimal" value={r.max_amount} onChange={(e) => updateRule(r.key, { max_amount: e.target.value })} />
                    </label>
                    <div className="md:col-span-1 flex gap-1 justify-end">
                      {!readOnly && (
                        <>
                          <button type="button" onClick={() => moveRule(i, -1)} className="act !px-2" aria-label="Su">↑</button>
                          <button type="button" onClick={() => moveRule(i, 1)} className="act !px-2" aria-label="Giù">↓</button>
                          <button type="button" onClick={() => setForm({ ...form, rules: form.rules.filter((x) => x.key !== r.key) })} className="act !px-2 !text-danger-300" aria-label="Rimuovi">✕</button>
                        </>
                      )}
                    </div>
                    <label className="col-span-2 md:col-span-6 space-y-1"><span>Etichetta (facoltativa)</span>
                      <input className={small} value={r.label} onChange={(e) => updateRule(r.key, { label: e.target.value })} placeholder="es. Direttore della squadra" />
                    </label>
                    <label className="col-span-2 md:col-span-6 space-y-1"><span>Se manca il beneficiario (solo questa regola)</span>
                      <select className={small} value={r.fallback_strategy} onChange={(e) => updateRule(r.key, { fallback_strategy: e.target.value })}>
                        <option value="">Come il piano</option>
                        {Object.entries(FALLBACK_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                    </label>
                  </fieldset>
                );
              })}
            </div>
            {!readOnly && (
              <button onClick={() => setForm({ ...form, rules: [...form.rules, emptyRule()] })} className="act mt-3">
                + Aggiungi regola
              </button>
            )}
          </div>

          {validation && (
            <div className={`space-y-4 rounded-3xl border p-5 text-xs ${validation.ok ? "border-success-500/30 bg-success-500/10" : "border-danger-500/30 bg-danger-500/10"}`}>
              <div className="flex flex-wrap items-center gap-2">
                <p className="kpi-label mr-auto">Verifica del piano</p>
                <Chip tone={validation.ok ? "ok" : "bad"} live={!validation.ok}>{validation.ok ? "Attivabile" : "Da correggere"}</Chip>
              </div>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <div>
                  <p className="kpi-label">Percentuali</p>
                  <p className="mt-1 text-2xl font-black tabular-nums text-white">{pctLabel(validation.percentage_total)}</p>
                </div>
                <div>
                  <p className="kpi-label">Quote fisse</p>
                  <p className="mt-1 text-2xl font-black tabular-nums text-white">{euro(validation.fixed_total_cents)}</p>
                </div>
                {validation.reference_margin_cents != null && (
                  <>
                    <div>
                      <p className="kpi-label">Margine del prodotto</p>
                      <p className="mt-1 text-2xl font-black tabular-nums text-white">{euro(validation.reference_margin_cents)}</p>
                    </div>
                    <div>
                      <p className="kpi-label">Totale residuo</p>
                      <p className="mt-1 text-2xl font-black tabular-nums text-white">{euro(validation.residual_cents ?? 0)}</p>
                      <p className="text-[10.5px] text-surface-400">{validation.has_remainder ? "(alla regola Residuo)" : "(all'azienda)"}</p>
                    </div>
                  </>
                )}
              </div>
              {validation.reference_margin_cents != null && (
                <div className="flex items-end gap-4">
                  <div className="flex-1">
                    <p className="mb-1.5 text-surface-300">Totale distribuito sul margine</p>
                    <div className="meter h-2">
                      <i style={{ width: `${validation.reference_margin_cents > 0 ? Math.max(3, Math.min(100, ((validation.distributed_cents ?? 0) / validation.reference_margin_cents) * 100)) : 3}%` }} />
                    </div>
                  </div>
                  <span className="text-2xl font-black tabular-nums text-brand-300">{euro(validation.distributed_cents ?? 0)}</span>
                </div>
              )}
              <p className="text-surface-300">
                Validità: <strong className="text-white">dal {form.valid_from || "—"}{form.valid_to ? ` al ${form.valid_to}` : ", senza scadenza"}</strong>
              </p>
              <p className={validation.ok ? "font-semibold text-success-300" : "font-semibold text-danger-300"}>
                {validation.ok ? "Il piano è valido e può essere attivato." : "Il piano non può ancora essere attivato:"}
              </p>
              {validation.errors.length > 0 && <ul className="ml-4 list-disc text-danger-300">{validation.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
              {validation.warnings.length > 0 && <ul className="ml-4 list-disc text-warn-300">{validation.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
            </div>
          )}

          {editingId && (
            <div>
              <button onClick={() => setShowSimulator((v) => !v)} className="act">
                {showSimulator ? "Nascondi la prova" : "Prova questo piano su una vendita"}
              </button>
              {showSimulator && (
                <div className="rise mt-3 rounded-3xl border border-white/10 bg-black/15 p-5">
                  <p className="mb-3 text-[11px] text-surface-400">Usa la versione salvata del piano, anche se è ancora una bozza. Non scrive niente.</p>
                  <CommissionSimulator adminMode planId={editingId} />
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
