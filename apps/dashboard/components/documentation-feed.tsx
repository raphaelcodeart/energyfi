"use client";

import type { CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { DocumentationPostRead } from "@/lib/types";

async function fetchFeed(): Promise<DocumentationPostRead[]> {
  const res = await fetch("/api/proxy/documentation");
  if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile caricare la documentazione."));
  return res.json();
}

/**
 * Read-only news/documentation feed, shared by the customer and promoter
 * dashboards. Audience filtering is server-side (documentation/service.py
 * audiences_for_roles).
 */
export function DocumentationFeed() {
  const { data: posts, error, isLoading } = useQuery({
    queryKey: ["documentation", "feed"],
    queryFn: fetchFeed,
  });

  if (isLoading) {
    return <div className="panel rounded-3xl p-6 animate-pulse h-40" />;
  }
  if (error) {
    return <p className="text-sm text-danger-400">{(error as Error).message}</p>;
  }
  if (!posts || posts.length === 0) {
    return (
      <div className="panel rounded-3xl p-10 flex flex-col items-center gap-3 text-center">
        <span className="text-3xl float-soft" aria-hidden="true">📰</span>
        <p className="text-sm text-surface-300">Non c&apos;è ancora nessuna news o documentazione disponibile.</p>
      </div>
    );
  }

  return (
    <div className="grid gap-5 sm:grid-cols-2 stagger">
      {posts.map((p, i) => (
        <article
          key={p.id}
          className="panel rounded-3xl overflow-hidden flex flex-col"
          style={{ "--i": i } as CSSProperties}
        >
          {p.image_url && (
            // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source uploaded photo
            <img src={p.image_url} alt="" className="w-full h-44 object-cover" />
          )}
          <div className="p-6 flex flex-col gap-2.5 flex-1">
            <span className="kpi-label">
              {new Date(p.created_at).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" })}
            </span>
            <h3 className="text-xl font-black tracking-tight text-white">{p.title}</h3>
            {p.body && (
              <p className="text-sm text-surface-300 whitespace-pre-wrap">{p.body}</p>
            )}
            <div className="flex flex-wrap gap-2 mt-2">
              {p.video_url && (
                <a
                  href={p.video_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="act"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Guarda il video
                </a>
              )}
              {p.pdf_url && (
                <a
                  href={p.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="act"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H8a2 2 0 01-2-2V5a2 2 0 012-2h6l6 6v11a2 2 0 01-2 2z" />
                  </svg>
                  {p.pdf_filename ? `Scarica ${p.pdf_filename}` : "Scarica PDF"}
                </a>
              )}
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
