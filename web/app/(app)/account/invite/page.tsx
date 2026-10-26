"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, Copy, MessageCircle, Plus } from "lucide-react";
import { Avatar } from "@/components/Avatar";
import { api, send, type Settings } from "@/lib/api";
import { useApi } from "@/lib/useApi";

const message = (url: string) =>
  `היי! צירפתי אותך ל-FreeRise, שבה אנחנו מנהלים את הכסף של הבית 🏡\nכדי להצטרף צריך רק לבחור שם משתמש וסיסמה כאן:\n${url}\n\nהקישור לשימוש אחד ותקף לשבוע.`;

/** RiseUp-style: one ready-made WhatsApp message with a join link; the partner signs up on their own phone. */
export default function InvitePage() {
  const { data: me } = useApi<{ username: string }>("/auth/me");
  const [url, setUrl] = useState<string | null>(null);
  const [guessed, setGuessed] = useState(false); // no "כתובת FreeRise" set: the link uses this tab's address
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);

  // A fresh link per visit: only its hash is stored, so a link nobody sent can't be used.
  useEffect(() => {
    Promise.all([send<{ token: string }>("POST", "/auth/invites"), api<Settings>("/settings")])
      .then(([{ token }, { app_url }]) => {
        setGuessed(!app_url);
        setUrl(`${app_url ?? location.origin}/join/${token}`);
      })
      .catch(() => setFailed(true));
  }, []);

  async function copy() {
    await navigator.clipboard.writeText(url!);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-5">
      <Link href="/account" className="icon-btn" aria-label="חזרה לחשבון">
        <ArrowRight size={20} />
      </Link>

      <div aria-hidden className="flex h-44 items-center justify-center rounded-[28px] bg-sun-soft">
        <Avatar name={me?.username ?? ""} size={84} className="ring-[6px] ring-sun-soft" />
        <span className="-ms-5 flex size-[84px] items-center justify-center rounded-full border-[3px] border-dashed border-sun-strong bg-surface text-sun-strong ring-[6px] ring-sun-soft">
          <Plus size={34} strokeWidth={2.5} />
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-sm font-bold text-brand">לנהל את הכסף ביחד</p>
        <h1 className="page-title">הוספת שותף או שותפה</h1>
        <p className="text-muted">מי שיצטרף יראה את כל מה שאתם רואים: החשבונות, התזרים, התקציב וההתראות. הוא או היא גם יוכלו לסווג, לתכנן ולשנות הגדרות, בדיוק כמוכם.</p>
        <p className="text-muted">הכנו הודעת הזמנה אישית. רק לשלוח אותה בוואטסאפ, ובקישור בוחרים שם משתמש וסיסמה.</p>
      </div>

      {failed && (
        <p role="alert" className="rounded-xl bg-danger-soft px-3 py-2 text-sm font-semibold text-danger-strong">
          יצירת הקישור נכשלה. רעננו את העמוד ונסו שוב.
        </p>
      )}
      {url && (
        <figure className="flex flex-col gap-1.5">
          <figcaption className="text-xs font-bold text-faint">ההודעה שתישלח</figcaption>
          <p className="rounded-2xl rounded-ss-sm bg-surface p-3.5 text-sm whitespace-pre-line shadow-card [overflow-wrap:anywhere]">{message(url)}</p>
        </figure>
      )}

      <div className="flex flex-col gap-2">
        <a
          href={url ? `https://wa.me/?text=${encodeURIComponent(message(url))}` : undefined}
          aria-disabled={!url}
          target="_blank"
          rel="noreferrer"
          className={`btn-accent ${url ? "" : "pointer-events-none opacity-50"}`}
        >
          <MessageCircle size={19} /> הזמנה בוואטסאפ
        </a>
        <button type="button" className="btn-ghost min-h-12" disabled={!url} onClick={copy}>
          {copied ? <Check size={17} /> : <Copy size={17} />} {copied ? "הקישור הועתק" : "העתקת הקישור"}
        </button>
        {guessed && (
          <p className="text-center text-xs text-muted">
            הקישור בנוי מהכתובת שממנה נכנסת עכשיו. אם היא לא נפתחת מהטלפון, הגדירו את{" "}
            <Link href="/settings#telegram" className="font-bold text-brand underline">
              כתובת FreeRise
            </Link>{" "}
            בהגדרות.
          </p>
        )}
      </div>
    </div>
  );
}
