import type { EntitiesPage, EntityDetail, AskResponse, Filters } from "./types";

function qs(f: Filters): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  return p.toString();
}

export async function listEntities(f: Filters): Promise<EntitiesPage> {
  const r = await fetch(`/api/entities?${qs(f)}`);
  if (!r.ok) throw new Error(`entities ${r.status}`);
  return r.json();
}

export async function getEntity(id: string): Promise<EntityDetail> {
  const r = await fetch(`/api/entities/${encodeURIComponent(id)}`);
  if (!r.ok) throw new Error(`entity ${r.status}`);
  return r.json();
}

export async function ask(question: string): Promise<AskResponse> {
  const r = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!r.ok) throw new Error(`ask ${r.status}`);
  return r.json();
}
