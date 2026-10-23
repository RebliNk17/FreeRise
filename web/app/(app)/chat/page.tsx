"use client";

import { useEffect, useRef, useState } from "react";
import { SendHorizontal } from "lucide-react";
import { Card, Status } from "@/components/Card";
import { send } from "@/lib/api";
import { chatWindow, type ChatMessage } from "@/lib/chat";
import { useApi } from "@/lib/useApi";

const SUGGESTIONS = ["כמה הוצאתי החודש על סופר לעומת חודש רגיל?", "באיזה חודש הוצאנו הכי הרבה ולמה?", "איך ייגמר החודש בקצב הנוכחי?"];

/** "שאל אותי על התזרים": questions answered from aggregated cash-flow data by an LLM (off unless configured). */
export default function ChatPage() {
  const { data, error } = useApi<{ enabled: boolean }>("/chat/status");
  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">שאל אותי על התזרים</h1>
      <Status loading={!data} error={error} />
      {data && !data.enabled && <Disabled />}
      {data?.enabled && <Chat />}
    </div>
  );
}

function Disabled() {
  return (
    <Card title="הצ׳אט כבוי">
      <p className="text-sm">כדי להפעיל אותו צריך חיבור למודל שפה בממשק תואם OpenAI (למשל OpenRouter). מגדירים בשרת שלושה משתני סביבה ומפעילים מחדש את ה־API:</p>
      <pre dir="ltr" className="overflow-x-auto rounded-2xl bg-sunken p-3 text-start text-xs leading-relaxed">
        {"FREERISE_LLM_BASE_URL=https://openrouter.ai/api/v1\nFREERISE_LLM_API_KEY=...\nFREERISE_LLM_MODEL=..."}
      </pre>
      <p className="text-xs text-muted">נשלחים למודל רק סיכומים: סכומים לפי חודש וקטגוריה, הוצאות קבועות ויעדי חיסכון. בלי מספרי חשבונות, בלי פרטי התחברות ובלי רשימת עסקאות.</p>
    </Card>
  );
}

function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [messages, busy]);

  async function ask(q: string) {
    const content = q.trim();
    if (!content || busy) return;
    const next = [...messages, { role: "user" as const, content }];
    setMessages(next);
    setText("");
    setBusy(true);
    setFailed(false);
    try {
      const { reply } = await send<{ reply: string }>("POST", "/chat", { messages: chatWindow(next) });
      setMessages((m) => [...m, { role: "assistant", content: reply }]);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {messages.length === 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">התשובות מבוססות על סיכומי התזרים שלכם. אפשר לשאול למשל:</p>
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className="btn-secondary justify-start text-start" onClick={() => ask(s)}>
              {s}
            </button>
          ))}
        </div>
      )}
      <ol className="flex flex-col gap-2.5" aria-live="polite">
        {messages.map((m, i) => (
          <li key={i} className={`max-w-[85%] rounded-[18px] px-3.5 py-2.5 text-[15px] whitespace-pre-wrap ${m.role === "user" ? "self-start bg-brand-fill text-brand-fg" : "card self-end"}`}>
            <span className="sr-only">{m.role === "user" ? "שאלה: " : "תשובה: "}</span>
            {m.content}
          </li>
        ))}
        {busy && <li className="card self-end px-3.5 py-2.5 text-sm text-muted">חושב…</li>}
      </ol>
      {failed && (
        <p className="rounded-2xl bg-danger-soft px-4 py-3 text-sm font-semibold text-danger-strong" role="alert">
          לא התקבלה תשובה. נסו שוב.
        </p>
      )}
      <div ref={end} />
      <form
        className="sticky bottom-[calc(5.5rem+env(safe-area-inset-bottom))] flex gap-2 md:bottom-4"
        onSubmit={(e) => {
          e.preventDefault();
          ask(text);
        }}
      >
        <input className="input flex-1 shadow-card" value={text} onChange={(e) => setText(e.target.value)} placeholder="שאלה על התזרים…" aria-label="שאלה" maxLength={2000} />
        <button className="btn size-12 shrink-0 px-0" aria-label="שליחה" disabled={busy || !text.trim()}>
          <SendHorizontal size={18} className="-scale-x-100" aria-hidden />
        </button>
      </form>
    </>
  );
}
