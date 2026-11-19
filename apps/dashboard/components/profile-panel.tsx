"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { PROVINCES } from "@/lib/provinces";
import { Chip } from "@/components/ui/data-cells";

/*
 * "Il mio profilo": fiscal code and residence, filled in whenever the person
 * wants. They are no longer demanded at first login unless the organization
 * turns the "profile_gate" feature back on.
 */

type Profile = {
  fiscal_code: string | null;
  residence_street: string | null;
  residence_city: string | null;
  residence_province: string | null;
  residence_postal_code: string | null;
  is_complete: boolean;
};

export function ProfilePanel({ email }: { email?: string }) {
  const queryClient = useQueryClient();
  const { data: profile } = useQuery({
    queryKey: ["auth", "me", "profile"],
    queryFn: async (): Promise<Profile> => {
      const res = await fetch("/api/proxy/auth/me/profile");
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });
  const [form, setForm] = useState({ fiscal_code: "", street: "", city: "", province: "", postal_code: "" });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!profile) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setForm({
      fiscal_code: profile.fiscal_code ?? "",
      street: profile.residence_street ?? "",
      city: profile.residence_city ?? "",
      province: profile.residence_province ?? "",
      postal_code: profile.residence_postal_code ?? "",
    });
  }, [profile]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch("/api/proxy/auth/me/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fiscal_code: form.fiscal_code,
          residence_street: form.street,
          residence_city: form.city,
          residence_province: form.province,
          residence_postal_code: form.postal_code,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile salvare i dati."));
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      setMessage({ ok: true, text: "Dati salvati." });
    } catch (err: any) {
      setMessage({ ok: false, text: err.message || "Impossibile salvare i dati." });
    } finally {
      setSaving(false);
    }
  }

  const field = "field w-full rounded-2xl px-4 py-3 text-sm";

  return (
    <section className="panel rounded-3xl p-6 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="kpi-label">Il mio profilo</p>
          <h3 className="mt-1 text-2xl font-black tracking-tight text-white">Dati personali</h3>
          <p className="mt-1 text-sm text-surface-300">
            {email && <>Accedi come <strong className="text-white">{email}</strong>. </>}
            Codice fiscale e residenza servono per i documenti fiscali: puoi compilarli quando vuoi.
          </p>
        </div>
        {profile && <Chip tone={profile.is_complete ? "ok" : "warn"}>{profile.is_complete ? "Completo" : "Da completare"}</Chip>}
      </div>

      <form onSubmit={save} className="mt-6 grid gap-4 md:grid-cols-2">
        <label className="space-y-1.5 text-xs text-surface-300 md:col-span-2">
          <span>Codice fiscale (o partita IVA)</span>
          <input
            className={`${field} font-mono uppercase`}
            maxLength={16}
            value={form.fiscal_code}
            onChange={(e) => setForm({ ...form, fiscal_code: e.target.value.toUpperCase().replace(/\s/g, "") })}
          />
        </label>
        <label className="space-y-1.5 text-xs text-surface-300 md:col-span-2">
          <span>Indirizzo di residenza</span>
          <input className={field} placeholder="Via/Piazza e numero civico" value={form.street} onChange={(e) => setForm({ ...form, street: e.target.value })} />
        </label>
        <label className="space-y-1.5 text-xs text-surface-300">
          <span>Città</span>
          <input className={field} value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
        </label>
        <div className="grid grid-cols-2 gap-4">
          <label className="space-y-1.5 text-xs text-surface-300">
            <span>Provincia</span>
            <select className={field} value={form.province} onChange={(e) => setForm({ ...form, province: e.target.value })}>
              <option value="">--</option>
              {PROVINCES.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1.5 text-xs text-surface-300">
            <span>CAP</span>
            <input className={field} inputMode="numeric" maxLength={5} value={form.postal_code} onChange={(e) => setForm({ ...form, postal_code: e.target.value })} />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-3 md:col-span-2">
          <button type="submit" className="act act-primary !h-11 !px-6" disabled={saving}>
            {saving ? "Salvataggio…" : "Salva i dati"}
          </button>
          {message && <span className={`text-sm ${message.ok ? "text-success-300" : "text-danger-300"}`}>{message.text}</span>}
        </div>
      </form>
    </section>
  );
}
