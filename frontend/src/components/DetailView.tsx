import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { getEntity } from "../api";

interface Props { id: string; onBack: () => void }

export default function DetailView({ id, onBack }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["entity", id], queryFn: () => getEntity(id),
  });
  if (isLoading) return <div className="p-6 text-muted">Loading…</div>;
  if (error || !data) return <div className="p-6 text-muted">Failed to load.</div>;
  const e = data.entity;
  return (
    <div className="flex-1 overflow-auto p-6">
      <button onClick={onBack}
              className="flex items-center gap-1 text-muted hover:text-text mb-4">
        <ArrowLeft size={14} /> Back
      </button>
      <h2 className="text-2xl font-semibold">{e.name}</h2>
      <p className="text-muted">{e.country} · {e.type} · {e.controlling_family}</p>
      <p className="numeric text-accent text-xl mt-2">
        ${e.estimated_aum_usd?.toLocaleString() ?? "—"}
        <span className="text-muted text-xs ml-2">{e.aum_basis}</span>
      </p>
      {e.thesis_blurb && <p className="mt-4">{e.thesis_blurb}</p>}

      <h3 className="mt-6 text-muted uppercase text-xs tracking-wider">Sources</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {data.sources.map((s, i) => (
          <li key={i}>
            <span className="font-mono text-xs text-muted">{s.field}</span> ·{" "}
            <span className="text-xs">{s.source_type}</span>
            {s.url && <> · <a href={s.url} className="text-accent hover:underline"
                              target="_blank" rel="noreferrer">link</a></>}
            {s.note && <div className="text-muted text-xs">{s.note}</div>}
          </li>
        ))}
      </ul>

      {data.activities.length > 0 && (
        <>
          <h3 className="mt-6 text-muted uppercase text-xs tracking-wider">Activity</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {data.activities.map((a, i) => (
              <li key={i}>
                <span className="font-mono text-xs text-muted">{a.date ?? "—"}</span> ·{" "}
                <span className="text-xs">{a.kind}</span> — {a.description}
              </li>
            ))}
          </ul>
        </>
      )}

      {data.assumptions.length > 0 && (
        <>
          <h3 className="mt-6 text-muted uppercase text-xs tracking-wider">Assumptions</h3>
          <ul className="mt-2 list-disc pl-5 text-sm">
            {data.assumptions.map((t, i) => <li key={i}>{t}</li>)}
          </ul>
        </>
      )}
    </div>
  );
}
