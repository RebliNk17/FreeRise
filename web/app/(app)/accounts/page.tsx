"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Check, Eye, EyeOff, Lock, Pause, Pencil, Play, Plus, RefreshCw, Trash2, TriangleAlert } from "lucide-react";
import { api, send,type Account, type Credential, type Provider, type Uncategorized } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { SERVICE_LABELS, fieldLabel, filledFields, isSecretField, methodLabel, providerKeywords, providerName, storedMethod } from "@/lib/providers";
import { friendlyError, saveError, technicalDetails } from "@/lib/connectErrors";
import { useApi } from "@/lib/useApi";
import { Amount } from "@/components/Amount";
import { useInactive } from "@/components/InactiveFilter";
import { ProviderLogo } from "@/components/ProviderLogo";
import { ConnectSheet, TechDetails } from "@/components/ConnectSheet";
import { Menu } from "@/components/home/parts";
import { CategorizeSheet } from "@/components/home/CategorizeSheet";
import { announceSync, type RunRef } from "../sync/SyncToasts";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/Card";
import { DataHealth, ym, type Health } from "./DataHealth";

/** Status pill: syncing / error / disabled / synced / never synced. */
function StatusPill({ c }: { c: Credential }) {
  const s = c.syncing
    ? { tone: "bg-sunken text-muted", icon: <RefreshCw size={13} className="animate-spin motion-reduce:animate-none" aria-hidden />, text: "מסנכרן…" }
    : c.last_error
      ? { tone: "bg-danger-soft text-danger-strong", icon: <TriangleAlert size={13} aria-hidden />, text: "שגיאה" }
      : !c.enabled
        ? { tone: "bg-sunken text-muted", icon: <Pause size={13} aria-hidden />, text: "מושבת" }
        : c.last_success_at
          ? { tone: "bg-brand-soft text-brand", icon: <Check size={13} strokeWidth={2.6} aria-hidden />, text: "מסונכרן" }
          : { tone: "bg-sun-soft text-text", icon: <span className="size-[7px] rounded-full bg-sun" aria-hidden />, text: "טרם סונכרן" };
  return (
    <span className={`chip shrink-0 ${s.tone}`}>
      {s.icon}
      {s.text}
    </span>
  );
}

const time = (iso: string) => new Date(iso).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });

/** The page's sections, by the provider's service. Anything else (the demo bank) goes with the banks. */
const GROUPS = [
  { service: "banks", title: "בנקים" },
  { service: "credit_cards", title: "כרטיסי אשראי" },
  { service: "insurances", title: "פנסיה וקרנות השתלמות" },
];

export default function AccountsPage() {
  return (
    <Suspense>
      <Accounts />
    </Suspense>
  );
}

