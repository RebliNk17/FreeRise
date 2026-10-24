"use client";

import Link from "next/link";
import { CircleCheck, TriangleAlert } from "lucide-react";
import { Money } from "@/components/Amount";
import { Card } from "@/components/Card";
import { formatDate, monthName, txnCount } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Health = {
  ok: boolean;
  connections: {
    id: number;
    label: string;
    provider: string;
    owner: string;
    enabled: boolean;
    last_success_at: string | null;
    last_error: string | null;
    months_without_data: string[];
  }[];
  idle_accounts: {
    id: number;
    label: string;
    kind: string;
    last_txn: string | null;
  }[];
  card_bills: {
    bank_txn_id: number;
    date: string;
    issuer: string;
    amount: number;
    status: "mismatch" | "unknown_card";
    gap: number;
  }[];
  uncategorized: number;
};

const ym = (s: string) =>
  `${monthName(Number(s.slice(5, 7)))} ${s.slice(0, 4)}`;

type Conn = Health["connections"][number];
const connProblem = (c: Conn) =>
  !!c.last_error || c.months_without_data.length > 0;

/** One line per kind of problem: what it means and what to do about it. */
function problems(d: Health): { key: string; text: React.ReactNode }[] {
  const out: { key: string; text: React.ReactNode }[] = [];
  const failed = d.connections.filter((c) => c.last_error);
  if (failed.length)
    out.push({
      key: "failed",
      text: (
        <>
          <b>הסנכרון נכשל</b> ב
          {failed.map((c) => `${c.label} · ${c.provider}`).join(", ")}. לרוב
          הסיסמה השתנתה או שצריך קוד חדש —{" "}
          <Link href="/settings/credentials" className="link">
            לעדכון החיבור
          </Link>
          .
        </>
      ),
    });
  const gaps = d.connections.filter((c) => c.months_without_data.length);
  if (gaps.length)
    out.push({
      key: "gaps",
      text: (
        <>
          <b>חודשים בלי נתונים</b> ב
          {gaps.map((c) => `${c.label} · ${c.provider}`).join(", ")}: הסנכרון לא
          הביא עסקאות לחודשים האלה, אז הסכומים שם חסרים. אם השתמשתם בחשבון באותם
          חודשים, כדאי לסנכרן מחדש.
        </>
      ),
    });
  if (d.idle_accounts.length)
    out.push({
      key: "idle",
      text: (
        <>
          <b>
            {d.idle_accounts.length === 1
              ? "חשבון אחד"
              : `${d.idle_accounts.length} חשבונות`}{" "}
            בלי עסקאות ב־90 יום.
          </b>{" "}
          אם עדיין משתמשים בהם, הסנכרון כנראה לא מביא את העסקאות שלהם. אם לא —
          אפשר להתעלם.
        </>
      ),
    });
  const unknown = d.card_bills.filter(
    (b) => b.status === "unknown_card",
  ).length;
  if (unknown)
    out.push({
      key: "unknown",
      text: (
        <>
          <b>חיובי אשראי לכרטיס שלא מחובר</b> ({unknown}): הבנק חייב כרטיס שאין
          לנו את הפירוט שלו, ולכן לא רואים על מה הכסף יצא. כדאי{" "}
          <Link href="/settings/credentials?add=1" className="link">
            לחבר את הכרטיס
          </Link>
          .
        </>
      ),
    });
  const mismatch = d.card_bills.length - unknown;
  if (mismatch)
    out.push({
      key: "mismatch",
      text: (
        <>
          <b>חיובי אשראי שלא מסתדרים</b> ({mismatch}): הסכום שירד מהבנק שונה
          מהעסקאות שיש לנו בכרטיס — כנראה חסרות עסקאות. פירוט למטה.
        </>
      ),
    });
  if (d.uncategorized)
    out.push({
      key: "uncategorized",
      text: (
        <>
          <b>{txnCount(d.uncategorized)} בלי קטגוריה</b>, ולכן לא נספרות נכון
          בתקציב —{" "}
          <Link href="/home?categorize=1" className="link">
            לסיווג
          </Link>
          .
        </>
      ),
    });
  return out;
}

