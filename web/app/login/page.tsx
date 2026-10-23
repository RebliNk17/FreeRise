"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Logo } from "@/components/Logo";
import { ApiError, api, send } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [totp, setTotp] = useState(true);

  useEffect(() => {
    api<{ totp: boolean }>("/auth/config")
      .then((c) => setTotp(c.totp))
      .catch(() => {});
  }, []);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      await send("POST", "/auth/login", {
        username: f.get("username"),
        password: f.get("password"),
        totp: f.get("totp") ?? "",
      });
      router.replace("/home");
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(
        status === 429
          ? "יותר מדי ניסיונות. נסו שוב בעוד 15 דקות."
          : status === 401 || status === 400 || status === 422
            ? totp ? "שם משתמש, סיסמה או קוד שגויים." : "שם משתמש או סיסמה שגויים."
            : "שגיאת תקשורת. נסו שוב.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-6 px-4">
      <div className="flex flex-col items-center gap-3">
        <Logo size={72} />
        <h1 className="font-display text-4xl font-extrabold">FreeRise</h1>
        <p className="text-muted">כניסה לחשבון</p>
      </div>
      <form onSubmit={onSubmit} className="card flex flex-col gap-3.5 rounded-3xl p-5">
        <label className="flex flex-col gap-1.5 text-[13px] text-muted">
          שם משתמש
          <input name="username" required autoComplete="username" className="input" dir="ltr" />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] text-muted">
          סיסמה
          <input name="password" type="password" required autoComplete="current-password" className="input" dir="ltr" />
        </label>
        {totp && (
        <label className="flex flex-col gap-1.5 text-[13px] text-muted">
          קוד אימות (6 ספרות)
          <input
            name="totp"
            required
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            autoComplete="one-time-code"
            className="input text-center tracking-[0.4em]"
            dir="ltr"
          />
        </label>
        )}
        {error && <p className="text-sm text-danger" role="alert">{error}</p>}
        <button className="btn-accent mt-2" disabled={busy}>
          {busy ? "מתחבר…" : "כניסה"}
        </button>
      </form>
    </main>
  );
}
