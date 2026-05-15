import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import TopBar from "./components/TopBar";
import FilterPanel from "./components/FilterPanel";
import EntityTable from "./components/EntityTable";
import AskPanel from "./components/AskPanel";
import DetailView from "./components/DetailView";
import { listEntities, ask } from "./api";
import type { AskResponse, Filters } from "./types";

export default function App() {
  const [filters, setFilters] = useState<Filters>({ sort: "aum_desc", limit: 50, offset: 0 });
  const [askResult, setAskResult] = useState<AskResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [askLoading, setAskLoading] = useState(false);

  const { data } = useQuery({
    queryKey: ["entities", filters],
    queryFn: () => listEntities(filters),
    placeholderData: (prev) => prev,
  });

  const handleAsk = async (q: string) => {
    setAskLoading(true);
    try { setAskResult(await ask(q)); }
    catch { setAskResult({ answer: "Sorry — the assistant is unreachable.",
                            entities: [], filters_used: {} }); }
    finally { setAskLoading(false); }
  };

  return (
    <div className="h-full flex flex-col">
      <TopBar onAsk={handleAsk} />
      <div className="flex-1 flex overflow-hidden">
        <FilterPanel value={filters} onChange={setFilters} />
        {selected ? (
          <DetailView id={selected} onBack={() => setSelected(null)} />
        ) : (
          <main className="flex-1 flex flex-col overflow-hidden">
            {askLoading && <div className="px-4 py-2 text-muted text-sm">Thinking…</div>}
            {askResult && (
              <AskPanel result={askResult}
                        onDismiss={() => setAskResult(null)}
                        onSelect={setSelected} />
            )}
            <EntityTable
              entities={data?.results ?? []}
              total={data?.total ?? 0}
              onSelect={setSelected}
              onSort={(s) => setFilters({ ...filters, sort: s, offset: 0 })}
            />
          </main>
        )}
      </div>
    </div>
  );
}