/** One card per connection (login): status, its accounts, a ⋮ menu for the actions. Data health below. */
function Accounts() {
  const [creds, setCreds] = useState<Credential[] | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [providers, setProviders] = useState<Provider[] | null>(null); // null until loaded: it decides each card's section
  const params = useSearchParams();
  const router = useRouter();
  const [adding, setAdding] = useState(params.has("add")); // /accounts?add=1 opens the form
  const [unc, setUnc] = useState<Uncategorized[] | null>(null); // the categorize drawer's queue while it's open
  const [editing, setEditing] = useState<{ id: number; password?: boolean } | null>(null);
  const [deleting, setDeleting] = useState<Credential | null>(null);
  const [msg, setMsg] = useState("");
  const [connecting, setConnecting] = useState<{ id: number; provider: string } | null>(null);
  const [fixing, setFixing] = useState<Credential | null>(null); // a new connection that failed its check

  const reload = () =>
    Promise.all([api<Credential[]>("/credentials"), api<Account[]>("/accounts")])
      .then(([c, a]) => {
        setCreds(c);
        setAccounts(a);
      })
      .catch(() => setMsg("טעינת החשבונות נכשלה."));

  useEffect(() => {
    reload();
    api<Provider[]>("/providers")
      .then(setProviders)
      .catch(() => setProviders([]));
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
      const { runs } = await send<{ runs: RunRef[] }>("POST", "/sync", credential_id ? { credential_id } : {});
      reload();
      announceSync(runs, creds ?? []); // bottom toast now, and again when each one finishes
    } catch {
      setMsg("בקשת הסנכרון נכשלה.");
    }
  }

  /** The eye: in or out of the cashflow, optimistic. */
  async function exclude(a: Account) {
    const set = (excluded: boolean) => setAccounts((as) => as.map((x) => (x.id === a.id ? { ...x, excluded } : x)));
    set(!a.excluded);
    try {
      await send("PATCH", `/accounts/${a.id}`, { excluded: !a.excluded });
    } catch {
      set(a.excluded);
      setMsg("העדכון נכשל.");
    }
  }

  // While a connection syncs, its status says so; refresh until it's done.
  const syncing = creds?.some((c) => c.syncing);
  useEffect(() => {
    if (!syncing) return;
    const t = setInterval(reload, 4000);
    return () => clearInterval(t);
  }, [syncing]);
  const { data: health, reload: reloadHealth } = useApi<Health>("/data-health", !!syncing); // refetched when a sync ends

  const categorize = () =>
    api<Uncategorized[]>("/categories/uncategorized")
      .then(setUnc)
      .catch(() => setMsg("טעינת העסקאות לסיווג נכשלה."));

  // /accounts?edit=<id> (a failed-sync alert) opens that connection's edit sheet, its error on top.
  const editParam = Number(params.get("edit")) || 0; // NaN would never equal seenEdit: endless re-render
  const [seenEdit, setSeenEdit] = useState(0);
  if (creds && editParam !== seenEdit) {
    setSeenEdit(editParam);
    const c = creds.find((x) => x.id === editParam);
    if (c) setEditing({ id: c.id, password: friendlyError(c.last_failure_kind, c.last_error).key === "password" });
  }
  const closeEdit = () => {
    setEditing(null);
    if (editParam) router.replace("/accounts", { scroll: false }); // so the same alert opens it again
  };

  const last = creds?.map((c) => c.last_success_at).filter((x): x is string => !!x).sort().at(-1);
  const edited = creds?.find((c) => c.id === editing?.id);
  const serviceOf = (c: Credential) => {
    const s = providers?.find((p) => p.key === c.provider)?.service;
    return GROUPS.some((g) => g.service === s) ? s : "banks";
  };

  const card = (c: Credential) => {
    const gaps = health?.connections.find((h) => h.id === c.id)?.months_without_data ?? [];
    return (
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
          <Menu
            label={`פעולות: ${c.label}`}
            items={[
              ...(c.enabled && !c.syncing ? [{ label: "סנכרון", icon: <RefreshCw size={16} />, onSelect: () => sync(c.id) }] : []),
              { label: "עדכון פרטים", icon: <Pencil size={16} />, onSelect: () => setEditing({ id: c.id }) },
              c.enabled
                ? { label: "השבתה", icon: <Pause size={16} />, onSelect: () => setEnabled(c, false) }
                : { label: "הפעלה", icon: <Play size={16} />, onSelect: () => setEnabled(c, true) },
              { label: "מחיקה", icon: <Trash2 size={16} />, danger: true, onSelect: () => setDeleting(c) },
            ]}
          />
        </div>
        {c.last_error && (
          <div className="text-xs">
            <CardError c={c} onEditPassword={() => setEditing({ id: c.id, password: true })} />
          </div>
        )}
        {gaps.length > 0 && <p className="text-xs text-sun-strong">חודשים בלי נתונים: {gaps.map(ym).join(", ")}</p>}
        <AccountRows accounts={accounts.filter((a) => a.credential_id === c.id)} owner={c.owner} syncedAt={c.last_success_at} onExclude={exclude} />
      </li>
    );
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="page-title">חשבונות וחיבורים</h1>
          {last && (
            <p className="text-[13px] text-muted">
              סונכרן לאחרונה <span dir="ltr">{formatDate(last)} {time(last)}</span>
            </p>
          )}
        </div>
        <button className="btn shrink-0 px-3" onClick={() => sync()} disabled={!creds?.some((c) => c.enabled && !c.syncing)} aria-label="סנכרון הכל" data-tip="סנכרון הכל">
          <RefreshCw size={18} strokeWidth={2.2} aria-hidden />
        </button>
      </div>
      {msg && <p className="rounded-2xl bg-sunken px-4 py-2.5 text-sm" role="status">{msg}</p>}
      {(creds === null || providers === null) && <p className="text-muted">טוען…</p>}
      {creds?.length === 0 && <EmptyState text="עדיין לא נוספו חיבורים לבנקים ולאשראי." />}

      {creds &&
        providers &&
        GROUPS.map((g) => {
          const list = creds.filter((c) => serviceOf(c) === g.service);
          if (!list.length) return null;
          return (
            <section key={g.service} aria-labelledby={`group-${g.service}`} className="flex flex-col gap-2">
              <h2 id={`group-${g.service}`} className="section-title px-1 pt-1">
                {g.title}
              </h2>
              <ul className="flex flex-col gap-2.5">{list.map(card)}</ul>
            </section>
          );
        })}

      {edited && (
        <EditCredential
          key={edited.id}
          credential={edited}
          provider={providers?.find((p) => p.key === edited.provider)}
          toPassword={editing?.password}
          onDone={() => {
            closeEdit();
            reload();
          }}
          onVerify={(id) => {
            closeEdit();
            setConnecting({ id, provider: edited.provider });
          }}
        />
      )}

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
            if (creds?.some((x) => x.id === c.id)) setEditing({ id: c.id }); // updating a live connection
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
          providers={providers ?? []}
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
      {!!creds?.length && health && (
        <div id="health" className="scroll-mt-20">
          <DataHealth data={health} onAdd={() => setAdding(true)} onCategorize={categorize} />
        </div>
      )}
      {unc && (
        <CategorizeSheet
          list={unc}
          multi={new Set(accounts.map((a) => a.holder)).size > 1}
          onClose={(changed) => {
            setUnc(null);
            if (changed) reloadHealth();
          }}
        />
      )}
    </div>
  );
}

