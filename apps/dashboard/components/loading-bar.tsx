"use client";

import { useEffect, useState } from "react";
import { useIsFetching, useIsMutating } from "@tanstack/react-query";

/** Thin colored bar across the top of the page while anything loads or
    saves, so a slow answer never looks like a frozen page. Appears after a
    short delay (quick answers do not flash it) and creeps toward the end
    until the work is done. */
export function LoadingBar() {
  const busy = useIsFetching() + useIsMutating() > 0;
  const [width, setWidth] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (busy) {
      const show = setTimeout(() => { setVisible(true); setWidth(12); }, 150);
      const creep = setInterval(() => setWidth((w) => (w <= 0 ? w : w + (90 - w) * 0.08)), 200);
      return () => { clearTimeout(show); clearInterval(creep); };
    }
    const finish = setTimeout(() => setWidth((w) => (w > 0 ? 100 : 0)), 0);
    const hide = setTimeout(() => { setVisible(false); setWidth(0); }, 350);
    return () => { clearTimeout(finish); clearTimeout(hide); };
  }, [busy]);

  return (
    <div aria-hidden className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-[3px]"
      style={{ opacity: visible ? 1 : 0, transition: "opacity 300ms" }}>
      <div className="h-full rounded-r-full"
        style={{
          width: `${width}%`,
          background: "linear-gradient(90deg, var(--brand, #4488ff), #a855f7, #22d3ee)",
          boxShadow: "0 0 8px var(--brand, #4488ff)",
          transition: "width 200ms ease-out",
        }} />
    </div>
  );
}
