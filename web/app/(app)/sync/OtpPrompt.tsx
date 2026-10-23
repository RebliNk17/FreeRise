"use client";

import { useEffect, useState } from "react";
import { api, send, type OtpRequest } from "@/lib/api";
import { providerName } from "@/lib/providers";

// ponytail: polls always while logged in (paused when tab hidden); poll only during active runs if load matters.
export function OtpPrompt() {
  const [requests, setRequests] = useState<OtpRequest[]>([]);
  const [handled, setHandled] = useState<number[]>([]); // answered or dismissed; server may list them until next poll

  useEffect(() => {
    let alive = true;
    const poll = () => {
      if (document.hidden) return;
      api<OtpRequest[]>("/sync/otp")
        .then((r) => alive && setRequests(r))
        .catch(() => {});
    };
    poll();
    const t = setInterval(poll, 3000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const req = requests.find((r) => !handled.includes(r.id));
  if (!req) return null;
  return (
    <OtpDialog
      key={req.id}
      req={req}
      onDone={() => setHandled((h) => [...h, req.id])}
    />
  );
}

function OtpDialog({ req, onDone }: { req: OtpRequest; onDone: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await send("POST", `/sync/otp/${req.id}`, { code });
      onDone();
    } catch {
      setError("שליחת הקוד נכשלה. ייתכן שפג תוקפו.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-(--backdrop) p-4 sm:items-center" role="dialog" aria-modal="true" aria-labelledby={`otp-${req.id}`}
      onKeyDown={(e) => e.key === "Escape" && onDone()}
    >
      <form onSubmit={submit} className="card flex w-full max-w-sm flex-col gap-3 rounded-3xl p-5">
        <h2 id={`otp-${req.id}`} className="section-title">קוד אימות נדרש</h2>
        <p className="text-sm text-muted">
          {providerName(req.provider)} · {req.credential_label} שלחו קוד ב-SMS. הזינו אותו כדי להמשיך בסנכרון.
        </p>
        <input
          autoFocus
          required
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          inputMode="numeric"
          pattern="\d{6}"
          autoComplete="one-time-code"
          className="input text-center text-xl tracking-[0.5em]"
          dir="ltr"
          aria-label="קוד בן 6 ספרות"
        />
        {error && <p className="text-sm text-danger" role="alert">{error}</p>}
        <div className="flex gap-2">
          <button className="btn flex-1" disabled={busy || code.length !== 6}>שליחה</button>
          <button type="button" className="btn-ghost" onClick={onDone}>סגירה</button>
        </div>
      </form>
    </div>
  );
}
