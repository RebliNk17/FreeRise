"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, LogOut } from "lucide-react";
import { ApiError, send } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Row, Section } from "./parts";

const MIN = 8; // matches the API

export function AccountCard({ onChanged }: { onChanged: () => void }) {
  const { data: me } = useApi<{ username: string }>("/auth/me");
  const router = useRouter();
  const [editing, setEditing] = useState(false);

  async function logout() {
    await send("POST", "/auth/logout").catch(() => {});
    router.replace("/login");
  }

  return (
    <Section id="account">
      <Row label={me?.username ?? ""} hint="המשתמש המחובר עכשיו">
        <button type="button" className="btn-ghost" onClick={logout}>
          <LogOut size={16} /> יציאה
        </button>
      </Row>
      <Row label="סיסמה" hint="שינוי הסיסמה מנתק את כל המכשירים האחרים. האימות הדו-שלבי לא משתנה.">
        {!editing && (
          <button type="button" className="btn-secondary" onClick={() => setEditing(true)}>
            <KeyRound size={16} /> שינוי סיסמה
          </button>
        )}
      </Row>
      {editing && (
        <PasswordForm
          onCancel={() => setEditing(false)}
          onDone={() => {
            setEditing(false);
            onChanged();
          }}
        />
      )}
    </Section>
  );
}

function PasswordForm({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const next = String(f.get("new"));
    if (next !== f.get("confirm")) return setError("הסיסמאות החדשות לא זהות.");
    setBusy(true);
    setError("");
    try {
      await send("POST", "/auth/password", { current: f.get("current"), new: next });
      onDone();
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(
        status === 403
          ? "הסיסמה הנוכחית שגויה."
          : status === 429
            ? "יותר מדי ניסיונות. נסו שוב בעוד 15 דקות."
            : status === 422
              ? `הסיסמה החדשה צריכה לפחות ${MIN} תווים.`
              : "השמירה נכשלה, נסו שוב.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} onKeyDown={(e) => e.key === "Escape" && onCancel()} className="flex max-w-sm flex-col gap-3.5 pt-1 pb-2">
      <label className="flex flex-col gap-1.5 text-[13px] text-muted">
        סיסמה נוכחית
        <input name="current" type="password" required autoFocus autoComplete="current-password" className="input" dir="ltr" />
      </label>
      <label className="flex flex-col gap-1.5 text-[13px] text-muted">
        סיסמה חדשה (לפחות {MIN} תווים)
        <input name="new" type="password" required minLength={MIN} maxLength={200} autoComplete="new-password" className="input" dir="ltr" />
      </label>
      <label className="flex flex-col gap-1.5 text-[13px] text-muted">
        סיסמה חדשה שוב
        <input name="confirm" type="password" required autoComplete="new-password" className="input" dir="ltr" />
      </label>
      {error && <p className="text-sm text-danger" role="alert">{error}</p>}
      <div className="grid grid-cols-2 gap-2">
        <button className="btn-accent" disabled={busy}>
          {busy ? "שומר…" : "שמירה"}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
          ביטול
        </button>
      </div>
    </form>
  );
}
