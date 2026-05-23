import { useState, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import TopBar from "./components/TopBar";
import FilterPanel from "./components/FilterPanel";
import EntityTable from "./components/EntityTable";
import ChatPanel from "./components/ChatPanel";
import DetailView from "./components/DetailView";
import { listEntities } from "./api";
import type { Filters } from "./types";

export default function App() {
  const [filters, setFilters] = useState<Filters>({
    sort: "aum_desc", limit: 0, offset: 0,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const sessionId = useRef(crypto.randomUUID()).current;
  const qc = useQueryClient();

  const { data } = useQuery({
    queryKey: ["entities", filters],
    queryFn: () => listEntities(filters),
    placeholderData: (prev) => prev,
  });

  const onDbWrite = (_id: string) => {
    qc.invalidateQueries({ queryKey: ["entities"] });
  };

  return (
    <div className="h-full flex flex-col">
      <TopBar onAsk={(q) => { setChatOpen(true); /* user sends in chat */ void q; }} />
      <button
        onClick={() => setChatOpen((v) => !v)}
        aria-label="Toggle research chat"
        className="fixed bottom-4 right-4 z-50 bg-accent text-bg rounded-full \
shadow-lg p-3 hover:opacity-90">
        <MessageSquare size={18} />
      </button>
      <div className="flex-1 flex overflow-hidden">
        <FilterPanel value={filters} onChange={setFilters} />
        {selected ? (
          <DetailView id={selected} onBack={() => setSelected(null)} />
        ) : (
          <main className="flex-1 flex flex-col overflow-hidden">
            <EntityTable
              entities={data?.results ?? []}
              total={data?.total ?? 0}
              onSelect={setSelected}
              onSort={(s) => setFilters({ ...filters, sort: s, offset: 0 })}
            />
          </main>
        )}
      </div>
      <ChatPanel
        sessionId={sessionId}
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        onDbWrite={onDbWrite}
      />
    </div>
  );
}
