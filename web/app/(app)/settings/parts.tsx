import type { Settings } from "@/lib/api";

export type Patch = (p: Partial<Settings>) => Promise<boolean>;

export function Section({ id, title, hint, action, children }: { id: string; title: string; hint?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="card flex scroll-mt-24 flex-col gap-1 p-4 sm:p-5">
      <div className="mb-2 flex items-start gap-2">
        <div className="flex-1">
          <h2 id={`${id}-h`} className="section-title">{title}</h2>
          {hint && <p className="mt-0.5 text-sm text-muted">{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline py-3 first-of-type:border-t-0">
      <div className="min-w-48 flex-1">
        <p className="font-semibold">{label}</p>
        {hint && <p className="text-[13px] text-muted">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

