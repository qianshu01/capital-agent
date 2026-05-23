import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { getEntity } from "../api";
import type { Evidence } from "../types";

const QUESTION_LABEL: Record<string, string> = {
  where_capital_sits: "Where the capital sits",
  how_much_capital: "How much capital",
  who_controls: "Who controls it",
  how_deployed: "How it's deployed",
  direct_or_external: "Direct vs external",
  accessibility: "Accessibility for third-party managers",
  why_invest: "Why it would invest",
};
const QUESTION_ORDER = Object.keys(QUESTION_LABEL);

function domainOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return url; }
}

function sourceLine(ev: Evidence, sourceTypes: Map<string, string>): string {
  if (!ev.source_urls.length) return "no sources cited";
  return ev.source_urls
    .map((u) => `${domainOf(u)} (${sourceTypes.get(u) ?? "src"})`)
    .join(" · ");
}

interface Props { id: string; onBack: () => void }

export default function DetailView({ id, onBack }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["entity", id], queryFn: () => getEntity(id),
  });
  if (isLoading) return <div className="p-6 text-muted">Loading…</div>;
  if (error || !data) return <div className="p-6 text-muted">Failed to load.</div>;
  const e = data.entity;
  const sourceTypes = new Map<string, string>();
  for (const s of data.sources) if (s.url) sourceTypes.set(s.url, s.source_type);
  const evidenceByKey = new Map(data.evidence.map((ev) => [ev.question_key, ev]));

  return (
    <div className="flex-1 overflow-auto p-6">
      <button onClick={onBack}
              className="flex items-center gap-1 text-muted hover:text-text mb-4">
        <ArrowLeft size={14} /> Back
      </button>
      <h2 className="text-2xl font-semibold">{e.name}</h2>
      <p className="text-muted text-sm">
        {e.country} · {e.type} · {e.controlling_family ?? "—"}
      </p>
      <p className="numeric text-accent text-xl mt-2">
        ${e.estimated_aum_usd?.toLocaleString() ?? "—"}
        <span className="text-muted text-xs ml-2">{e.aum_basis}</span>
      </p>
      <p className="text-muted text-xs mt-1">
        provenance: {(e as any).provenance ?? "curated"} ·
        conf {(e as any).confidence_score ?? "?"}/5 ·
        evidence {data.evidence.length}/7
      </p>

      <div className="mt-6 space-y-5">
        {QUESTION_ORDER.map((qk) => {
          const ev = evidenceByKey.get(qk);
          return (
            <section key={qk}>
              <h3 className="text-accent text-sm uppercase tracking-wider">
                {QUESTION_LABEL[qk]}
              </h3>
              {ev ? (
                <>
                  <p className="text-sm mt-1">{ev.answer}</p>
                  <p className="text-muted text-xs mt-1">
                    sources: {sourceLine(ev, sourceTypes)}
                  </p>
                </>
              ) : (
                <p className="text-muted text-xs mt-1">— not yet researched —</p>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
