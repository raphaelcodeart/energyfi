"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { GalaxyScene, webglAvailable, type LabelSpec } from "@/components/affiliate/galaxy-scene";
import { affiliateGet, num } from "@/lib/affiliate";
import { at, decodeGalaxy, levelColor, levelPalette, pathTo, searchStars, tourStops, type GalaxyAnswer, type Star } from "@/lib/galaxy";

/*
 * "La tua rete in versione virtuale": a Digital Ambassador flies through their
 * own network in 3D. Only their branch, only for them (no admin version: the
 * whole network would be far too many branches). The branch comes in one
 * answer, so moving around never waits for the server. Loaded on demand
 * (next/dynamic) from the "La mia rete" page, which stays as it is.
 */

type Level = { level: number; total_bc: number; leg_min_bc: number };

const TOUR_STEP_MS = 6000;

export default function NetworkGalaxy({ onClose, levels }: { onClose: () => void; levels?: Level[] }) {
  const q = useQuery({
    queryKey: ["affiliate", "galaxy"],
    queryFn: () => affiliateGet<GalaxyAnswer>("/me/network/galaxy"),
    staleTime: 60_000,
  });
  const stars = useMemo(() => (q.data ? decodeGalaxy(q.data) : null), [q.data]);
  const [supported] = useState(() => (typeof window === "undefined" ? true : webglAvailable()));

  // Esc closes from anywhere; the page behind does not scroll.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  return (
    <div className="fixed inset-0 z-[90] overflow-hidden bg-[#02040d] text-white" role="dialog" aria-modal="true" aria-label="La tua rete in versione virtuale">
      {!supported ? (
        <Notice onClose={onClose} title="Questo dispositivo non mostra il 3D">
          Il browser non supporta WebGL. L&apos;albero normale funziona come sempre.
        </Notice>
      ) : q.isLoading ? (
        <Warp />
      ) : q.error || !stars ? (
        <Notice onClose={onClose} title="Non riesco a caricare la rete">{(q.error as Error | null)?.message ?? "Riprova tra poco."}</Notice>
      ) : stars.length <= 1 ? (
        <Notice onClose={onClose} title="La tua rete è ancora vuota">Chi si iscrive su Mamify con il tuo invito comparirà qui come una nuova stella.</Notice>
      ) : (
        <Tour stars={stars} answer={q.data!} levels={levels} onClose={onClose} />
      )}
    </div>
  );
}

