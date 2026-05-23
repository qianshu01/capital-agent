import type { EntitiesPage, EntityDetail, Filters, ChatEvent, ChatHistory } from "./types";

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

export async function streamChat(
  session_id: string,
  message: string,
  on_event: (e: ChatEvent) => void,
): Promise<void> {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id, message }),
  });
  if (!r.body) throw new Error("no stream body");
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
      const eMatch = chunk.match(/^event:\s*(.+)$/m);
      const dMatch = chunk.match(/^data:\s*(.+)$/m);
      if (!eMatch || !dMatch) continue;
      try {
        on_event({ event: eMatch[1].trim() as ChatEvent["event"],
                   data: JSON.parse(dMatch[1].trim()) } as ChatEvent);
      } catch { /* ignore */ }
    }
  }
}

export async function chatHistory(session_id: string): Promise<ChatHistory> {
  const r = await fetch(`/api/chat/${encodeURIComponent(session_id)}`);
  if (!r.ok) throw new Error(`history ${r.status}`);
  return r.json();
}
