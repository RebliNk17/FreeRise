"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Lock, Plus, RefreshCw } from "lucide-react";
import { ApiError, api, send, type Credential, type Provider } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { SERVICE_LABELS, fieldLabel, filledFields, isSecretField, providerName } from "@/lib/providers";
import { friendlyError, technicalDetails } from "@/lib/connectErrors";
import { AccountBriefs } from "@/components/InactiveFilter";
import { ProviderLogo } from "@/components/ProviderLogo";
import { ConnectSheet, TechDetails } from "@/components/ConnectSheet";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/Card";

/** Status pill: error (coral) / disabled (grey) / never synced (sun) / up to date (green). */
function StatusPill({ c }: { c: Credential }) {
  const [tone, dot, text] = c.last_error
    ? ["bg-danger-soft text-danger-strong", "bg-danger", friendlyError(c.last_failure_kind, c.last_error).short]
    : !c.enabled
      ? ["bg-sunken text-muted", "bg-faint", "מושבת"]
      : c.last_success_at
        ? ["bg-brand-soft text-brand", "bg-positive-fill", "מעודכן"]
        : ["bg-sun-soft text-text", "bg-sun", "טרם סונכרן"];
  return (
    <span className={`chip shrink-0 ${tone}`}>
      <span className={`size-[7px] rounded-full ${dot}`} aria-hidden />
      {text}
    </span>
  );
}

const time = (iso: string) => new Date(iso).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });

export default function CredentialsPage() {
  return (
    <Suspense>
      <Credentials />
    </Suspense>
  );
}

