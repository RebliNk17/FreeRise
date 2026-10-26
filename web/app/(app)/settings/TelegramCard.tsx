"use client";

import { useEffect, useState } from "react";
import { Check, Copy, ExternalLink, Send } from "lucide-react";
import { Switch } from "@/components/Switch";
import { ApiError, send, type Settings, type TelegramConfig } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Row, Section, type Patch } from "./parts";

const errText = (e: unknown, fallback: string) =>
  e instanceof ApiError && typeof (e.body as { detail?: unknown })?.detail === "string" ? (e.body as { detail: string }).detail : fallback;

export function TelegramCard({ settings, patch }: { settings: Settings; patch: Patch }) {
  const { data: tg, setData, error } = useApi<TelegramConfig>("/settings/telegram");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function act(fn: () => Promise<TelegramConfig | void>, fallback: string) {
    setBusy(true);
    setErr("");
    try {
      const next = await fn();
      if (next) setData(() => next);
      return true;
    } catch (e) {
      setErr(errText(e, fallback));
      return false;
    } finally {
      setBusy(false);
    }
  }

  // Waiting for the user to press Start in Telegram: ask the server to look every 3s.
  const waiting = !!tg?.link_code;
  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(() => {
      if (document.visibilityState === "visible")
        send<TelegramConfig>("POST", "/settings/telegram/link")
          .then((next) => setData(() => next))
          .catch(() => {});
    }, 3000);
    return () => clearInterval(t);
  }, [waiting, setData]);

  const state = !tg?.bot_username ? "bot" : !tg.linked ? "link" : "ready";
  const connected = state === "ready" && !waiting; // setup done: the stepper gives way to a status banner

  return (
    <Section
      id="telegram"
      title="התראות בטלגרם"
      hint={connected ? "ההתראות של FreeRise מגיעות אליכם בטלגרם, דרך בוט פרטי שלכם." : "בוט פרטי שלכם ששולח לכם את ההתראות של FreeRise. ההגדרה לוקחת כ-2 דקות."}
      action={tg?.linked && <Switch label={tg.enabled ? "פעיל" : "כבוי"} checked={tg.enabled} disabled={busy} onChange={(enabled) => act(() => send("PUT", "/settings/telegram", { enabled }), "השינוי נכשל")} />}
    >
      {error && <p className="text-sm text-danger">טעינת הגדרות טלגרם נכשלה.</p>}
      {tg && (
        <>
          {connected ? (
            <>
              <Connected tg={tg} busy={busy} act={act} />
              <Ready tg={tg} settings={settings} patch={patch} busy={busy} act={act} />
            </>
          ) : (
            <ol className="flex flex-col">
              <Step n={1} title="יוצרים בוט אצל BotFather" state={state === "bot" ? "current" : "done"} doneText={tg.bot_username ? `@${tg.bot_username}` : undefined}>
                <CreateBot busy={busy} onToken={(token) => act(() => send("PUT", "/settings/telegram/bot", { token }), "החיבור לבוט נכשל")} />
              </Step>
              <Step n={2} title="מחברים את הצ'אט שלכם לבוט" state={state === "bot" ? "todo" : "current"} doneText={tg.chat_name ?? undefined}>
                {tg.link_url && <LinkChat tg={tg} />}
              </Step>
              <Step n={3} title="בוחרים מה לקבל" state="todo" last />
            </ol>
          )}
          {err && (
            <p role="alert" className="rounded-xl bg-danger-soft px-3 py-2 text-sm font-semibold text-danger-strong">
              {err}
            </p>
          )}
          {state !== "bot" && (
            <div className="mt-2 flex flex-wrap gap-2 border-t border-hairline pt-3">
              {connected && (
                <button className="btn-ghost" disabled={busy} onClick={() => act(() => send("POST", "/settings/telegram/relink"), "הפעולה נכשלה")}>
                  {"העברה לצ'אט אחר"}
                </button>
              )}
              <button
                className="btn-ghost text-danger"
                disabled={busy}
                onClick={() => confirm("לנתק את הבוט מ-FreeRise? ההתראות יפסיקו להגיע לטלגרם.") && act(() => send("DELETE", "/settings/telegram").then(() => api0()), "הניתוק נכשל")}
              >
                ניתוק הבוט
              </button>
            </div>
          )}
        </>
      )}
    </Section>
  );
}

const api0 = (): TelegramConfig => ({ bot_username: null, bot_name: null, chat_name: null, linked: false, enabled: false, kinds: [], feed_kinds: [], link_code: null, link_url: null, all_kinds: {} });

