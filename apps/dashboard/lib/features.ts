"use client";

import { useQuery } from "@tanstack/react-query";

/**
 * Optional parts of the platform (organizations/service.py::FEATURE_DEFAULTS),
 * switched by the super admin in Sistema → Impostazioni → Funzioni, or from
 * the command line (python -m app.seed.features). Values arrive with
 * prerequisites already applied.
 */
export type Features = {
  dropshipping: boolean;
  wallet: boolean;
  invoice_cashback: boolean;
  welcome_bonus: boolean;
  friend_referrals: boolean;
  profile_gate: boolean;
  external_wallet: boolean;
};

const ALL_OFF: Features = {
  dropshipping: false,
  wallet: false,
  invoice_cashback: false,
  welcome_bonus: false,
  friend_referrals: false,
  profile_gate: false,
  external_wallet: false,
};

export function useFeatures(): Features {
  const { data } = useQuery({
    queryKey: ["organization", "features"],
    queryFn: async (): Promise<Features> => {
      const res = await fetch("/api/proxy/organizations/me/features");
      if (!res.ok) return ALL_OFF;
      return { ...ALL_OFF, ...(await res.json()) };
    },
    staleTime: 60_000,
  });
  // Hidden until confirmed on, so switched-off sections never flash in.
  return data ?? ALL_OFF;
}

/** Sections that exist only while a feature is on, by nav key (all areas). */
export const FEATURE_OF_SECTION: Record<string, keyof Features> = {
  wallet: "wallet",
  wallets: "wallet",
  cashback: "invoice_cashback",
  "invoice-redemptions": "invoice_cashback",
  partners: "invoice_cashback",
  "friend-referral-claims": "friend_referrals",
  "friend-referrals": "friend_referrals",
  "invita-amici": "friend_referrals",
  "partner-shop": "dropshipping",
  "shopify-products": "dropshipping",
  "imported-products": "dropshipping",
};

export function sectionEnabled(key: string, features: Features): boolean {
  const feature = FEATURE_OF_SECTION[key];
  return feature ? features[feature] : true;
}
