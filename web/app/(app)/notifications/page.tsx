"use client";

import { useRouter } from "next/navigation";
import { Info, TriangleAlert } from "lucide-react";
import { Status, EmptyState } from "@/components/Card";
import { send, type Notification } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { NOTIFICATIONS_CHANGED } from "./NotificationBell";

const changed = () => window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));

export default function NotificationsPage() {
  const router = useRouter();
  const { data, setData, error } = useApi<Notification[]>("/notifications?limit=50");
  const now = new Date().toISOString();

  async function open(n: Notification) {
    if (!n.read_at) {
      setData((d) => d?.map((x) => (x.id === n.id ? { ...x, read_at: now } : x)));
      await send("POST", `/notifications/${n.id}/read`).catch(() => {});
      changed();
    }
    if (n.link) router.push(n.link);
  }

  async function readAll() {
    setData((d) => d?.map((x) => ({ ...x, read_at: x.read_at ?? now })));
    await send("POST", "/notifications/read-all").catch(() => {});
    changed();
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <h1 className="page-title flex-1">התראות</h1>
        <button className="btn-ghost" onClick={readAll} disabled={!data?.some((n) => !n.read_at)}>
          סימון הכל כנקרא
        </button>
      </div>
      <Status loading={!data} error={error} />
      {data?.length === 0 && <EmptyState text="אין התראות." />}
      <ul className="flex flex-col gap-2">
        {data?.map((n) => (
          <li key={n.id}>
            <button onClick={() => open(n)} className={`card flex w-full items-start gap-3 p-3.5 text-start ${n.read_at ? "opacity-60" : ""}`}>
              <span className={`flex size-[34px] shrink-0 items-center justify-center rounded-[11px] ${n.severity === "info" ? "bg-brand-soft text-brand" : n.severity === "critical" ? "bg-danger-soft text-danger" : "bg-sun-soft text-sun-strong"}`}>
                {n.severity === "info" ? <Info size={18} aria-hidden /> : <TriangleAlert size={18} aria-hidden />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className={`flex-1 ${n.read_at ? "" : "font-bold"}`}>{n.title}</span>
                  <span dir="ltr" className="shrink-0 text-xs text-faint">{formatDate(n.created_at)}</span>
                </div>
                {n.body && <p className="text-sm text-muted">{n.body}</p>}
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