function Credentials() {
  const [creds, setCreds] = useState<Credential[] | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [adding, setAdding] = useState(useSearchParams().has("add")); // /settings/credentials?add=1 opens the form
  const [editing, setEditing] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<Credential | null>(null);
  const [msg, setMsg] = useState("");
  const [connecting, setConnecting] = useState<{ id: number; provider: string } | null>(null);
  const [fixing, setFixing] = useState<Credential | null>(null); // a new connection that failed its check

  const reload = () =>
    api<Credential[]>("/credentials")
      .then(setCreds)
      .catch(() => setMsg("טעינת פרטי ההתחברות נכשלה."));

  useEffect(() => {
    reload();
    api<Provider[]>("/providers").then(setProviders).catch(() => {});
  }, []);

  async function setEnabled(c: Credential, enabled: boolean) {
    try {
      await send("PATCH", `/credentials/${c.id}`, { enabled });
      reload();
    } catch {
      setMsg("העדכון נכשל.");
    }
  }

  async function remove(c: Credential) {
    setDeleting(null);
    try {
      await send("DELETE", `/credentials/${c.id}`);
      setMsg(`החיבור "${c.label}" נמחק.`);
      reload();
    } catch {
      setMsg("המחיקה נכשלה.");
    }
  }

  async function sync(credential_id?: number) {
    try {
      const { run_ids } = await send<{ run_ids: number[] }>("POST", "/sync", credential_id ? { credential_id } : {});
      reload();
      setMsg(run_ids.length ? "הסנכרון התבקש. אם יידרש קוד SMS, תופיע בקשה." : "אין חיבורים פעילים לסנכרון.");
    } catch {
      setMsg("בקשת הסנכרון נכשלה.");
    }
  }

  const last = creds?.map((c) => c.last_success_at).filter((x): x is string => !!x).sort().at(-1);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="page-title">חיבורים</h1>
          {last && (
            <p className="text-[13px] text-muted">
              סונכרן לאחרונה <span dir="ltr">{formatDate(last)} {time(last)}</span>
            </p>
          )}
        </div>
        <button className="btn shrink-0" onClick={() => sync()} disabled={!creds?.length}>
          <RefreshCw size={16} strokeWidth={2.2} /> סנכרון הכל
        </button>
      </div>
      {msg && <p className="rounded-2xl bg-sunken px-4 py-2.5 text-sm" role="status">{msg}</p>}
      {creds === null && <p className="text-muted">טוען…</p>}
      {creds?.length === 0 && <EmptyState text="עדיין לא נוספו פרטי התחברות." />}

      <ul className="flex flex-col gap-2.5">
        {creds?.map((c) => (
          <li key={c.id} className="card flex flex-col gap-2 p-3">
            <div className="flex items-center gap-2.5">
              <span className="size-9 shrink-0">
                <ProviderLogo provider={c.provider} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[15px] font-bold leading-tight">{c.label}</div>
                <div className="truncate text-xs text-muted">
                  {[c.owner, providerName(c.provider)].filter(Boolean).join(" · ")}
                  {c.enabled && !c.last_error && c.last_success_at && (
                    <>
                      {" · "}
                      <span dir="ltr">{formatDate(c.last_success_at)} {time(c.last_success_at)}</span>
                    </>
                  )}
                </div>
              </div>
              <StatusPill c={c} />
            </div>
            <AccountBriefs accounts={c.accounts} />
            {c.last_error && (
              <div className="text-xs">
                <CardError c={c} />
              </div>
            )}
            {/* ponytail: masked fields list dropped — the edit form shows them as placeholders */}
            <div className="-mx-1 flex items-center gap-0.5 border-t border-hairline pt-1.5 text-[13px] font-bold">
              <button className="card-action text-brand" onClick={() => sync(c.id)} disabled={!c.enabled}>
                <RefreshCw size={14} /> סנכרון
              </button>
              <button className="card-action" onClick={() => setEditing(editing === c.id ? null : c.id)}>
                עדכון פרטים
              </button>
              <button className="card-action text-muted" onClick={() => setEnabled(c, !c.enabled)}>
                {c.enabled ? "השבתה" : "הפעלה"}
              </button>
              <button className="card-action ms-auto text-danger" onClick={() => setDeleting(c)}>
                מחיקה
              </button>
            </div>
            {editing === c.id && (
              <EditCredential
                credential={c}
                provider={providers.find((p) => p.key === c.provider)}
                onDone={() => setEditing(null)}
                onVerify={(id) => {
                  setEditing(null);
                  setConnecting({ id, provider: c.provider });
                }}
              />
            )}
          </li>
        ))}
      </ul>

      {deleting && (
        <ConfirmDelete
          credential={deleting}
          onCancel={() => setDeleting(null)}
          onDisable={() => {
            setDeleting(null);
            setEnabled(deleting, false);
          }}
          onDelete={() => remove(deleting)}
        />
      )}

      {connecting && (
        <ConnectSheet
          credentialId={connecting.id}
          provider={connecting.provider}
          onClose={(verified) => {
            setConnecting(null);
            setFixing(null);
            if (verified) setMsg("החיבור אומת ונשמר.");
            reload();
          }}
          onFix={(c) => {
            setConnecting(null);
            if (creds?.some((x) => x.id === c.id)) setEditing(c.id); // updating a live connection
            else {
              setFixing(c);
              setAdding(true);
            }
          }}
        />
      )}

      {adding && (
        <AddCredential
          key={fixing?.id ?? "new"}
          providers={providers}
          owners={creds?.map((c) => c.owner) ?? []}
          fix={fixing}
          onCancel={() => {
            // a pending connection being fixed is dropped, never left behind hidden
            if (fixing) send("DELETE", `/credentials/${fixing.id}/verify`).catch(() => {});
            setFixing(null);
            setAdding(false);
          }}
          onStarted={(c) => {
            setAdding(false);
            setConnecting({ id: c.id, provider: c.provider });
          }}
        />
      )}
      <button className="flex min-h-14 items-center justify-center gap-1.5 rounded-[20px] border-2 border-dashed border-border font-bold text-brand hover:border-brand" onClick={() => setAdding(true)}>
          <Plus size={18} /> הוספת חיבור
        </button>
    </div>
  );
}

