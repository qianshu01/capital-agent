import type { Entity } from "../types";

interface Props {
  entities: Entity[];
  total: number;
  onSelect: (id: string) => void;
  onSort: (s: "aum_desc" | "aum_asc" | "name" | "data_quality_desc") => void;
}

function fmtAum(v?: number | null): string {
  if (v == null) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

function dqDots(n: number): string {
  return "●".repeat(n) + "○".repeat(5 - n);
}

export default function EntityTable({ entities, total, onSelect, onSort }: Props) {
  return (
    <div className="flex-1 overflow-auto">
      <div className="px-3 py-2 text-muted text-xs">{total} results</div>
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-panel">
          <tr className="text-muted text-xs uppercase">
            <th className="text-left px-3 py-2 cursor-pointer"
                onClick={() => onSort("name")}>Name</th>
            <th className="text-left px-3 py-2">Country</th>
            <th className="text-left px-3 py-2">Type</th>
            <th className="text-left px-3 py-2">Family</th>
            <th className="text-right px-3 py-2 cursor-pointer"
                onClick={() => onSort("aum_desc")}>AUM</th>
            <th className="text-left px-3 py-2 cursor-pointer"
                onClick={() => onSort("data_quality_desc")}>DQ</th>
          </tr>
        </thead>
        <tbody>
          {entities.map((e) => (
            <tr key={e.id}
                className="border-b border-elev hover:bg-panel cursor-pointer"
                onClick={() => onSelect(e.id)}>
              <td className="px-3 py-2">{e.name}</td>
              <td className="px-3 py-2 font-mono text-muted">{e.country}</td>
              <td className="px-3 py-2 text-xs">{e.type}</td>
              <td className="px-3 py-2">{e.controlling_family ?? "—"}</td>
              <td className="px-3 py-2 numeric text-right text-accent">
                {fmtAum(e.estimated_aum_usd)}
              </td>
              <td className="px-3 py-2 numeric text-accent">
                {dqDots(e.data_quality)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
