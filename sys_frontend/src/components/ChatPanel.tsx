import { useEffect, useRef, useState } from "react";
import { X, Send } from "lucide-react";
import { streamChat } from "../api";
import type { ChatEvent } from "../types";

interface Props { sessionId: string; open: boolean; onClose: () => void;
                  onDbWrite: (entity_id: string) => void; }

interface Turn {
  user: string;
  steps: string[];          // "search_web (5 hits)" lines
  reply: string;
  done: boolean;
}

export default function ChatPanel({ sessionId, open, onClose, onDbWrite }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns, busy]);

  const submit = async () => {
    const msg = draft.trim();
    if (!msg || busy) return;
    setDraft(""); setBusy(true);
    const idx = turns.length;
    setTurns((t) => [...t, { user: msg, steps: [], reply: "", done: false }]);
    try {
      await streamChat(sessionId, msg, (ev: ChatEvent) => {
        setTurns((prev) => {
          const next = [...prev]; const cur = { ...next[idx] };
          if (ev.event === "tool_call") {
            cur.steps = [...cur.steps, `→ ${ev.data.tool}`];
          } else if (ev.event === "tool_result") {
            cur.steps = [...cur.steps, `← ${ev.data.tool}: ${ev.data.summary}`];
          } else if (ev.event === "db_write") {
            cur.steps = [...cur.steps, `✓ wrote ${ev.data.entity_id}`];
            onDbWrite(ev.data.entity_id);
          } else if (ev.event === "message") {
            cur.reply = ev.data.text;
          } else if (ev.event === "error") {
            cur.reply = `error: ${ev.data.message}`;
          } else if (ev.event === "done") {
            cur.done = true;
          }
          next[idx] = cur; return next;
        });
      });
    } finally { setBusy(false); }
  };

  return (
    <aside className={`fixed top-0 right-0 h-full w-[420px] bg-panel border-l \
border-border z-40 transition-transform ${open ? "" : "translate-x-full"}`}>
      <header className="flex items-center justify-between p-3 border-b border-border">
        <div className="text-text text-sm">Research chat</div>
        <button onClick={onClose} className="text-muted hover:text-text"
                aria-label="Close chat">
          <X size={16} />
        </button>
      </header>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-4"
           style={{ height: "calc(100% - 110px)" }}>
        {turns.map((t, i) => (
          <div key={i}>
            <div className="text-text text-sm"><span className="text-muted">you · </span>{t.user}</div>
            <div className="mt-2 space-y-0.5">
              {t.steps.map((s, j) => (
                <div key={j} className="text-muted text-xs font-mono">{s}</div>
              ))}
            </div>
            {t.reply && (
              <div className="mt-2 text-text text-sm bg-elev rounded p-2">{t.reply}</div>
            )}
          </div>
        ))}
        {busy && <div className="text-muted text-xs">working…</div>}
      </div>
      <form className="border-t border-border p-2 flex gap-2"
            onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)}
               placeholder="Ask for a vehicle or refinement…"
               className="flex-1 bg-elev border border-border rounded px-2 py-1 \
text-sm text-text placeholder-muted" aria-label="Chat message" />
        <button type="submit" disabled={busy} aria-label="Send"
                className="bg-accent text-bg rounded px-2">
          <Send size={14} />
        </button>
      </form>
    </aside>
  );
}