/** Friendly text for the card's last error; the raw text only behind "פרטים טכניים". */
function CardError({ c }: { c: Credential }) {
  const f = friendlyError(c.last_failure_kind, c.last_error);
  const details = technicalDetails(c.last_error?.replace(/^הושבת אוטומטית — יש לעדכן סיסמה: /, ""));
  return (
    <div className="flex flex-col gap-1">
      <span className="font-bold text-danger-strong">{f.title}</span>
      <span className="text-muted">
        {f.hint}
        {!c.enabled && " הסנכרון הושבת עד לעדכון הפרטים."}
      </span>
      {c.enabled && c.sync_paused && (
        <span className="font-bold text-text">
          הסנכרון האוטומטי הושהה אחרי כמה כישלונות התחברות ברצף, כדי שהחשבון לא יינעל. היכנסו לאתר הספק, ודאו שאפשר
          להתחבר ולחצו ״סנכרון״.
        </span>
      )}
      {details && <TechDetails text={details} />}
    </div>
  );
}

/** Native modal <dialog> (focus trap + Escape). Deleting cascades, so it steers toward disabling. */
function ConfirmDelete({ credential: c, onCancel, onDisable, onDelete }: { credential: Credential; onCancel: () => void; onDisable: () => void; onDelete: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    return () => d.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="delete-cred-title"
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      onClick={(e) => e.target === ref.current && onCancel()}
      className="m-auto w-[min(28rem,calc(100%-2rem))] rounded-3xl border-0 bg-surface p-5 text-text shadow-card backdrop:bg-(--backdrop)"
    >
      <h2 id="delete-cred-title" className="section-title">
        למחוק את החיבור &quot;{c.label}&quot;?
      </h2>
      <p className="mt-2 text-sm">
        המחיקה תמחק גם את כל החשבונות של ההתחברות הזו ואת היסטוריית העסקאות שלהם. אי אפשר לבטל את זה.
      </p>
      <p className="mt-2 text-sm text-muted">אם רק רוצים להפסיק לסנכרן, עדיף להשבית את החיבור. ההיסטוריה תישמר.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {c.enabled && (
          <button type="button" className="btn flex-1" onClick={onDisable} autoFocus>
            השבתה במקום
          </button>
        )}
        <button type="button" className="btn-ghost text-danger" onClick={onDelete}>
          מחיקה לצמיתות
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel} autoFocus={!c.enabled}>
          ביטול
        </button>
      </div>
    </dialog>
  );
}