function Tour({ stars, answer, levels, onClose }: { stars: Star[]; answer: GalaxyAnswer; levels?: Level[]; onClose: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const labelLayer = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<GalaxyScene | null>(null);
  const [focus, setFocus] = useState(0);
  const [selected, setSelected] = useState<number | null>(0);
  const [hover, setHover] = useState<number | null>(null);
  const [touring, setTouring] = useState(false);
  const [step, setStep] = useState(0);
  const [query, setQuery] = useState("");
  const [legend, setLegend] = useState(false);
  const [hint, setHint] = useState(true);
  const stops = useMemo(() => tourStops(stars), [stars]);
  const maxLevel = useMemo(() => Math.max(1, levels?.length ?? 0, ...stars.map((s) => s.level ?? 0)), [stars, levels]);

  const go = useCallback((i: number, opts?: { keepTour?: boolean }) => {
    if (!opts?.keepTour) setTouring(false);
    setFocus(i);
    setSelected(i);
    sceneRef.current?.flyTo(i);
  }, []);

  // The scene lives as long as this view; React only drives it.
  useEffect(() => {
    if (!host.current || !labelLayer.current) return;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const lowPower = window.innerWidth < 768 || (navigator.hardwareConcurrency ?? 8) <= 4 || stars.length > 3000;
    const scene = new GalaxyScene(host.current, labelLayer.current, stars, {
      reducedMotion,
      lowPower,
      onPick: (i) => { if (i !== null) go(i); },
      onHover: setHover,
      onUserMove: () => { setTouring(false); setHint(false); },
    });
    sceneRef.current = scene;
    scene.setFocus(0);
    scene.setSelected(0);
    scene.flyTo(0, { intro: true });
    return () => { scene.dispose(); sceneRef.current = null; };
  }, [stars, go]);

  // Highlight, pulse and names follow focus / selection / hover.
  useEffect(() => { sceneRef.current?.setFocus(focus); }, [focus]);
  useEffect(() => { sceneRef.current?.setSelected(selected); }, [selected]);
  useEffect(() => {
    const f = at(stars, focus);
    const kids = [...f.children].sort((a, b) => at(stars, b).size - at(stars, a).size).slice(0, 24);
    const specs: LabelSpec[] = [{ index: focus, kind: "focus" }, ...kids.map((index) => ({ index, kind: "child" as const }))];
    if (selected !== null && selected !== focus && !kids.includes(selected)) specs.push({ index: selected, kind: "selected" });
    if (hover !== null && !specs.some((s) => s.index === hover)) specs.push({ index: hover, kind: "hover" });
    sceneRef.current?.setLabels(specs);
  }, [stars, focus, selected, hover]);

  // Guided tour: the viewer, then the strongest legs, one stop at a time.
  useEffect(() => {
    if (!touring) return;
    const i = stops[step];
    if (i === undefined) {
      const t = setTimeout(() => { setTouring(false); go(0); }, 0);
      return () => clearTimeout(t);
    }
    const t0 = setTimeout(() => {
      setFocus(i);
      setSelected(i);
      sceneRef.current?.flyTo(i, { duration: 2.4 });
    }, 0);
    const t1 = setTimeout(() => setStep((s) => s + 1), TOUR_STEP_MS);
    return () => { clearTimeout(t0); clearTimeout(t1); };
  }, [touring, step, stops, go]);

  const startTour = () => { setStep(0); setTouring(true); setHint(false); };

  // Keyboard: Esc goes up (or closes), arrows move between relatives, space tours.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") {
        if (e.key === "Escape") setQuery("");
        return;
      }
      const cur = selected ?? focus;
      const s = at(stars, cur);
      if (e.key === "Escape") {
        e.preventDefault();
        if (touring) setTouring(false);
        else if (s.parent >= 0) go(s.parent);
        else onClose();
      } else if (e.key === " ") {
        e.preventDefault();
        if (touring) setTouring(false);
        else startTour();
      } else if (e.key === "ArrowUp" && s.parent >= 0) {
        e.preventDefault();
        go(s.parent);
      } else if (e.key === "ArrowDown" && s.children.length) {
        e.preventDefault();
        go(at([...s.children].sort((a, b) => at(stars, b).size - at(stars, a).size), 0));
      } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && s.parent >= 0) {
        e.preventDefault();
        const sib = [...at(stars, s.parent).children].sort((a, b) => at(stars, b).size - at(stars, a).size);
        const k = sib.indexOf(cur) + (e.key === "ArrowRight" ? 1 : -1);
        go(at(sib, (k + sib.length) % sib.length));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const path = pathTo(stars, focus);
  const hits = useMemo(() => searchStars(stars, query), [stars, query]);
  const sel = selected !== null ? at(stars, selected) : null;
  const tourStar = touring ? at(stars, stops[step] ?? 0) : null;
  const active = stars.filter((s) => s.bcp > 0 || s.bct > 0).length;

  return (
    <div className="absolute inset-0">
      <div ref={host} className="absolute inset-0" />
      <div ref={labelLayer} className="galaxy-labels pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,rgba(2,4,13,0.85))]" />

      {/* Top bar */}
      <div className="absolute inset-x-0 top-0 flex flex-wrap items-start justify-between gap-2 p-3 sm:p-4">
        <div className="pointer-events-auto rounded-2xl border border-white/10 bg-black/40 px-4 py-2.5 backdrop-blur-md">
          <p className="text-[10px] font-semibold uppercase tracking-[0.25em] text-accent-300">Versione virtuale</p>
          <p className="text-sm font-black">La tua rete · {num(answer.people)} persone</p>
          <p className="text-[11px] text-surface-300">{num(active)} con punti questo mese</p>
        </div>
        <div className="pointer-events-auto relative order-3 w-full sm:order-none sm:w-80">
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Cerca una persona e vola da lei"
            aria-label="Cerca nella rete virtuale"
            className="w-full rounded-2xl border border-white/15 bg-black/50 px-4 py-2.5 text-sm text-white placeholder:text-surface-400 backdrop-blur-md focus:border-accent-400 focus:outline-none" />
          {hits.length > 0 && (
            <ul className="absolute inset-x-0 top-full z-10 mt-1 overflow-hidden rounded-2xl border border-white/10 bg-[#070b1c]/95 backdrop-blur-md">
              {hits.map((i) => (
                <li key={i}>
                  <button type="button" className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm hover:bg-white/10"
                    onClick={() => { go(i); setQuery(""); }}>
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: levelColor(at(stars, i).level) }} />
                    <span className="min-w-0 flex-1 truncate">{at(stars, i).name}</span>
                    <span className="text-[11px] text-surface-400">{at(stars, i).code}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="pointer-events-auto flex gap-2">
          <button type="button" onClick={touring ? () => setTouring(false) : startTour}
            className="rounded-2xl border border-accent-400/50 bg-gradient-to-r from-brand-600 to-accent-500 px-4 py-2.5 text-sm font-bold shadow-lg shadow-brand-900/40 hover:brightness-110">
            {touring ? "■ Ferma il tour" : "▶ Tour guidato"}
          </button>
          <button type="button" onClick={onClose} autoFocus
            className="rounded-2xl border border-white/15 bg-black/50 px-4 py-2.5 text-sm font-semibold backdrop-blur-md hover:bg-white/10">
            ✕ Torna all&apos;albero
          </button>
        </div>
      </div>

      {/* Person card */}
      {sel && (
        <div className="pointer-events-auto absolute bottom-24 right-3 w-[min(320px,calc(100vw-24px))] rounded-3xl border border-white/10 bg-black/55 p-4 backdrop-blur-md sm:bottom-auto sm:right-4 sm:top-24">
          <div className="flex items-start gap-3">
            <span className="mt-1 h-3.5 w-3.5 shrink-0 rounded-full shadow-[0_0_12px_currentColor]" style={{ background: levelColor(sel.level), color: levelColor(sel.level) }} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-base font-black">{sel.name}{sel.parent < 0 && <span className="ml-1.5 rounded-full bg-accent-500/30 px-2 py-0.5 text-[10px] font-bold">tu</span>}</p>
              <p className="text-[11px] text-surface-300">{sel.code}{sel.level ? ` · Livello ${sel.level}` : " · nessun livello"}{sel.paid ? " · mensilità pagata" : ""}</p>
            </div>
            <button type="button" onClick={() => setSelected(null)} aria-label="Chiudi la scheda" className="text-surface-400 hover:text-white">✕</button>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-center">
            <Figure label="BCP" value={num(sel.bcp)} />
            <Figure label="BCT" value={num(sel.bct)} />
            <Figure label="Diretti" value={num(sel.directs)} />
            <Figure label="In rete" value={num(sel.size)} />
          </div>
          {sel.nextLevel ? (
            <p className="mt-3 text-[11px] text-surface-300">
              Verso il livello {sel.nextLevel}: <b className="text-white">{sel.qualifyingLegs}</b> gambe su 3 al minimo · {sel.activeLegs} gambe con punti.
            </p>
          ) : null}
          {sel.gone && <p className="mt-2 text-[11px] text-danger-300">Non risulta più nella rete Mamify.</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {sel.children.length > 0 && sel.index !== focus && (
              <button type="button" className="rounded-xl bg-white/10 px-3 py-1.5 text-xs font-semibold hover:bg-white/20" onClick={() => go(sel.index)}>Entra nel suo ramo</button>
            )}
            {sel.parent >= 0 && (
              <button type="button" className="rounded-xl bg-white/10 px-3 py-1.5 text-xs font-semibold hover:bg-white/20" onClick={() => go(sel.parent)}>↑ Dal suo sponsor</button>
            )}
          </div>
        </div>
      )}

      {/* Tour caption */}
      {tourStar && (
        <div className="pointer-events-none absolute inset-x-0 bottom-24 flex justify-center px-3">
          <div key={tourStar.index} className="galaxy-caption max-w-xl rounded-3xl border border-white/10 bg-black/55 px-5 py-3 text-center backdrop-blur-md">
            <p className="text-[10px] font-semibold uppercase tracking-[0.25em] text-accent-300">Tappa {Math.min(step + 1, stops.length)} di {stops.length}</p>
            <p className="text-lg font-black">{tourStar.parent < 0 ? "Tu, al centro della tua rete" : `La gamba di ${tourStar.name}`}</p>
            <p className="text-xs text-surface-200">
              {num(tourStar.size + 1)} persone · {num(tourStar.bct)} BCT questo mese
              {tourStar.level ? ` · Livello ${tourStar.level}` : ""}
            </p>
          </div>
        </div>
      )}

      {/* Path */}
      <nav aria-label="Percorso" className="pointer-events-auto absolute bottom-3 left-3 right-3 flex flex-wrap items-center gap-1 sm:right-auto sm:max-w-[60vw]">
        {path.map((i, k) => (
          <span key={i} className="flex items-center gap-1">
            {k > 0 && <span className="text-surface-500">›</span>}
            <button type="button" onClick={() => go(i)}
              className={`max-w-[11rem] truncate rounded-xl border px-2.5 py-1 text-xs backdrop-blur-md ${i === focus ? "border-accent-400/60 bg-accent-500/20 font-bold" : "border-white/10 bg-black/45 hover:bg-white/10"}`}>
              {k === 0 ? "Tu" : at(stars, i).name}
            </button>
          </span>
        ))}
      </nav>

      {/* Legend */}
      <div className="pointer-events-auto absolute bottom-3 right-3 hidden sm:block">
        {legend ? (
          <div className="w-64 rounded-3xl border border-white/10 bg-black/55 p-4 text-[11px] text-surface-200 backdrop-blur-md">
            <div className="mb-2 flex items-center justify-between">
              <p className="font-bold text-white">Come si legge</p>
              <button type="button" onClick={() => setLegend(false)} aria-label="Chiudi la legenda" className="text-surface-400 hover:text-white">✕</button>
            </div>
            <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1">
              {levelPalette(maxLevel).map((l) => (
                <span key={String(l.level)} className="flex items-center gap-1">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: l.color }} />{l.level ? `L${l.level}` : "senza livello"}
                </span>
              ))}
            </div>
            <ul className="space-y-1">
              <li>Più grande è la stella, più grande è il suo ramo.</li>
              <li>Le stelle che brillano hanno punti questo mese.</li>
              <li>Le scie dorate sono i punti che salgono verso di te, lungo la catena degli sponsor.</li>
              <li>Trascina per ruotare, rotella o due dita per avvicinarti, tocca una stella per volare da lei.</li>
              <li>Tastiera: ↑ sponsor · ↓ ramo più grande · ← → fratelli · Esc indietro · spazio tour.</li>
            </ul>
          </div>
        ) : (
          <button type="button" onClick={() => setLegend(true)} className="rounded-2xl border border-white/10 bg-black/45 px-3 py-2 text-xs backdrop-blur-md hover:bg-white/10">Come si legge</button>
        )}
      </div>

      {hint && !touring && (
        <div className="pointer-events-none absolute inset-x-0 top-1/2 flex justify-center px-6">
          <p className="galaxy-hint rounded-full border border-white/10 bg-black/45 px-4 py-2 text-center text-xs text-surface-200 backdrop-blur-md">
            Trascina per girare la rete · tocca una stella per volare da lei · oppure ▶ Tour guidato
          </p>
        </div>
      )}
      {answer.truncated && (
        <p className="pointer-events-none absolute left-1/2 top-24 -translate-x-1/2 rounded-full bg-black/50 px-3 py-1 text-[11px] text-warn-300">
          Mostrate le {num(answer.shown)} persone più vicine a te su {num(answer.people)}.
        </p>
      )}
    </div>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white/[0.06] px-2 py-2">
      <p className="text-[10px] uppercase tracking-wider text-surface-400">{label}</p>
      <p className="text-base font-black tabular-nums">{value}</p>
    </div>
  );
}

function Warp() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5">
      <div className="galaxy-warp" aria-hidden="true">
        {Array.from({ length: 3 }, (_, i) => <span key={i} style={{ animationDelay: `${i * 0.45}s` }} />)}
      </div>
      <p className="text-sm text-surface-200">Sto accendendo le stelle della tua rete…</p>
    </div>
  );
}

function Notice({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="max-w-md rounded-3xl border border-white/10 bg-white/5 p-6 text-center">
        <p className="text-lg font-black">{title}</p>
        <p className="mt-2 text-sm text-surface-300">{children}</p>
        <button type="button" onClick={onClose} autoFocus className="mt-4 rounded-2xl bg-white/10 px-4 py-2 text-sm font-semibold hover:bg-white/20">Torna all&apos;albero</button>
      </div>
    </div>
  );
}
