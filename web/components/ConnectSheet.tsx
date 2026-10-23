"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, CircleAlert, LoaderCircle } from "lucide-react";
import { ApiError, api, send, type Credential, type VerifyStatus } from "@/lib/api";
import { friendlyError, technicalDetails } from "@/lib/connectErrors";
import { providerName } from "@/lib/providers";
import { AccountBriefs } from "@/components/InactiveFilter";
import { ProviderLogo } from "@/components/ProviderLogo";

const STEPS = ["שולחים פרטים", "מתחברים לספק", "מאמתים"];
const STEP_OF: Record<VerifyStatus["stage"], number> = { sending: 0, connecting: 1, otp: 1, verifying: 2, success: 3, failed: -1 };
const POLL_MS = 1500;
/**
 * Blocking "connecting" sheet for a credential's verify run (modal <dialog>: the page behind is inert and
 * Escape does nothing). Polls the real backend stage; switches to a code input the moment one is asked.
 * onClose(true) after a verified connection's "המשך"; onClose(false) after "ביטול" (pending dropped).
 */
export function ConnectSheet({
  credentialId,
  provider,
  onClose,
  onFix,
}: {
  credentialId: number;
  provider: string;
  onClose: (verified: boolean) => void;
  onFix: (c: Credential) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [st, setSt] = useState<VerifyStatus | null>(null);
  const [poll, setPoll] = useState(0); // bump to restart polling after a retry
  const [busy, setBusy] = useState(false);
  const done = st?.stage === "success" || st?.stage === "failed";

  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    return () => d.close();
  }, []);

  useEffect(() => {
    let alive = true;
    let t: ReturnType<typeof setTimeout>;
    const tick = () =>
      api<VerifyStatus>(`/credentials/${credentialId}/verify`)
        .then((s) => {
          if (!alive) return;
          setSt(s);
          if (s.stage !== "success" && s.stage !== "failed") t = setTimeout(tick, POLL_MS);
        })
        .catch(() => alive && (t = setTimeout(tick, POLL_MS * 2)));
    tick();
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [credentialId, poll]);

  useEffect(() => {
    if (done) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault(); // leaving mid-check loses it
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [done]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  }
  const cancel = () => act(() => send("DELETE", `/credentials/${credentialId}/verify`).catch(() => {})).then(() => onClose(false));
  const retry = () =>
    act(() => send("POST", `/credentials/${credentialId}/verify`)).then(() => {
      setSt(null);
      setPoll((p) => p + 1);
    });

  const step = st ? STEP_OF[st.stage] : 0;
  const name = providerName(provider);

  return (
    <dialog
      ref={ref}
      aria-labelledby="connect-title"
      onCancel={(e) => e.preventDefault()}
      className="m-auto w-[min(26rem,calc(100%-2rem))] rounded-3xl border-0 bg-surface p-5 text-text shadow-card backdrop:bg-(--backdrop)"
    >
      <div className="flex items-center gap-3">
        <span className="size-12 shrink-0">
          <ProviderLogo provider={provider} />
        </span>
        <div className="min-w-0">
          <h2 id="connect-title" className="section-title">
            {st?.stage === "success" ? "החיבור אומת" : st?.stage === "failed" ? "החיבור לא הצליח" : `מתחברים ל${name}`}
          </h2>
          {st && <p className="truncate text-xs text-muted">{st.credential.label}</p>}
        </div>
      </div>

      {st?.stage === "otp" ? (
        <>
          <OtpForm credentialId={credentialId} name={name} onSent={() => setSt({ ...st, stage: "connecting" })} />
          <button type="button" className="btn-ghost mt-2 w-full text-muted" onClick={cancel} disabled={busy}>
            ביטול
          </button>
        </>
      ) : st?.stage === "success" ? (
        <Success st={st} onContinue={() => onClose(true)} />
      ) : st?.stage === "failed" ? (
        <Failed st={st} busy={busy} onRetry={retry} onFix={() => onFix({ ...st.credential, fields: { ...st.credential.fields, ...st.prefill } })} onCancel={cancel} />
      ) : (
        <>
          <ol className="mt-5 flex flex-col gap-3" aria-live="polite">
            {STEPS.map((label, i) => (
              <li key={label} className={`flex items-center gap-3 text-sm ${i > step ? "text-faint" : "font-bold"}`}>
                <span
                  className={`flex size-7 shrink-0 items-center justify-center rounded-full ${i < step ? "bg-positive-fill text-brand-fg" : i === step ? "bg-brand-soft text-brand" : "bg-sunken"}`}
                  aria-hidden
                >
                  {i < step ? <Check size={16} strokeWidth={3} /> : i === step ? <LoaderCircle size={16} className="motion-safe:animate-spin" /> : i + 1}
                </span>
                {label}
                {i === step && <span className="sr-only">(בתהליך)</span>}
              </li>
            ))}
          </ol>
          <p className="mt-4 text-xs text-muted">זה לוקח בדרך כלל פחות מדקה. אם {name} ישלחו קוד ב-SMS, נבקש אותו כאן.</p>
          <button type="button" className="btn-ghost mt-4 w-full text-muted" onClick={cancel} disabled={busy}>
            ביטול
          </button>
        </>
      )}
    </dialog>
  );
}

function OtpForm({ credentialId, name, onSent }: { credentialId: number; name: string; onSent: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await send("POST", `/credentials/${credentialId}/verify/otp`, { code });
      onSent();
    } catch (err) {
      const s = err instanceof ApiError ? err.status : 0;
      setError(s === 429 ? "יותר מדי ניסיונות. המתינו כמה דקות." : s === 409 ? "תוקף הקוד פג או שהוא כבר נשלח." : "שליחת הקוד נכשלה. נסו שוב.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-5 flex flex-col gap-3">
      <label htmlFor="connect-otp" className="text-sm">
        {name} שלחו קוד אימות ב-SMS. הזינו אותו כדי להמשיך.
      </label>
      <input
        id="connect-otp"
        autoFocus
        required
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        inputMode="numeric"
        pattern="\d{6}"
        maxLength={6}
        autoComplete="one-time-code"
        className="input text-center text-xl tracking-[0.5em]"
        dir="ltr"
        aria-describedby={error ? "connect-otp-error" : undefined}
      />
      {error && (
        <p id="connect-otp-error" className="text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <button className="btn-accent" disabled={busy || code.length !== 6}>
        אימות
      </button>
    </form>
  );
}

function Success({ st, onContinue }: { st: VerifyStatus; onContinue: () => void }) {
  return (
    <div className="mt-4 flex flex-col gap-3">
      <p className="flex items-center gap-2 text-sm font-bold text-positive" role="status">
        <Check size={18} strokeWidth={3} aria-hidden /> ההתחברות הצליחה
      </p>
      <AccountBriefs accounts={st.accounts} kinds />
      {!st.credential.last_success_at && <p className="text-xs text-muted">היסטוריית העסקאות ממשיכה להיטען ברקע.</p>}
      <button type="button" className="btn-accent" onClick={onContinue} autoFocus>
        המשך
      </button>
    </div>
  );
}

function Failed({ st, busy, onRetry, onFix, onCancel }: { st: VerifyStatus; busy: boolean; onRetry: () => void; onFix: () => void; onCancel: () => void }) {
  const f = friendlyError(st.failure_kind, st.error);
  const details = technicalDetails(st.error);
  const canRetry = ["otp", "otp_timeout", "timeout", "blocked", "general"].includes(f.key);
  return (
    <div className="mt-4 flex flex-col gap-3">
      <div className="flex gap-2 rounded-xl bg-danger-soft px-3 py-2.5 text-danger-strong" role="alert">
        <CircleAlert size={18} className="mt-0.5 shrink-0" aria-hidden />
        <div>
          <p className="text-sm font-bold">{f.title}</p>
          <p className="text-xs">{f.hint}</p>
        </div>
      </div>
      {details && <TechDetails text={details} />}
      {canRetry && (
        <button type="button" className="btn" onClick={onRetry} disabled={busy}>
          {f.key === "otp" || f.key === "otp_timeout" ? "שליחת קוד חדש" : "ניסיון נוסף"}
        </button>
      )}
      <div className="grid grid-cols-2 gap-2">
        <button type="button" className={canRetry ? "btn-secondary" : "btn"} onClick={onFix} disabled={busy} autoFocus={!canRetry}>
          תיקון פרטים
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
          ביטול
        </button>
      </div>
    </div>
  );
}

export function TechDetails({ text }: { text: string }) {
  return (
    <details className="group text-xs text-muted">
      <summary className="flex cursor-pointer list-none items-center gap-1 select-none">
        <ChevronDown size={14} className="transition-transform group-open:rotate-180" aria-hidden />
        פרטים טכניים
      </summary>
      <p dir="ltr" className="mt-1.5 rounded-lg bg-bg px-2.5 py-2 text-start font-mono break-words">
        {text}
      </p>
    </details>
  );
}
