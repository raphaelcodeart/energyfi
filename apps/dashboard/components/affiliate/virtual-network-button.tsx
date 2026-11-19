"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { affiliateGet } from "@/lib/affiliate";

// The virtual tour (three.js) is downloaded only when someone opens it.
const NetworkGalaxy = dynamic(() => import("@/components/affiliate/network-galaxy"), { ssr: false });

type Level = { level: number; total_bc: number; leg_min_bc: number };

/** "Passa alla versione virtuale": the Digital Ambassador's own network in 3D.
 *  Used on both "La mia rete" pages; nothing else on them changes. */
export function VirtualNetworkButton({ levels }: { levels?: Level[] }) {
  const [open, setOpen] = useState(false);
  // Career levels for the legend, when the page does not pass them.
  const { data: catalog } = useQuery({
    queryKey: ["affiliate", "catalog"],
    queryFn: () => affiliateGet<{ config: { career_levels: Level[] } }>("/catalog"),
    enabled: open && !levels,
    staleTime: 300_000,
  });
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}
        onMouseEnter={() => void import("@/components/affiliate/network-galaxy")}
        onFocus={() => void import("@/components/affiliate/network-galaxy")}
        className="relative overflow-hidden rounded-2xl border border-accent-400/50 bg-gradient-to-r from-brand-700 via-brand-600 to-accent-500 px-5 py-3 text-left shadow-lg shadow-brand-900/40 transition hover:brightness-110">
        <span className="block text-[10px] font-semibold uppercase tracking-[0.25em] text-white/80">Novità · 3D</span>
        <span className="block text-sm font-black text-white">Passa alla versione virtuale ✦</span>
      </button>
      {open && <NetworkGalaxy levels={levels ?? catalog?.config.career_levels} onClose={() => setOpen(false)} />}
    </>
  );
}
