import Link from "next/link";
import { SunHorizon } from "./Logo";

export function Card({ title, action, className = "", children }: { title?: React.ReactNode; action?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <section className={`card flex flex-col gap-3 p-4 ${className}`}>
      {(title || action) && (
        <div className="flex min-h-7 items-center gap-2">
          <h2 className="section-title flex-1">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function ProgressBar({ percent, danger = false, label }: { percent: number; danger?: boolean; label?: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-sunken" role="progressbar" aria-valuenow={Math.round(percent)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className={`h-full rounded-full ${danger ? "bg-danger" : "bg-brand"}`} style={{ width: `${percent}%` }} />
    </div>
  );
}

/** Loading / error / empty states shared by all screens. Returns null when data is ready and non-empty. */
export function Status({ loading, error, empty }: { loading: boolean; error: boolean; empty?: boolean }) {
  if (error) return <p className="rounded-2xl bg-danger-soft px-4 py-3 text-sm font-semibold text-danger-strong" role="alert">הטעינה נכשלה.</p>;
  if (loading) return <p className="px-1 text-muted">טוען…</p>;
  if (empty)
    return (
      <EmptyState text="אין עדיין נתונים">
        <Link href="/settings/credentials" className="btn">
          סנכרון חשבונות
        </Link>
      </EmptyState>
    );
  return null;
}

/** Small sun-over-horizon illustration, one line, and an optional primary action. */
export function EmptyState({ text, children, className = "" }: { text: React.ReactNode; children?: React.ReactNode; className?: string }) {
  return (
    <div className={`card flex flex-col items-center gap-3 px-6 pt-6 pb-5 text-center ${className}`}>
      <SunHorizon width={96} ground="var(--surface)" />
      <p className="text-muted">{text}</p>
      {children}
    </div>
  );
}
