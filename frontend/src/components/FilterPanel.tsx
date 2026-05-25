import type { Filters } from "../types";

const REGIONS: { code: string; label: string; countries: string[] }[] = [
  { code: "East Asia", label: "East Asia", countries: ["HK","JP","KR","CN","MN"] },
  { code: "SEA", label: "SEA", countries: ["SG","MY","ID","TH","PH","VN","KH","LA","MM","BN"] },
  { code: "South Asia", label: "South Asia", countries: ["IN","PK","LK","BD","NP","BT"] },
  { code: "Oceania", label: "Oceania", countries: ["AU","NZ"] },
  { code: "Central Asia", label: "Central Asia", countries: ["KZ"] },
];

const TYPES = ["listed_holding", "sfo", "mfo", "trust", "foundation"];

interface Props { value: Filters; onChange: (f: Filters) => void }

export default function FilterPanel({ value, onChange }: Props) {
  const selectedCountries = new Set((value.country ?? "").split(",").filter(Boolean));
  const toggleCountry = (c: string) => {
    const next = new Set(selectedCountries);
    next.has(c) ? next.delete(c) : next.add(c);
    onChange({ ...value, country: [...next].join(",") || undefined, offset: 0 });
  };
  const selectedTypes = new Set((value.type ?? "").split(",").filter(Boolean));
  const toggleType = (t: string) => {
    const next = new Set(selectedTypes);
    next.has(t) ? next.delete(t) : next.add(t);
    onChange({ ...value, type: [...next].join(",") || undefined, offset: 0 });
  };
  return (
    <aside className="w-56 bg-panel border-r border-border p-3 overflow-y-auto text-sm">
      {REGIONS.map((r) => (
        <section key={r.code} className="mb-4">
          <h3 className="text-muted text-xs uppercase tracking-wider mb-1">{r.label}</h3>
          {r.countries.map((c) => (
            <label key={c} className="flex items-center gap-2 py-0.5 cursor-pointer">
              <input type="checkbox" checked={selectedCountries.has(c)}
                     onChange={() => toggleCountry(c)} className="accent-accent" />
              <span className="font-mono text-xs">{c}</span>
            </label>
          ))}
        </section>
      ))}
      <section className="mb-4">
        <h3 className="text-muted text-xs uppercase tracking-wider mb-1">Type</h3>
        {TYPES.map((t) => (
          <label key={t} className="flex items-center gap-2 py-0.5 cursor-pointer">
            <input type="checkbox" checked={selectedTypes.has(t)}
                   onChange={() => toggleType(t)} className="accent-accent" />
            <span className="text-xs">{t.replace("_", " ")}</span>
          </label>
        ))}
      </section>
      <section>
        <h3 className="text-muted text-xs uppercase tracking-wider mb-1">Min AUM (USD billions)</h3>
        <input
          type="number" min={0} step={0.5}
          value={value.min_aum_usd != null ? value.min_aum_usd / 1e9 : ""}
          onChange={(e) => onChange({
            ...value,
            min_aum_usd: e.target.value ? Number(e.target.value) * 1e9 : undefined,
            offset: 0,
          })}
          className="w-full bg-elev border border-border rounded px-2 py-1 font-mono text-xs text-accent"
          aria-label="Minimum AUM in USD billions"
        />
      </section>
    </aside>
  );
}
