"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { type CodeEntry, emptyEntries, SupplyPointCodeFields } from "@/components/supply-point-code-fields";
import { AgentPicker } from "@/components/agent-picker";
import type {
  ProductCategoryRead,
  ContractRead,
  CustomerDetailRead,
  CustomerRead,
  ProductCatalogRead,
} from "@/lib/types";

const KIND_LABELS: Record<string, string> = {
  PRIVATE: "Privato",
  SOLE_PROPRIETOR: "Partita IVA",
  COMPANY: "Azienda",
  CONDOMINIUM: "Condominio",
};
const PRIVATE_LIKE = new Set(["PRIVATE", "SOLE_PROPRIETOR"]);

async function fetchCustomers(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

async function fetchCustomerDetail(id: string): Promise<CustomerDetailRead> {
  const res = await fetch(`/api/proxy/customers/${id}`);
  if (!res.ok) throw new Error("Impossibile caricare il cliente.");
  return res.json();
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

export function AdminCreateContractPanel({ onCreated }: { onCreated: (contract: ContractRead) => void }) {
  const { data: customers } = useQuery({ queryKey: ["admin", "customers"], queryFn: fetchCustomers });
  const { data: products } = useQuery({ queryKey: ["admin", "products"], queryFn: fetchProducts });
  const { data: commercialCategories } = useQuery({
    queryKey: ["commercial", "categories"],
    queryFn: async (): Promise<ProductCategoryRead[]> => {
      const res = await fetch("/api/proxy/commercial/categories");
      if (!res.ok) throw new Error("Impossibile caricare le categorie.");
      return res.json();
    },
  });

  const [customerMode, setCustomerMode] = useState<"existing" | "new">("new");

  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const { data: selectedCustomerDetail } = useQuery({
    queryKey: ["admin", "customers", "detail", selectedCustomerId],
    queryFn: () => fetchCustomerDetail(selectedCustomerId),
    enabled: !!selectedCustomerId,
  });
  const [selectedSupplyPointId, setSelectedSupplyPointId] = useState("");

  const [kind, setKind] = useState("PRIVATE");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [pec, setPec] = useState("");
  const [fiscalCode, setFiscalCode] = useState("");
  const [vatNumber, setVatNumber] = useState("");

  // Supply point fields: required for a new customer. One Contract per POD/PDR
  // code (supply-point-code-fields.tsx, as in the self-service wizard), all
  // sharing one address.
  const [energyType, setEnergyType] = useState("ELECTRICITY");
  const [podEntries, setPodEntries] = useState<CodeEntry[]>(() => emptyEntries(1));
  const [pdrEntries, setPdrEntries] = useState<CodeEntry[]>(() => emptyEntries(1));
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [province, setProvince] = useState("");
  const [postalCode, setPostalCode] = useState("");

  const [productVersionId, setProductVersionId] = useState("");
  const [producerAgentId, setProducerAgentId] = useState("");
  const [notes, setNotes] = useState("");
  const [iban, setIban] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const energyProducts = (products ?? []).filter((p) => p.status === "ACTIVE" && p.current_version);
  // Electricity and gas have a POD/PDR, fiber or SIM do not; the product's
  // commercial category decides. Without a category, ask for it.
  const selectedProduct = energyProducts.find((p) => p.current_version?.id === productVersionId);
  const selectedCategory = (commercialCategories ?? []).find((c) => c.id === selectedProduct?.commercial_category_id);
  const needsSupplyPoint = !selectedProduct || !selectedCategory || selectedCategory.requires_supply_point;
  const needsPod = needsSupplyPoint && energyType === "ELECTRICITY";
  const needsPdr = needsSupplyPoint && energyType === "GAS";

  async function createContract(customerId: string, supplyPointId: string | null): Promise<ContractRead> {
    const contractRes = await fetch("/api/proxy/contracts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_id: customerId,
        supply_point_id: supplyPointId,
        product_version_id: productVersionId,
        producer_agent_id: producerAgentId,
        notes: notes || null,
        iban: iban ? iban.replace(/\s/g, "").toUpperCase() : null,
      }),
    });
    if (!contractRes.ok) throw new Error(await contractRes.text());
    return contractRes.json();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      if (customerMode === "new") {
        const customerRes = await fetch("/api/proxy/customers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kind,
            email,
            phone: phone || null,
            pec: pec || null,
            fiscal_code: fiscalCode || null,
            vat_number: vatNumber || null,
            first_name: PRIVATE_LIKE.has(kind) ? firstName : null,
            last_name: PRIVATE_LIKE.has(kind) ? lastName : null,
            company_name: PRIVATE_LIKE.has(kind) ? null : companyName,
          }),
        });
        if (!customerRes.ok) throw new Error(await customerRes.text());
        const newCustomer = (await customerRes.json()) as CustomerRead;

        if (!needsSupplyPoint) {
          const contract = await createContract(newCustomer.id, null);
          onCreated(contract);
          setSuccess(true);
          setTimeout(() => setSuccess(false), 3000);
          return;
        }

        // One supply point and one Contract per code, created sequentially so a
        // partial failure's message ("2° punto: ...") stays meaningful.
        const codeEntries: { entry: CodeEntry; podCode: string | null; pdrCode: string | null }[] = [
          ...(needsPod ? podEntries.map((entry) => ({ entry, podCode: entry.code.toUpperCase(), pdrCode: null })) : []),
          ...(needsPdr ? pdrEntries.map((entry) => ({ entry, podCode: null, pdrCode: entry.code.toUpperCase() })) : []),
        ];
        let lastContract: ContractRead | null = null;
        for (const { entry, podCode, pdrCode } of codeEntries) {
          const supplyPointRes = await fetch(`/api/proxy/customers/${newCustomer.id}/supply-points`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              energy_type: energyType,
              pod_code: podCode,
              pdr_code: pdrCode,
              meter_number: entry.meterNumber || null,
              street,
              city,
              province,
              postal_code: postalCode,
              country: "IT",
            }),
          });
          if (!supplyPointRes.ok) throw new Error(await supplyPointRes.text());
          const newSupplyPoint = await supplyPointRes.json();
          lastContract = await createContract(newCustomer.id, newSupplyPoint.id);
          onCreated(lastContract);
        }
        if (!lastContract) throw new Error("Nessun punto di fornitura inserito.");
        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
        return;
      }

      if (!selectedCustomerId || (needsSupplyPoint && !selectedSupplyPointId)) {
        throw new Error(needsSupplyPoint ? "Seleziona un cliente e un punto di fornitura." : "Seleziona un cliente.");
      }
      const newContract = await createContract(selectedCustomerId, needsSupplyPoint ? selectedSupplyPointId : null);
      onCreated(newContract);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      setSubmitError(err.message || "Impossibile creare il contratto.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto panel rounded-3xl p-8 sm:p-10">
      <div className="kpi-label">Nuova pratica energia</div>
      <h3 className="mt-1 text-3xl font-black tracking-tight text-white mb-2">
        Crea un <span className="text-gradient">Nuovo Contratto</span>
      </h3>
      <p className="text-xs text-surface-300 mb-7">
        Collega un cliente (nuovo o esistente), un&apos;offerta e il promoter/venditore che ha originato la vendita.
      </p>

      {success && (
        <div className="p-4 mb-6 rounded-2xl bg-success-500/10 border border-success-500/20 text-success-400 text-center pop">
          Contratto creato con successo.
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Customer mode */}
        <div className="subnav">
          <button type="button" onClick={() => setCustomerMode("new")}
            data-active={customerMode === "new"} className="subnav-pill cursor-pointer">
            Nuovo Cliente
          </button>
          <button type="button" onClick={() => setCustomerMode("existing")}
            data-active={customerMode === "existing"} className="subnav-pill cursor-pointer">
            Cliente Esistente
          </button>
        </div>

        {customerMode === "existing" ? (
          <div className="space-y-4">
            <div className="space-y-1">
              <label className="kpi-label block">Cliente</label>
              <select required value={selectedCustomerId} onChange={(e) => { setSelectedCustomerId(e.target.value); setSelectedSupplyPointId(""); }}
                className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
                <option value="">— Seleziona cliente —</option>
                {(customers ?? []).map((c) => (
                  <option key={c.id} value={c.id}>{c.display_name} ({c.email})</option>
                ))}
              </select>
            </div>
            {selectedCustomerId && needsSupplyPoint && (
              <div className="space-y-1">
                <label className="kpi-label block">Punto di Fornitura</label>
                <select required value={selectedSupplyPointId} onChange={(e) => setSelectedSupplyPointId(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
                  <option value="">— Seleziona punto di fornitura —</option>
                  {(selectedCustomerDetail?.supply_points ?? []).map((sp) => (
                    <option key={sp.id} value={sp.id}>{sp.label ?? sp.energy_type} ({sp.pod_code ?? sp.pdr_code ?? "—"})</option>
                  ))}
                </select>
                {selectedCustomerDetail && selectedCustomerDetail.supply_points.length === 0 && (
                  <p className="text-[11px] text-warn-400">Questo cliente non ha punti di fornitura. Aggiungine uno dalla sua scheda in Anagrafiche Clienti.</p>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1">
              <label className="kpi-label block">Tipologia Cliente</label>
              <select value={kind} onChange={(e) => setKind(e.target.value)}
                className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
                {Object.entries(KIND_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
            </div>

            {PRIVATE_LIKE.has(kind) ? (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="kpi-label block">Nome Cliente</label>
                  <input required value={firstName} onChange={(e) => setFirstName(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="kpi-label block">Cognome Cliente</label>
                  <input required value={lastName} onChange={(e) => setLastName(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>
            ) : (
              <div className="space-y-1">
                <label className="kpi-label block">Ragione Sociale</label>
                <input required value={companyName} onChange={(e) => setCompanyName(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="kpi-label block">Codice Fiscale</label>
                <input value={fiscalCode} onChange={(e) => setFiscalCode(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>
              <div className="space-y-1">
                <label className="kpi-label block">Partita IVA</label>
                <input value={vatNumber} onChange={(e) => setVatNumber(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="kpi-label block">Email Cliente</label>
                <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>
              <div className="space-y-1">
                <label className="kpi-label block">Cellulare</label>
                <input value={phone} onChange={(e) => setPhone(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>
            </div>

            <div className="space-y-1">
              <label className="kpi-label block">PEC (opzionale)</label>
              <input type="email" value={pec} onChange={(e) => setPec(e.target.value)}
                placeholder="nome@pec.it"
                className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
            </div>

            {needsSupplyPoint && (
            <div className="p-5 rounded-2xl bg-white/[0.04] border border-white/10">
              <p className="text-lg font-black tracking-tight text-white mb-4">Punto di Fornitura</p>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="space-y-1">
                  <label className="kpi-label block">Tipo Energia</label>
                  <select value={energyType} onChange={(e) => setEnergyType(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
                    <option value="ELECTRICITY">Luce</option>
                    <option value="GAS">Gas</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="kpi-label block">Indirizzo</label>
                  <input required value={street} onChange={(e) => setStreet(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1">
                  <label className="kpi-label block">Città</label>
                  <input required value={city} onChange={(e) => setCity(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="kpi-label block">Prov.</label>
                  <input required maxLength={2} value={province} onChange={(e) => setProvince(e.target.value.toUpperCase())}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
                <div className="space-y-1">
                  <label className="kpi-label block">CAP</label>
                  <input required value={postalCode} onChange={(e) => setPostalCode(e.target.value)}
                    className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              </div>

              {needsPod && (
                <SupplyPointCodeFields kind="POD" entries={podEntries} onChange={setPodEntries} />
              )}
              {needsPdr && (
                <SupplyPointCodeFields kind="PDR" entries={pdrEntries} onChange={setPdrEntries} />
              )}
            </div>
            )}
          </div>
        )}

        <div className="p-5 rounded-2xl bg-white/[0.04] border border-white/10 space-y-4">
          <p className="text-lg font-black tracking-tight text-white">Offerta e vendita</p>
          <div className="space-y-1">
            <label className="kpi-label block">Offerta</label>
            <select required value={productVersionId} onChange={(e) => setProductVersionId(e.target.value)}
              className="w-full rounded-xl field px-3 py-2.5 text-sm bg-surface-900 focus:border-brand-500">
              <option value="">— Seleziona offerta —</option>
              {energyProducts.map((p) => (
                <option key={p.id} value={p.current_version!.id}>{p.current_version!.name} ({p.code})</option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="kpi-label block">Promoter / Venditore</label>
            <AgentPicker required allowEmpty={false} value={producerAgentId} onChange={(id) => setProducerAgentId(id)}
              placeholder="— Seleziona promoter —" ariaLabel="Promoter / Venditore" />
          </div>

          <div className="space-y-1">
            <label className="kpi-label block">IBAN per Addebito (opzionale)</label>
            <input value={iban} onChange={(e) => setIban(e.target.value)}
              placeholder="IT00A0000000000000000000000"
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500 uppercase" />
          </div>

          <div className="space-y-1">
            <label className="kpi-label block">Note (opzionale)</label>
            <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="Contesto utile per l'amministrazione: come è arrivato il cliente, promozione di riferimento, preferenze di contatto..."
              className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500 resize-none" />
          </div>
        </div>

        {submitError && (
          <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">
            {submitError}
          </div>
        )}

        <button type="submit" disabled={submitting}
          className="w-full rounded-full bg-gradient-to-r from-brand-600 to-accent-500 hover:brightness-110 py-3.5 text-sm font-black text-white shadow-lg shadow-brand-500/30 transition duration-300 disabled:opacity-50 cursor-pointer mt-2">
          {submitting
            ? "Creazione in corso..."
            : customerMode === "new" && (needsPod ? podEntries.length : 0) + (needsPdr ? pdrEntries.length : 0) > 1
              ? `Genera ${(needsPod ? podEntries.length : 0) + (needsPdr ? pdrEntries.length : 0)} Contratti`
              : "Genera Contratto"}
        </button>
      </form>
    </div>
  );
}
