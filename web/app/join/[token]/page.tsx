"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Logo } from "@/components/Logo";
import { ApiError, api, send } from "@/lib/api";

type Setup = { otpauth: string; qr: string };

const MIN = 8; // matches the API

/** Where an invite link lands: pick a login, then (when the server asks for codes) set up the authenticator. */
export default function JoinPage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-6 px-4 py-8">
      <Suspense fallback={null}>
        <Join />
      </Suspense>
    </main>
  );
}

function Join() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [invite, setInvite] = useState<{ invited_by: string } | "dead" | null>(null);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ invited_by: string }>(`/auth/invites/${token}`)
      .then(setInvite)
      .catch(() => setInvite("dead"));
  }, [token]);

  async function submit(e: React.FormEvent<HTMLFormElement>, run: (f: FormData) => Promise<string | void>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setError((await run(new FormData(e.currentTarget))) ?? "");
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(
        status === 409
          ? "שם המשתמש הזה כבר תפוס, נסו אחר."
          : status === 404
            ? "הקישור כבר לא פעיל. בקשו קישור חדש."
            : status === 422
              ? `שם משתמש בלי רווחים, וסיסמה של לפחות ${MIN} תווים.`
              : status === 400
                ? "הקוד לא נכון. הקלידו את הקוד שמוצג עכשיו באפליקציה."
                : "משהו השתבש, נסו שוב.",
      );
    } finally {
      setBusy(false);
    }
  }

  const join = async (f: FormData) => {
    if (f.get("password") !== f.get("confirm")) return "הסיסמאות לא זהות.";
    const name = String(f.get("name")).trim() || null; // empty: the app shows the username
    const s = await send<Setup>("POST", "/auth/join", { token, name, username: f.get("username"), password: f.get("password") });
    const { totp } = await api<{ totp: boolean }>("/auth/config");
    if (totp) setSetup(s);
    else router.replace("/home");
  };

  const check = async (f: FormData) => {
    await send("POST", "/auth/totp/check", { code: f.get("code") });
    router.replace("/home");
  };

  if (!invite) return null;
  if (invite === "dead")
    return (
      <Header title="הקישור לא פעיל">
        כל קישור הזמנה עובד פעם אחת ולשבוע אחד. בקשו ממי ששלח אותו קישור חדש.
      </Header>
    );

  if (setup) {
    const key = new URL(setup.otpauth).searchParams.get("secret") ?? "";
    return (
      <>
        <Header title="עוד צעד אחד">בכל כניסה נבקש קוד בן 6 ספרות מאפליקציית אימות, כמו Google Authenticator. מוסיפים את FreeRise לאפליקציה פעם אחת:</Header>
        <div className="card flex flex-col items-center gap-4 rounded-3xl p-5 text-center">
          <a href={setup.otpauth} className="btn w-full min-h-12">
            הוספה לאפליקציית האימות
          </a>
          <p className="text-[13px] text-muted">במחשב? סורקים את הקוד עם הטלפון:</p>
          {/* eslint-disable-next-line @next/next/no-img-element -- a data URI, nothing to optimize */}
          <img src={setup.qr} alt="קוד QR להגדרת האימות" className="size-44 rounded-xl" />
          <p className="text-[13px] text-muted">
            או מקלידים את המפתח:{" "}
            <span dir="ltr" className="font-mono font-bold break-all text-text select-all">
              {key}
            </span>
          </p>
          <form onSubmit={(e) => submit(e, check)} className="flex w-full flex-col gap-3 border-t border-hairline pt-4">
            <label className="flex flex-col gap-1.5 text-[13px] text-muted">
              הקוד שמופיע עכשיו באפליקציה
              <input name="code" required inputMode="numeric" pattern="\d{6}" maxLength={6} autoComplete="one-time-code" className="input text-center tracking-[0.4em]" dir="ltr" />
            </label>
            {error && <p className="text-sm text-danger" role="alert">{error}</p>}
            <button className="btn-accent" disabled={busy}>
              {busy ? "בודק…" : "סיום"}
            </button>
          </form>
        </div>
      </>
    );
  }

  return (
    <>
      <Header title="הוזמנת ל-FreeRise">{invite.invited_by} רוצה לנהל איתך את הכסף של הבית. בוחרים שם משתמש וסיסמה, ונכנסים.</Header>
      <form onSubmit={(e) => submit(e, join)} className="card flex flex-col gap-3.5 rounded-3xl p-5">
        <label className="flex flex-col gap-1.5 text-[13px] text-muted">
          איך לקרוא לך?
          <input name="name" autoFocus maxLength={40} autoComplete="given-name" className="input" dir="auto" />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] text-muted">
          שם משתמש לכניסה
          <input name="username" required maxLength={50} pattern="\S+" autoCapitalize="none" autoComplete="username" className="input" dir="ltr" />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] text-muted">
          סיסמה (לפחות {MIN} תווים)
          <input name="password" type="password" required minLength={MIN} maxLength={200} autoComplete="new-password" className="input" dir="ltr" />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] text-muted">
          סיסמה שוב
          <input name="confirm" type="password" required autoComplete="new-password" className="input" dir="ltr" />
        </label>
        {error && <p className="text-sm text-danger" role="alert">{error}</p>}
        <button className="btn-accent mt-2" disabled={busy}>
          {busy ? "רגע…" : "הצטרפות"}
        </button>
      </form>
    </>
  );
}

function Header({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <Logo size={72} />
      <h1 className="font-display text-3xl font-extrabold">{title}</h1>
      <p className="text-muted">{children}</p>
    </div>
  );
}
