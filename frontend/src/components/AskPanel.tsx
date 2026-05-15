import type { AskResponse } from "../types";
import { X } from "lucide-react";

interface Props { result: AskResponse; onDismiss: () => void; onSelect: (id: string) => void }

export default function AskPanel({ result, onDismiss, onSelect }: Props) {
  return (
    <section className="border-b border-border bg-panel p-4">
      <div className="flex justify-between gap-4">
        <p className="text-text">{result.answer}</p>
        <button onClick={onDismiss} aria-label="Dismiss answer"
                className="text-muted hover:text-text">
          <X size={16} />
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {Object.entries(result.filters_used).map(([k, v]) => (
          <span key={k} className="bg-elev border border-border text-xs
                                   text-muted px-2 py-0.5 rounded font-mono">
            {k}: {String(v)}
          </span>
        ))}
      </div>
      {result.entities.length > 0 && (
        <ul className="mt-3 grid gap-1">
          {result.entities.map((e) => (
            <li key={e.id}>
              <button onClick={() => onSelect(e.id)}
                      className="text-accent hover:underline text-sm">
                {e.name} <span className="text-muted">({e.country})</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