function Step({ n, title, state, doneText, last, children }: { n: number; title: string; state: "todo" | "current" | "done"; doneText?: string; last?: boolean; children?: React.ReactNode }) {
  return (
    <li className="relative flex gap-3 pb-4" aria-current={state === "current" ? "step" : undefined}>
      {!last && <span aria-hidden className={`absolute top-8 bottom-0 right-[13px] w-0.5 rounded-full ${state === "done" ? "bg-brand" : "bg-border"}`} />}
      <span
        aria-hidden
        className={`relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-extrabold ${
          state === "done" ? "bg-brand-fill text-brand-fg" : state === "current" ? "bg-sun text-on-sun" : "bg-sunken text-faint"
        }`}
      >
        {state === "done" ? <Check size={15} strokeWidth={3} /> : n}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2 pt-0.5">
        <p className={`font-bold ${state === "todo" ? "text-faint" : ""}`}>
          {title}
          {state === "done" && doneText && <span className="ms-2 text-sm font-semibold text-brand"><bdi>{doneText}</bdi></span>}
        </p>
        {state === "current" && children}
      </div>
    </li>
  );
}

function CreateBot({ busy, onToken }: { busy: boolean; onToken: (t: string) => Promise<boolean> }) {
  const [token, setToken] = useState("");
  return (
    <div className="flex flex-col gap-3 text-[15px]">
      <ul className="flex list-disc flex-col gap-1.5 ps-5 text-muted marker:text-faint">
        <li>
          בטלגרם, פותחים את{" "}
          <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="link inline-flex items-center gap-1 text-[15px]" dir="ltr">
            @BotFather <ExternalLink size={13} />
          </a>{" "}
          (עם וי כחול) ולוחצים Start.
        </li>
        <li>
          שולחים <Code>/newbot</Code>, בוחרים שם לתצוגה (למשל &quot;FreeRise של משפחת כהן&quot;) ואז שם משתמש שנגמר ב-<Code>bot</Code>.
        </li>
        <li>
          BotFather עונה עם טוקן שנראה כך: <Code>123456789:AAH…</Code>. מעתיקים אותו ומדביקים כאן.
        </li>
      </ul>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await onToken(token.trim())) setToken("");
        }}
      >
        <input
          aria-label="טוקן הבוט"
          className="input min-w-0 flex-1 basis-64 font-mono text-sm"
          dir="ltr"
          autoComplete="off"
          spellCheck={false}
          placeholder="123456789:AAH..."
          value={token}
          onChange={(e) => setToken(e.target.value)}
          required
          pattern="\s*\d+:[\w-]{20,}\s*"
          title="הטוקן מ-BotFather: מספר, נקודתיים ומחרוזת ארוכה"
        />
        <button className="btn" disabled={busy}>
          {busy ? "בודק…" : "חיבור הבוט"}
        </button>
      </form>
      <p className="text-[13px] text-faint">הטוקן נשמר מוצפן בשרת שלכם ולא מוצג שוב. מי שמחזיק בו יכול לשלוח הודעות בשם הבוט, אז לא משתפים אותו.</p>
    </div>
  );
}

function LinkChat({ tg }: { tg: TelegramConfig }) {
  const cmd = `/start ${tg.link_code}`;
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-col gap-3 text-[15px]">
      <p className="text-muted">פותחים את הבוט ולוחצים Start. הדף יזהה את זה לבד תוך כמה שניות.</p>
      <div className="flex flex-wrap items-center gap-3">
        <a href={tg.link_url!} target="_blank" rel="noreferrer" className="btn-accent">
          פתיחת <bdi dir="ltr">@{tg.bot_username}</bdi> בטלגרם <ExternalLink size={16} />
        </a>
        <span className="flex items-center gap-2 text-sm text-muted" role="status">
          <span className="relative flex size-2.5">
            <span className="absolute inline-flex size-full rounded-full bg-sun opacity-60 motion-safe:animate-ping" />
            <span className="relative inline-flex size-2.5 rounded-full bg-sun" />
          </span>
          ממתין ללחיצה על Start
        </span>
      </div>
      <details className="text-sm text-muted">
        <summary className="cursor-pointer font-semibold">הכפתור לא עובד, או רוצים לקבל התראות בקבוצה?</summary>
        <div className="mt-2 flex flex-col gap-2">
          <p>שולחים לבוט את ההודעה הזו (בקבוצה: מוסיפים קודם את הבוט כחבר בקבוצה ושולחים בה):</p>
          <div className="flex items-center gap-2">
            <code dir="ltr" className="flex-1 rounded-lg bg-sunken px-3 py-2 font-mono text-[13px] text-text select-all">
              {cmd}
            </code>
            <button
              type="button"
              className="icon-btn"
              aria-label="העתקת הפקודה"
              onClick={() => navigator.clipboard.writeText(cmd).then(() => setCopied(true), () => {})}
            >
              {copied ? <Check size={17} /> : <Copy size={17} />}
            </button>
          </div>
        </div>
      </details>
    </div>
  );
}

