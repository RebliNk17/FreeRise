"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronLeft, KeyRound, LogOut, Pencil, Trash2, UserPlus } from "lucide-react";
import { Avatar } from "@/components/Avatar";
import { Status } from "@/components/Card";
import { Sheet, SheetTitle } from "@/components/Sheet";
import { ApiError, send } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Member = { id: number; username: string; name: string };

const MIN = 8; // matches the API

const failure = (err: unknown) => {
  const status = err instanceof ApiError ? err.status : 0;
  if (status === 403) return "הסיסמה שגויה.";
  if (status === 429) return "יותר מדי ניסיונות. נסו שוב בעוד 15 דקות.";
  if (status === 422) return `הסיסמה החדשה צריכה לפחות ${MIN} תווים.`;
  return "השמירה נכשלה, נסו שוב.";
};

/** Who's signed in and who else shares the household: everyone sees and does everything. */
export default function AccountPage() {
  const router = useRouter();
  const { data: members, setData, error } = useApi<Member[]>("/auth/users");
  const { data: me, setData: setMe } = useApi<Member>("/auth/me");
  const [sheet, setSheet] = useState<"name" | "password" | Member | null>(null);
  const [msg, setMsg] = useState<{ text: string; n: number } | null>(null);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 2200);
    return () => clearTimeout(t);
  }, [msg]);
  const toast = (text: string) => setMsg((m) => ({ text, n: (m?.n ?? 0) + 1 }));

  async function logout() {
    await send("POST", "/auth/logout").catch(() => {});
    router.replace("/login");
  }

  const others = members?.filter((m) => m.id !== me?.id) ?? [];
  const place = (m: Member) => members?.findIndex((x) => x.id === m.id) ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <Status loading={!members || !me} error={error} />
      {members && me && (
        <>
          <section aria-labelledby="me-h">
            <div className="flex flex-col items-center gap-2 rounded-[28px] bg-brand-fill px-5 pt-7 pb-16 text-center text-brand-fg">
              <Avatar name={me.name} i={place(me)} size={68} className="ring-4 ring-brand-fg/25" />
              <div>
                <h1 id="me-h" dir="auto" className="font-display text-2xl font-extrabold">
                  {me.name}
                </h1>
                <p className="text-sm text-on-fill-muted">
                  שם משתמש: <span dir="ltr">{me.username}</span>
                </p>
              </div>
              <div className="mt-1 flex flex-wrap justify-center gap-2">
                <button type="button" onClick={() => setSheet("name")} className={pill}>
                  <Pencil size={15} /> עריכת פרטים
                </button>
                <button type="button" onClick={() => setSheet("password")} className={pill}>
                  <KeyRound size={15} /> שינוי סיסמה
                </button>
              </div>
            </div>

            <div className="card relative mx-3 -mt-10 flex flex-col gap-3 p-4 sm:mx-6 sm:p-5">
              <div>
                <h2 className="section-title">בני הבית</h2>
                <p className="text-[13px] text-muted">
                  {others.length ? "רואים ועושים הכול באפליקציה, כל אחד עם כניסה משלו." : "עוד אין כאן אף אחד מלבדך. אפשר להזמין בן או בת זוג לנהל איתך את הכסף."}
                </p>
              </div>
              {others.length > 0 && (
                <ul className="flex flex-col">
                  {others.map((m) => (
                    <li key={m.id} className="flex min-h-14 items-center gap-3 border-t border-hairline first:border-t-0">
                      <Avatar name={m.name} i={place(m)} />
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span dir="auto" className="truncate font-semibold">
                          {m.name}
                        </span>
                        {m.name !== m.username && (
                          <span dir="ltr" className="truncate text-end text-xs text-muted">
                            {m.username}
                          </span>
                        )}
                      </span>
                      <button type="button" className="icon-btn text-muted" aria-label={`הסרת ${m.name}`} title="הסרה" onClick={() => setSheet(m)}>
                        <Trash2 size={17} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <Link href="/account/invite" className="flex min-h-14 items-center gap-3 rounded-2xl bg-sun-soft px-3 font-bold">
                <span className="flex size-10 items-center justify-center rounded-full bg-sun text-on-sun">
                  <UserPlus size={19} />
                </span>
                <span className="flex-1">הוספת שותף או שותפה</span>
                <ChevronLeft size={18} className="text-muted" />
              </Link>
            </div>
          </section>

          <button type="button" onClick={logout} className="card flex min-h-14 items-center gap-3 px-4 font-semibold text-danger">
            <span className="flex size-9 items-center justify-center rounded-xl bg-danger-soft">
              <LogOut size={18} />
            </span>
            יציאה
          </button>
        </>
      )}

      {sheet === "name" && (
        <NameSheet
          me={me!}
          onClose={() => setSheet(null)}
          onDone={(next) => {
            setMe(() => next);
            setData((d) => d?.map((x) => (x.id === next.id ? next : x)));
            setSheet(null);
            toast("הפרטים נשמרו");
          }}
        />
      )}
      {sheet === "password" && (
        <PasswordSheet
          onClose={() => setSheet(null)}
          onDone={() => {
            setSheet(null);
            toast("הסיסמה שונתה");
          }}
        />
      )}
      {typeof sheet === "object" && sheet && (
        <RemoveSheet
          member={sheet}
          onClose={() => setSheet(null)}
          onDone={() => {
            setData((d) => d?.filter((x) => x.id !== sheet.id));
            setSheet(null);
            toast(`הכניסה של ${sheet.name} נמחקה`);
          }}
        />
      )}
      {msg && (
        <p key={msg.n} role="status" className="fixed inset-x-0 bottom-24 z-50 mx-auto w-fit rounded-full bg-brand-fill px-4 py-2 text-sm font-bold text-brand-fg shadow-nav lg:bottom-8">
          {msg.text}
        </p>
      )}
    </div>
  );
}

const pill = "inline-flex min-h-9 items-center gap-1.5 rounded-full border border-brand-fg/40 px-3.5 text-sm font-bold hover:bg-brand-fg/10";

/** Submit state + error for a sheet's form; `run` throws ApiError on failure. */
function useSubmit(run: (f: FormData) => Promise<string | void>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const problem = await run(new FormData(e.currentTarget));
      if (problem) setError(problem);
    } catch (err) {
      setError(failure(err));
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, onSubmit };
}

function Field({ label, hint, ...input }: { label: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex flex-col gap-1.5 text-[13px] text-muted">
      {label}
      <input type="password" required className="input" dir="ltr" {...input} />
      {hint && <span className="text-xs text-faint">{hint}</span>}
    </label>
  );
}

function Actions({ busy, submit, onCancel, danger }: { busy: boolean; submit: string; onCancel: () => void; danger?: boolean }) {
  return (
    <div className="mt-1 grid grid-cols-2 gap-2">
      <button className={danger ? "inline-flex min-h-12 items-center justify-center rounded-2xl bg-danger px-4 font-extrabold text-white disabled:opacity-50" : "btn-accent"} disabled={busy}>
        {busy ? "רגע…" : submit}
      </button>
      <button type="button" className="btn-ghost min-h-12" onClick={onCancel} disabled={busy}>
        ביטול
      </button>
    </div>
  );
}

function NameSheet({ me, onClose, onDone }: { me: Member; onClose: () => void; onDone: (me: Member) => void }) {
  const { busy, error, onSubmit } = useSubmit(async (f) => onDone(await send<Member>("PATCH", "/auth/me", { name: f.get("name") })));
  return (
    <Sheet form labelledBy="name-title" onClose={onClose} header={<SheetTitle id="name-title" title="הפרטים שלי" onClose={onClose} />}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3.5 px-1 pb-2">
        <Field label="שם" hint="כך יופיע לבני הבית" name="name" type="text" dir="auto" defaultValue={me.name} maxLength={40} pattern=".*\S.*" autoFocus autoComplete="given-name" />
        <div className="flex flex-col gap-1.5 text-[13px] text-muted">
          שם משתמש לכניסה
          <p dir="ltr" className="input flex items-center justify-end bg-sunken text-muted">
            {me.username}
          </p>
          <span className="text-xs text-faint">שם המשתמש לא משתנה. איתו ועם הסיסמה נכנסים לאפליקציה.</span>
        </div>
        {error && <p className="text-sm text-danger" role="alert">{error}</p>}
        <Actions busy={busy} submit="שמירה" onCancel={onClose} />
      </form>
    </Sheet>
  );
}

function PasswordSheet({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { busy, error, onSubmit } = useSubmit(async (f) => {
    const next = String(f.get("new"));
    if (next !== f.get("confirm")) return "הסיסמאות החדשות לא זהות.";
    await send("POST", "/auth/password", { current: f.get("current"), new: next });
    onDone();
  });
  return (
    <Sheet form labelledBy="pw-title" onClose={onClose} header={<SheetTitle id="pw-title" title="שינוי סיסמה" onClose={onClose} />}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3.5 px-1 pb-2">
        <p className="text-[13px] text-muted">שאר המכשירים שלך ינותקו. האימות הדו-שלבי לא משתנה.</p>
        <Field label="סיסמה נוכחית" name="current" autoFocus autoComplete="current-password" />
        <Field label={`סיסמה חדשה (לפחות ${MIN} תווים)`} name="new" minLength={MIN} maxLength={200} autoComplete="new-password" />
        <Field label="סיסמה חדשה שוב" name="confirm" autoComplete="new-password" />
        {error && <p className="text-sm text-danger" role="alert">{error}</p>}
        <Actions busy={busy} submit="שמירה" onCancel={onClose} />
      </form>
    </Sheet>
  );
}

function RemoveSheet({ member, onClose, onDone }: { member: Member; onClose: () => void; onDone: () => void }) {
  const { busy, error, onSubmit } = useSubmit(async (f) => {
    await send("DELETE", `/auth/users/${member.id}`, { current: f.get("current") });
    onDone();
  });
  return (
    <Sheet form labelledBy="rm-title" onClose={onClose} header={<SheetTitle id="rm-title" title={`להסיר את ${member.name}?`} onClose={onClose} />}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3.5 px-1 pb-2">
        <p className="text-[13px] text-muted">הכניסה של {member.name} תימחק, וכל המכשירים שמחוברים איתה ינותקו. הנתונים של הבית לא משתנים, ואפשר להזמין שוב בכל זמן.</p>
        <Field label="הסיסמה שלך, לאישור" name="current" autoFocus autoComplete="current-password" />
        {error && <p className="text-sm text-danger" role="alert">{error}</p>}
        <Actions busy={busy} submit="הסרה" onCancel={onClose} danger />
      </form>
    </Sheet>
  );
}