/** One line per account: name (· whose, when not the login's owner), balance, and the eye that takes it out of the cashflow. */
function AccountRows({ accounts, owner, syncedAt, onExclude }: { accounts: Account[]; owner: string; syncedAt: string | null; onExclude: (a: Account) => void }) {
  const { shown, toggle } = useInactive(accounts);
  if (!accounts.length) return null;
  return (
    <div className="flex flex-col gap-1.5">
      {shown!.length > 0 && (
        <ul className="flex flex-col divide-y divide-hairline rounded-xl bg-bg px-3 text-sm">
          {shown!.map((a) => {
            // "נכון ל-" only when the balance is from another day than the last sync
            const asOf = a.balance_as_of && (!syncedAt || formatDate(a.balance_as_of) !== formatDate(syncedAt)) ? a.balance_as_of : null;
            return (
              <li key={a.id} className="flex min-h-10 items-center gap-2 py-1">
                <span className={`min-w-0 flex-1 truncate ${a.excluded ? "opacity-45" : a.active ? "" : "text-muted"}`}>
                  <span className="font-semibold">{a.label}</span>
                  {a.holder !== owner && <span className="text-muted"> · {a.holder}</span>}
                </span>
                <span className={`shrink-0 text-end leading-tight ${a.excluded ? "line-through opacity-45" : ""}`}>
                  {a.balance != null ? <Amount value={a.balance} className="font-bold" /> : <span className="text-muted">—</span>}
                  {asOf && (
                    <span className="block text-xs text-muted">
                      {/* a card's balance is its next charge, dated the charge day */}
                      {new Date(asOf) > new Date() ? "לחיוב ב-" : "נכון ל-"}
                      <span dir="ltr">{formatDate(asOf)}</span>
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  className={`-me-1.5 flex size-8 shrink-0 items-center justify-center rounded-lg hover:bg-sunken ${a.excluded ? "text-danger" : "text-faint"}`}
                  aria-pressed={a.excluded}
                  aria-label={`החרגת ${a.label} מהתזרים`}
                  data-tip={a.excluded ? "מוחרג מהתזרים. לחצו להחזרה" : "החרגה מהתזרים"}
                  onClick={() => onExclude(a)}
                >
                  {a.excluded ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {toggle}
    </div>
  );
}

/** Friendly text for the card's last error; a wrong password links straight to the edit sheet. The raw text only behind "פרטים טכניים". */
function CardError({ c, onEditPassword }: { c: Credential; onEditPassword?: () => void }) {
  const f = friendlyError(c.last_failure_kind, c.last_error);
  const details = technicalDetails(c.last_error?.replace(/^הושבת אוטומטית — יש לעדכן סיסמה: /, ""));
  return (
    <div className="flex flex-col gap-1">
      <span className="font-bold text-danger-strong">{f.title}</span>
      {f.key === "password" && onEditPassword ? (
        <button type="button" className="link self-start font-bold" onClick={onEditPassword}>
          עדכנו את הסיסמה
        </button>
      ) : (
        <span className="text-muted">
          {f.hint}
          {!c.enabled && " הסנכרון הושבת עד לעדכון הפרטים."}
        </span>
      )}
      {c.enabled && c.sync_paused && (
        <span className="font-bold text-text">
          הסנכרון האוטומטי הושהה אחרי כמה כישלונות התחברות ברצף, כדי שהחשבון לא יינעל. היכנסו לאתר הספק, ודאו שאפשר
          להתחבר ובחרו ״סנכרון״ בתפריט.
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

/** New connection, or `fix`: correcting a pending one whose check failed (secrets left empty keep their value).
 * No close on a backdrop click: a stray tap would throw away what was typed. */
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
  const methods = provider?.login_methods ?? [];
  const [picked, setMethod] = useState<number | null>(null); // null: the fixed login's method, else the first
  const method = picked ?? (fix ? storedMethod(methods, Object.keys(fix.fields)) : 0);
  const keys = provider ? formFields(provider, method) : [];
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
    const fields = filledFields(keys, f);
    const label = String(f.get("label") ?? "").trim() || providerName(key);
    const owner = String(f.get("owner") ?? "").trim() || label;
    setBusy(true);
    setError("");
    try {
      const body = { label, owner, fields };
      let c = fix
        ? await send<Credential>("PATCH", `/credentials/${fix.id}`, { ...body, method })
        : await send<Credential>("POST", "/credentials", { ...body, provider: key });
      if (!c.verify_run_id) c = await send<Credential>("POST", `/credentials/${c.id}/verify`); // nothing secret changed
      onStarted(c);
    } catch (err) {
      setError(saveError(err, "חסרים שדות חובה או שהערכים אינם תקינים."));
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
            onChange={(k) => {
              setKey(k);
              setMethod(null);
            }}
            options={providers.map((p) => ({
              value: p.key,
              label: providerName(p.key),
              keywords: providerKeywords(p.key),
              icon: <ProviderLogo provider={p.key} />,
              group: SERVICE_LABELS[p.service],
            }))}
          />
        )}
      </div>
      <MethodSwitch methods={methods} value={method} onChange={setMethod} provider={key} />
      {keys.map((k) => {
        const required = methods[method].includes(k);
        return (
          <label key={`${key}:${k}`} className="flex flex-col gap-1.5 text-[13px] text-muted">
            <span>
              {fieldLabel(k)}
              {!required && <span className="text-faint"> (רשות)</span>}
            </span>
            <input
              name={`field:${k}`}
              type={isSecretField(k) ? "password" : "text"}
              required={required && !(fix && k in fix.fields)}
              placeholder={isSecretField(k) ? (fix?.fields[k] ?? "") : ""}
              defaultValue={isSecretField(k) ? undefined : (fix?.fields[k] ?? undefined)}
              autoComplete="off"
              className="input"
              dir="ltr"
            />
          </label>
        );
      })}
      <label className="flex flex-col gap-1.5 text-[13px] text-muted">
        <span>
          כינוי<span className="text-faint"> (רשות)</span>
        </span>
        <input name="label" className="input" placeholder={providerName(key)} defaultValue={fix?.label} />
      </label>
      <label className="flex flex-col gap-1.5 text-[13px] text-muted">
        <span>
          שייך ל<span className="text-faint"> (רשות)</span>
        </span>
        <input name="owner" className="input" placeholder={owners[0] ?? "בעל החשבון"} defaultValue={fix?.owner} />
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

/** The chosen login method's fields, then the provider's optional ones. */
const formFields = (p: Provider, method: number) => [...new Set([...p.login_methods[method], ...p.optional_fields])];

/** Only for providers with more than one way in (Max: password, or ID + card digits and an SMS code). */
function MethodSwitch({ methods, value, onChange, provider }: { methods: string[][]; value: number; onChange: (i: number) => void; provider: string }) {
  if (methods.length < 2) return null;
  return (
    <div className="flex flex-col gap-1.5 text-[13px] text-muted">
      דרך התחברות
      <div role="radiogroup" aria-label="דרך התחברות" className="flex rounded-[14px] bg-sunken p-1">
        {methods.map((m, i) => (
          <button
            key={m.join()}
            type="button"
            role="radio"
            aria-checked={value === i}
            onClick={() => onChange(i)}
            className={`min-h-10 flex-1 rounded-[11px] px-2 py-1.5 text-sm font-semibold ${value === i ? "bg-surface text-text shadow-card" : "text-muted"}`}
          >
            {methodLabel(m)}
          </button>
        ))}
      </div>
      {!methods[value].some(isSecretField) && (
        <span className="text-xs">{providerName(provider)} ישלחו קוד ב-SMS ונבקש להזין אותו. ייתכן שיידרש קוד גם בסנכרונים הבאים.</span>
      )}
    </div>
  );
}

/** "עדכון פרטים" sheet. Like AddCredential, a backdrop click doesn't close it; `toPassword` focuses the password (from a wrong-password error). */
function EditCredential({
  credential,
  provider,
  toPassword = false,
  onDone,
  onVerify,
}: {
  credential: Credential;
  provider: Provider | undefined;
  toPassword?: boolean;
  onDone: () => void;
  onVerify: (credentialId: number) => void;
}) {
  const methods = provider?.login_methods ?? [];
  const stored = Object.keys(credential.fields);
  const [picked, setMethod] = useState<number | null>(null);
  const method = picked ?? storedMethod(methods, stored);
  const keys = provider ? formFields(provider, method) : stored;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Non-secret fields (ID, card digits, username) in clear; passwords are never sent back.
  const [details, setDetails] = useState<Record<string, string> | null>(null);
  useEffect(() => {
    api<Record<string, string>>(`/credentials/${credential.id}/details`)
      .then(setDetails)
      .catch(() => setDetails({}));
  }, [credential.id]);
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    return () => d.close();
  }, []);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const filled = filledFields(keys, form);
    const fields = Object.fromEntries(Object.entries(filled).filter(([k, v]) => details?.[k] !== v));
    const label = String(form.get("label") ?? "").trim();
    const owner = String(form.get("owner") ?? "").trim();
    const patch: Record<string, unknown> = {};
    if (Object.keys(fields).length || method !== storedMethod(methods, stored)) {
      patch.fields = fields;
      // `method` drops the other methods' stored fields (a stored password would win over an SMS login)
      if (provider) patch.method = method;
    }
    if (label && label !== credential.label) patch.label = label;
    if (owner && owner !== credential.owner) patch.owner = owner;
    if (!Object.keys(patch).length) return onDone();
    setBusy(true);
    setError("");
    try {
      // Staged until verified; success also re-enables a connection auto-disabled after a login failure.
      const c = await send<Credential>("PATCH", `/credentials/${credential.id}`, patch);
      if (c.verify_run_id) onVerify(c.id);
      else onDone();
    } catch (err) {
      setError(saveError(err, "הערכים אינם תקינים."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="edit-cred-title"
      onCancel={(e) => {
        e.preventDefault();
        onDone();
      }}
      className="sheet"
    >
      <form onSubmit={submit} className="flex flex-col gap-3">
        <h2 id="edit-cred-title" className="section-title flex items-center gap-2">
          <span className="size-7 shrink-0">
            <ProviderLogo provider={credential.provider} />
          </span>
          <span className="min-w-0 truncate">עדכון פרטים · {credential.label}</span>
        </h2>
        {credential.last_error && (
          <div className="rounded-2xl bg-danger-soft px-3 py-2.5 text-xs">
            <CardError c={credential} />
          </div>
        )}
        {!details ? (
          <p className="text-sm text-muted">טוען…</p>
        ) : (
          <>
            <p className="text-xs text-muted">סיסמה ריקה נשארת ללא שינוי. הפרטים הקיימים נשארים בשימוש עד שהחדשים יאומתו.</p>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1.5 text-[13px] text-muted">
                כינוי
                <input name="label" className="input" defaultValue={credential.label} autoComplete="off" />
              </label>
              <label className="flex flex-col gap-1.5 text-[13px] text-muted">
                שייך ל
                <input name="owner" className="input" defaultValue={credential.owner} autoComplete="off" />
              </label>
            </div>
            <MethodSwitch methods={methods} value={method} onChange={setMethod} provider={credential.provider} />
            {keys.map((k) => (
              <label key={k} className="flex flex-col gap-1.5 text-[13px] text-muted">
                {fieldLabel(k)}
                <input
                  name={`field:${k}`}
                  type={isSecretField(k) ? "password" : "text"}
                  required={methods[method]?.includes(k) && !stored.includes(k)}
                  defaultValue={isSecretField(k) ? "" : (details[k] ?? "")}
                  placeholder={isSecretField(k) ? "••••" : ""}
                  autoFocus={toPassword && k === keys.find(isSecretField)}
                  autoComplete="off"
                  className="input"
                  dir="ltr"
                />
              </label>
            ))}
            {error && <p className="text-sm text-danger" role="alert">{error}</p>}
          </>
        )}
        <div className="flex gap-2">
          <button className="btn flex-1" disabled={busy || !details}>
            שמירה
          </button>
          <button type="button" className="btn-ghost" onClick={onDone}>
            ביטול
          </button>
        </div>
      </form>
    </dialog>
  );
}
