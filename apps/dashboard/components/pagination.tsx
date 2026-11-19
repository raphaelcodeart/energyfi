"use client";

import { useState } from "react";

export const DEFAULT_PAGE_SIZE = 25;
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

/** Client-side pagination over an already-fetched array.
 *
 * The backing endpoints return full arrays, which is fine at current volumes.
 * Past a few thousand rows per list, paging should move server-side; this
 * hook's API can stay the same.
 *
 * `page` is clamped during render, not fixed in an effect, so a filter that
 * shrinks the list simply shows the last valid page. */
export function usePagination<T>(items: T[], defaultPageSize: number = DEFAULT_PAGE_SIZE) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(defaultPageSize);

  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const startIndex = (currentPage - 1) * pageSize;
  const pageItems = items.slice(startIndex, startIndex + pageSize);

  function changePageSize(next: number) {
    setPageSize(next);
    // Back to page 1, so resizing never skips rows.
    setPage(1);
  }

  return {
    pageItems,
    page: currentPage,
    setPage,
    pageSize,
    setPageSize: changePageSize,
    total,
    totalPages,
    // 1-based, inclusive ("Mostrati X-Y di Z"); both 0 when empty.
    firstShown: total === 0 ? 0 : startIndex + 1,
    lastShown: Math.min(startIndex + pageSize, total),
  };
}

/** The same navigator for a list paged on the server: the page answer gives
    the total, the screen keeps page and size in state. */
export function serverPagination(
  total: number, page: number, pageSize: number,
  setPage: React.Dispatch<React.SetStateAction<number>>, setPageSize: (s: number) => void,
) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(Math.max(page, 1), totalPages);
  const start = (current - 1) * pageSize;
  return {
    page: current, setPage, pageSize,
    setPageSize: (s: number) => { setPageSize(s); setPage(1); },
    total, totalPages,
    firstShown: total === 0 ? 0 : start + 1,
    lastShown: Math.min(start + pageSize, total),
  };
}

/** Page numbers to render, `null` marking an ellipsis. First, last and a
    window around the current page keep the control a fixed width. */
function pageNumbers(current: number, totalPages: number): (number | null)[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
  const pages = new Set<number>([1, totalPages, current, current - 1, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= totalPages).sort((a, b) => a - b);
  const out: (number | null)[] = [];
  let previous = 0;
  for (const p of sorted) {
    if (previous && p - previous > 1) out.push(null);
    out.push(p);
    previous = p;
  }
  return out;
}

type PaginationProps = Pick<
  ReturnType<typeof usePagination<unknown>>,
  "page" | "setPage" | "pageSize" | "setPageSize" | "total" | "totalPages" | "firstShown" | "lastShown"
> & {
  /** Plural noun for the summary line ("clienti", "contratti", ...). */
  label?: string;
};

/** Standard list navigator: range summary, page controls and page-size
    selector. Hidden when everything fits on one page. */
export function Pagination({
  page, setPage, pageSize, setPageSize, total, totalPages, firstShown, lastShown, label = "risultati",
}: PaginationProps) {
  if (total === 0) return null;
  const onlyOnePage = totalPages <= 1;
  // A long single-page list still gets the page-size selector.
  if (onlyOnePage && total <= PAGE_SIZE_OPTIONS[0]!) return null;

  const buttonBase =
    "min-w-[32px] h-8 px-2 rounded-lg text-xs font-semibold border transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed";
  const inactive =
    "bg-white/5 light:bg-surface-900/5 border-white/10 light:border-surface-300 text-surface-300 light:text-surface-600 hover:bg-white/10";

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
      <p className="text-xs text-surface-400 light:text-surface-500">
        Mostrati <strong className="text-white light:text-surface-900">{firstShown}-{lastShown}</strong> di{" "}
        <strong className="text-white light:text-surface-900">{total}</strong> {label}
        {!onlyOnePage && (
          <span className="text-surface-500"> · pagina {page} di {totalPages}</span>
        )}
      </p>

      <div className="flex items-center gap-3">
        {!onlyOnePage && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage(page - 1)}
              disabled={page <= 1}
              aria-label="Pagina precedente"
              className={`${buttonBase} ${inactive}`}
            >
              ‹
            </button>
            {pageNumbers(page, totalPages).map((p, i) =>
              p === null ? (
                <span key={`gap-${i}`} className="px-1 text-xs text-surface-600 select-none">…</span>
              ) : (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPage(p)}
                  aria-current={p === page ? "page" : undefined}
                  className={`${buttonBase} ${
                    p === page ? "bg-brand-600 border-brand-600 text-white" : inactive
                  }`}
                >
                  {p}
                </button>
              )
            )}
            <button
              type="button"
              onClick={() => setPage(page + 1)}
              disabled={page >= totalPages}
              aria-label="Pagina successiva"
              className={`${buttonBase} ${inactive}`}
            >
              ›
            </button>
          </div>
        )}

        <label className="flex items-center gap-1.5 text-xs text-surface-400 light:text-surface-500">
          <span className="hidden sm:inline">Per pagina</span>
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="rounded-lg field px-2 py-1 text-xs bg-surface-900 light:bg-white focus:border-brand-500 cursor-pointer"
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}