type Act = (fn: () => Promise<TelegramConfig | void>, fallback: string) => Promise<boolean>;

function Connected({ tg, busy, act }: { tg: TelegramConfig; busy: boolean; act: Act }) {
  const [tested, setTested] = useState(false);
  return (
    <div className="mb-3 flex flex-wrap items-center gap-3 rounded-2xl bg-brand-soft p-3">
      <span aria-hidden className={`flex size-10 shrink-0 items-center justify-center rounded-full ${tg.enabled ? "bg-brand-fill text-brand-fg" : "bg-sunken text-faint"}`}>
        <Send size={18} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-bold">
          {"מחובר ל"}
          <bdi>{tg.chat_name ?? "צ'אט שלכם"}</bdi>
        </p>
        <p className="text-sm text-muted">
          {tg.enabled ? "דרך " : "ההתראות מושהות · "}
          <bdi dir="ltr">@{tg.bot_username}</bdi>
        </p>
      </div>
      <button className="btn-secondary" disabled={busy} onClick={async () => setTested(await act(() => send("POST", "/settings/telegram/test"), "השליחה נכשלה"))}>
        {tested ? (
          <>
            <Check size={16} /> נשלחה, בדקו בטלגרם
          </>
        ) : (
          "שליחת הודעת בדיקה"
        )}
      </button>
    </div>
  );
}

function Ready({ tg, settings, patch, busy, act }: { tg: TelegramConfig; settings: Settings; patch: Patch; busy: boolean; act: Act }) {
  const all = Object.keys(tg.all_kinds);
  const alerts = all.filter((k) => !tg.feed_kinds.includes(k));
  const on = new Set(tg.kinds);
  const setKinds = (next: Set<string>) => act(() => send("PUT", "/settings/telegram", { kinds: all.filter((k) => next.has(k)) }), "השינוי נכשל");
  const allOn = alerts.every((k) => on.has(k));
  const checks = (kinds: string[]) => (
    <ul className="grid gap-x-4 sm:grid-cols-2">
      {kinds.map((k) => (
        <li key={k}>
          <label className="flex min-h-10 cursor-pointer items-center gap-2.5 text-[15px]">
            <input
              type="checkbox"
              checked={on.has(k)}
              disabled={busy}
              onChange={(e) => {
                const next = new Set(on);
                if (e.target.checked) next.add(k);
                else next.delete(k);
                setKinds(next);
              }}
            />
            {tg.all_kinds[k]}
          </label>
        </li>
      ))}
    </ul>
  );
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted">
          {allOn ? "כל ההתראות והסיכומים נשלחים" : `${alerts.filter((k) => on.has(k)).length} מתוך ${alerts.length} סוגים נשלחים`}
        </p>
        <button type="button" className="link" onClick={() => setKinds(new Set([...on].filter((k) => !alerts.includes(k)).concat(allOn ? [] : alerts)))}>
          {allOn ? "ניקוי הכל" : "בחירת הכל"}
        </button>
      </div>
      {checks(alerts)}
      <div className="mt-2 flex flex-col gap-0.5 border-t border-hairline pt-3">
        <p className="font-bold">עדכון על כל תנועה</p>
        <p className="text-sm text-muted">הודעה על כל חיוב שנכנס ועל עסקאות בתשלומים. נשלח רק לטלגרם, לא לפעמון באפליקציה.</p>
      </div>
      {checks(tg.feed_kinds)}
      <Row label="כתובת FreeRise" hint="אם האפליקציה זמינה מהטלפון, כל הודעה תכלול קישור ישיר למסך הרלוונטי.">
        <AppUrl value={settings.app_url} patch={patch} />
      </Row>
    </div>
  );
}

function AppUrl({ value, patch }: { value: string | null; patch: Patch }) {
  const [text, setText] = useState(value ?? "");
  return (
    <input
      aria-label="כתובת FreeRise"
      type="url"
      dir="ltr"
      className="input w-full sm:w-72"
      placeholder="https://freerise.example.com"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={async () => {
        if (text.trim() !== (value ?? "") && !(await patch({ app_url: text.trim() || null }))) setText(value ?? "");
      }}
      onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
    />
  );
}

const Code = ({ children }: { children: React.ReactNode }) => (
  <code dir="ltr" className="rounded-md bg-sunken px-1.5 py-0.5 font-mono text-[13px] text-text">
    {children}
  </code>
);
