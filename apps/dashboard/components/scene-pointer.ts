"use client";

import { useEffect } from "react";

/**
 * Feeds the pointer light and 3D tilt (globals.css §10): one pointermove
 * listener for the whole page, throttled to one update per frame.
 */
export function useScenePointer() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    let lastTilt: HTMLElement | null = null;

    function apply(event: PointerEvent) {
      const target = event.target instanceof Element ? event.target : null;
      const panel = target?.closest<HTMLElement>(".panel, [data-tilt]") ?? null;
      if (panel) {
        const rect = panel.getBoundingClientRect();
        panel.style.setProperty("--mx", `${event.clientX - rect.left}px`);
        panel.style.setProperty("--my", `${event.clientY - rect.top}px`);
      }
      const tilt = target?.closest<HTMLElement>("[data-tilt]") ?? null;
      if (lastTilt && lastTilt !== tilt) {
        lastTilt.style.removeProperty("--rx");
        lastTilt.style.removeProperty("--ry");
      }
      if (tilt) {
        const rect = tilt.getBoundingClientRect();
        const nx = (event.clientX - rect.left) / rect.width - 0.5;
        const ny = (event.clientY - rect.top) / rect.height - 0.5;
        tilt.style.setProperty("--rx", `${(-ny * 9).toFixed(2)}deg`);
        tilt.style.setProperty("--ry", `${(nx * 11).toFixed(2)}deg`);
      }
      lastTilt = tilt;
    }

    function onMove(event: PointerEvent) {
      if (event.pointerType === "touch") return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => apply(event));
    }

    document.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("pointermove", onMove);
    };
  }, []);
}
