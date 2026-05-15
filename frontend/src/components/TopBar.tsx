import { Search } from "lucide-react";
import { useState } from "react";

interface Props { onAsk: (q: string) => void }

export default function TopBar({ onAsk }: Props) {
  const [q, setQ] = useState("");
  return (
    <header className="bg-panel border-b border-border px-4 py-3 flex items-center gap-3">
      <div className="text-accent font-mono font-bold">▲ CAPITAL.AGENT</div>
      <form
        className="flex-1 flex"
        onSubmit={(e) => { e.preventDefault(); if (q.trim()) onAsk(q); }}
      >
        <div className="flex-1 flex items-center bg-elev border border-border rounded-md px-3 py-2">
          <Search size={16} className="text-muted mr-2" aria-hidden />
          <input
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Ask about Asian family offices…"
            aria-label="Ask about Asian family offices"
            className="flex-1 bg-transparent outline-none text-text placeholder-muted text-sm"
          />
        </div>
      </form>
    </header>
  );
}
