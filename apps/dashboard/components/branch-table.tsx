"use client";

import { flexRender, getCoreRowModel, useReactTable, createColumnHelper } from "@tanstack/react-table";
import { Chip, Identity, type ChipTone } from "@/components/ui/data-cells";
import type { BranchMemberRead } from "@/lib/types";

const columnHelper = createColumnHelper<BranchMemberRead>();

const STATUS_TONES: Record<string, ChipTone> = {
  ACTIVE: "ok",
  SUSPENDED: "warn",
  TERMINATED: "bad",
  PENDING_APPROVAL: "warn",
};
const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Attivo",
  SUSPENDED: "Sospeso",
  TERMINATED: "Cessato",
  PENDING_APPROVAL: "Da approvare",
};

const columns = [
  columnHelper.accessor("display_name", {
    header: "Collaboratore",
    cell: (info) => {
      const m = info.row.original;
      return (
        <Identity
          name={info.getValue()}
          detail={
            <>
              <span className="font-mono">{m.promoter_code}</span>
              {" · "}
              {m.role_name ?? "—"}
            </>
          }
        />
      );
    },
  }),
  columnHelper.accessor("depth", {
    header: "Livello",
    cell: (info) => {
      const depth = info.getValue();
      return (
        <div className="min-w-[88px]">
          <div className="text-[13px] font-black tabular-nums text-white">
            {depth}
            <span className="text-[10.5px] font-semibold text-surface-400"> / 12</span>
          </div>
          <div className="meter mt-1.5">
            <i style={{ width: `${Math.max(3, Math.min(100, (depth / 12) * 100))}%` }} />
          </div>
        </div>
      );
    },
  }),
  columnHelper.accessor("status", {
    header: "Situazione",
    // Frozen members only reach viewers allowed to see them (the server prunes
    // them and their subtree otherwise, see network/service.py::get_branch), so
    // here they are clearly marked.
    cell: (info) => {
      const status = info.getValue();
      return (
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip tone={STATUS_TONES[status] ?? "muted"} live={status === "PENDING_APPROVAL"}>
            {STATUS_LABELS[status] ?? status}
          </Chip>
          {info.row.original.is_frozen && <Chip tone="bad">Congelato</Chip>}
        </div>
      );
    },
  }),
];

export function BranchTable({
  members,
  onOpenAgent,
}: {
  members: BranchMemberRead[];
  onOpenAgent?: (agentId: string) => void;
}) {
  const table = useReactTable({ data: members, columns, getCoreRowModel: getCoreRowModel() });

  if (members.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-10 text-center">
        <svg className="float-soft h-10 w-10 text-surface-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
        </svg>
        <p className="text-sm text-surface-300">Il tuo ramo è ancora vuoto: invita il primo collaboratore.</p>
      </div>
    );
  }

  return (
    <table className="w-full text-sm text-white">
      <thead>
        {table.getHeaderGroups().map((headerGroup) => (
          <tr key={headerGroup.id} className="text-left">
            {headerGroup.headers.map((header) => (
              <th key={header.id} className="px-4 py-3">
                {flexRender(header.column.columnDef.header, header.getContext())}
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr
            key={row.id}
            onClick={onOpenAgent ? () => onOpenAgent(row.original.agent_id) : undefined}
            className={onOpenAgent ? "cursor-pointer" : undefined}
            title={onOpenAgent ? "Apri la scheda completa" : undefined}
          >
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id} className="px-4 py-3">
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