/** New connection, or `fix`: correcting a pending one whose check failed (secrets left empty keep their value). */
function AddCredential({
  providers,
  owners,
  fix,
  onCancel,
  onStarted,
}: {
  providers: Provider[];
  owners: string[];
  fix: Credential | null;
  onCancel: () => void;
  onStarted: (c: Credential) => void;
}) {
  const [selected, setKey] = useState<string | undefined>(fix?.provider);
  const key = selected ?? providers[0]?.key ?? ""; // derived so a late /providers load still picks a default
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const provider = providers.find((p) => p.key === key);
  // ponytail: one household, so no "whose is it" question; reuse the existing owner (it still feeds account holders/pension).
  const owner = fix?.owner ?? owners[0] ?? "";
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    return () => d.close();
  }, []);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!provider) return;
    const f = new FormData(e.currentTarget);
    const fields = filledFields([...provider.required_fields, ...provider.optional_fields], f);
    setBusy(true);
    setError("");
    try {
      const body = { label: String(f.get("label") ?? "").trim() || providerName(key), owner, fields };
      let c = fix
        ? await send<Credential>("PATCH", `/credentials/${fix.id}`, body)
        : await send<Credential>("POST", "/credentials", { ...body, provider: key });
      if (!c.verify_run_id) c = await send<Credential>("POST", `/credentials/${c.id}/verify`); // nothing secret changed
      onStarted(c);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 422 ? "חסרים שדות חובה או שהערכים אינם תקינים." : "השמירה נכשלה.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="add-cred-title"
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      onClick={(e) => e.target === ref.current && onCancel()}
      className="sheet"
    >
    <form onSubmit={submit} className="flex flex-col gap-3">
      <h2 id="add-cred-title" className="section-title">{fix ? "תיקון פרטי החיבור" : "חיבור חדש"}</h2>
      {fix && <p className="text-xs text-muted">שדה ריק נשאר ללא שינוי. מטעמי אבטחה הסיסמה לא מוצגת.</p>}
      <div className="flex flex-col gap-1.5 text-[13px] text-muted">
        ספק
        {fix ? (
          <span className="flex items-center gap-2 text-[15px] text-text">
            <span className="size-6">
              <ProviderLogo provider={fix.provider} />
            </span>
            {providerName(fix.provider)}
          </span>
        ) : (
          <Select
            label="ספק"
            value={key}
            onChange={setKey}
            options={providers.map((p) => ({
              value: p.key,
              label: providerName(p.key),
              icon: <ProviderLogo provider={p.key} />,
              group: SERVICE_LABELS[p.service],
            }))}
          />
        )}
      </div>
      {provider &&
        [...provider.required_fields.map((k) => [k, true] as const), ...provider.optional_fields.map((k) => [k, false] as const)].map(
          ([k, required]) => (
            <label key={`${key}:${k}`} className="flex flex-col gap-1.5 text-[13px] text-muted">
              <span>
                {fieldLabel(k)}
                {!required && <span className="text-faint"> (רשות)</span>}
              </span>
              <input
                name={`field:${k}`}
                type={isSecretField(k) ? "password" : "text"}
                required={required && !fix}
                placeholder={isSecretField(k) ? (fix?.fields[k] ?? "") : ""}
                defaultValue={isSecretField(k) ? undefined : (fix?.fields[k] ?? undefined)}
                autoComplete="off"
                className="input"
                dir="ltr"
              />
            </label>
          ),
        )}
      <label className="flex flex-col gap-1.5 text-[13px] text-muted">
        <span>
          כינוי<span className="text-faint"> (רשות)</span>
        </span>
        <input name="label" className="input" placeholder={providerName(key)} defaultValue={fix?.label} />
      </label>
      {provider && (
        <p className="flex items-center gap-1.5 text-xs text-muted">
          <Lock size={14} className="shrink-0 text-positive-fill" aria-hidden />
          הפרטים נשמרים מוצפנים ונשלחים רק ל{providerName(provider.key)}
        </p>
      )}
      {error && <p className="text-sm text-danger" role="alert">{error}</p>}
      <div className="flex gap-2">
        <button className="btn-accent flex-1" disabled={busy || !provider}>
          חיבור
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </form>
    </dialog>
  );
}

function EditCredential({
  credential,
  provider,
  onDone,
  onVerify,
}: {
  credential: Credential;
  provider: Provider | undefined;
  onDone: () => void;
  onVerify: (credentialId: number) => void;
}) {
  const keys = provider ? [...provider.required_fields, ...provider.optional_fields] : Object.keys(credential.fields);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fields = filledFields(keys, new FormData(e.currentTarget));
    if (!Object.keys(fields).length) return onDone();
    setBusy(true);
    setError("");
    try {
      // Staged until verified; success also re-enables a connection auto-disabled after a login failure.
      const c = await send<Credential>("PATCH", `/credentials/${credential.id}`, { fields });
      if (c.verify_run_id) onVerify(c.id);
      else onDone();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 422 ? "הערכים אינם תקינים." : "השמירה נכשלה.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 border-t border-hairline pt-3">
      <p className="text-xs text-muted">שדה ריק נשאר ללא שינוי. הפרטים הקיימים נשארים בשימוש עד שהחדשים יאומתו.</p>
      {keys.map((k) => (
        <label key={k} className="flex flex-col gap-1.5 text-[13px] text-muted">
          {fieldLabel(k)}
          <input
            name={`field:${k}`}
            type={isSecretField(k) ? "password" : "text"}
            placeholder={credential.fields[k] ?? ""}
            autoComplete="off"
            className="input"
            dir="ltr"
          />
        </label>
      ))}
      {error && <p className="text-sm text-danger" role="alert">{error}</p>}
      <div className="flex gap-2">
        <button className="btn flex-1" disabled={busy}>
          שמירה
        </button>
        <button type="button" className="btn-ghost" onClick={onDone}>
          ביטול
        </button>
      </div>
    </form>
  );
}