/** "בדיקת תקינות": what needs checking first (with what to do), then per connection last sync and months with no data, idle accounts, card bills that don't add up. */
export function DataHealth() {
  const { data } = useApi<Health>("/data-health");
  if (!data) return null;
  const todo = problems(data);
  // Connections with a problem first; stable otherwise.
  const conns = [...data.connections].sort(
    (a, b) => Number(connProblem(b)) - Number(connProblem(a)),
  );
  return (
    <Card
      title="בדיקת תקינות"
      action={
        data.ok ? (
          <span className="chip bg-brand-soft text-brand">
            <CircleCheck size={14} aria-hidden /> הכל תקין
          </span>
        ) : (
          <span className="chip bg-sun-soft text-sun-strong">
            <TriangleAlert size={14} aria-hidden /> יש מה לבדוק ({todo.length})
          </span>
        )
      }
    >
      {todo.length > 0 && (
        <section
          aria-label="מה לבדוק"
          className="flex flex-col gap-2 rounded-2xl bg-sun-soft p-3 text-[13px] leading-snug"
        >
          <h3 className="text-sm font-bold text-sun-strong">מה לבדוק</h3>
          <ul className="flex flex-col gap-2">
            {todo.map((t) => (
              <li key={t.key} className="flex items-start gap-2">
                <TriangleAlert
                  size={14}
                  className="mt-0.5 shrink-0 text-sun-strong"
                  aria-hidden
                />
                <span>{t.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <ul className="flex flex-col divide-y divide-hairline text-sm">
        {conns.map((c) => (
          <li key={c.id} className="flex flex-col gap-0.5 py-2.5">
            <div className="flex items-baseline gap-2">
              <span className="flex-1 font-bold">
                {connProblem(c) && (
                  <TriangleAlert
                    size={14}
                    className="me-1 inline align-[-2px] text-sun-strong"
                    aria-label="יש בעיה"
                  />
                )}
                {c.label}{" "}
                <span className="font-normal text-muted">· {c.provider}</span>
              </span>
              <span
                className={`text-xs ${c.last_error ? "font-semibold text-danger" : "text-muted"}`}
              >
                {c.last_success_at ? (
                  <>
                    סונכרן{" "}
                    <span dir="ltr">{formatDate(c.last_success_at)}</span>
                  </>
                ) : (
                  "עוד לא סונכרן"
                )}
              </span>
            </div>
            {!c.enabled && <p className="text-xs text-muted">מושבת</p>}
            {c.last_error && (
              <p className="text-xs text-danger">הסנכרון האחרון נכשל</p>
            )}
            {c.months_without_data.length > 0 && (
              <p className="text-xs text-sun-strong">
                חודשים בלי נתונים: {c.months_without_data.map(ym).join(", ")}
              </p>
            )}
          </li>
        ))}
      </ul>
      {data.idle_accounts.length > 0 && (
        <section className="flex flex-col gap-1 border-t border-hairline pt-3 text-sm">
          <h3 className="flex items-center gap-1 font-bold text-sun-strong">
            <TriangleAlert size={14} aria-hidden /> חשבונות בלי פעילות ב־90
            הימים האחרונים
          </h3>
          {data.idle_accounts.map((a) => (
            <p key={a.id} className="flex gap-2">
              <span className="flex-1">{a.label}</span>
              <span className="text-xs text-muted">
                {a.last_txn ? (
                  <>
                    אחרונה <span dir="ltr">{formatDate(a.last_txn)}</span>
                  </>
                ) : (
                  "אין עסקאות"
                )}
              </span>
            </p>
          ))}
        </section>
      )}
      {data.card_bills.length > 0 && (
        <section className="flex flex-col gap-1.5 border-t border-hairline pt-3 text-sm">
          <h3 className="flex items-center gap-1 font-bold text-sun-strong">
            <TriangleAlert size={14} aria-hidden /> חיובי אשראי שלא מסתדרים
          </h3>
          {data.card_bills.map((b) => (
            <p key={b.bank_txn_id} className="text-[13px]">
              {b.status === "unknown_card" ? (
                <>
                  חיוב {b.issuer || "אשראי"} של{" "}
                  <Money value={b.amount} className="font-bold" /> מ־
                  <span dir="ltr">{formatDate(b.date)}</span> לכרטיס שלא מחובר.
                </>
              ) : (
                <>
                  חיוב {b.issuer} מ־<span dir="ltr">{formatDate(b.date)}</span>{" "}
                  {b.gap > 0 ? "גבוה" : "נמוך"} ב־
                  <Money value={Math.abs(b.gap)} className="font-bold" />{" "}
                  מהעסקאות שיש לנו.
                </>
              )}
            </p>
          ))}
        </section>
      )}
    </Card>
  );
}
