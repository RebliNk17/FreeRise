"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, Info, TriangleAlert } from "lucide-react";
import { EmptyState, Status } from "@/components/Card";
import { Sheet, SheetTitle } from "@/components/Sheet";
import { api, send, type Notification } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/** Fired after marking read, so the badge refreshes without waiting for the poll. */
export const NOTIFICATIONS_CHANGED = "freerise:notifications";
const changed = () => window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));

/** Header bell with the unread count; opens the notifications sheet (list, mark read, mark all read). */
export function NotificationBell({ className = "" }: { className?: string }) {
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const poll = () => {
      if (document.hidden) return;
      api<{ count: number }>("/notifications/unread-count")
        .then((r) => setCount(r.count))
        .catch(() => {});
    };
    poll();
    const t = setInterval(poll, 60_000);
    window.addEventListener(NOTIFICATIONS_CHANGED, poll);
    document.addEventListener("visibilitychange", poll); // poll() skips while hidden
    return () => {
      clearInterval(t);
      window.removeEventListener(NOTIFICATIONS_CHANGED, poll);
      document.removeEventListener("visibilitychange", poll);
    };
  }, []);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={`icon-btn ${className}`} aria-label={count ? `התראות, ${count} שלא נקראו` : "התראות"} title="התראות" aria-haspopup="dialog">
        <Bell size={19} strokeWidth={1.8} />
        {count > 0 && (
          <span dir="ltr" className="absolute -top-1 -left-1 min-w-[18px] rounded-full border-2 border-bg bg-danger px-1 text-center text-[10px] leading-[14px] font-bold text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>
      {open && <NotificationsSheet onClose={() => setOpen(false)} />}
    </>
  );
}

function NotificationsSheet({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { data, setData, error } = useApi<Notification[]>("/notifications?limit=50");
  const now = new Date().toISOString();

  async function openOne(n: Notification) {
    if (!n.read_at) {
      setData((d) => d?.map((x) => (x.id === n.id ? { ...x, read_at: now } : x)));
      await send("POST", `/notifications/${n.id}/read`).catch(() => {});
      changed();
    }
    if (n.link) {
      onClose();
      router.push(n.link);
    }
  }

  async function readAll() {
    setData((d) => d?.map((x) => ({ ...x, read_at: x.read_at ?? now })));
    await send("POST", "/notifications/read-all").catch(() => {});
    changed();
  }

  return (
    <Sheet
      labelledBy="notifications-title"
      onClose={onClose}
      header={
        <>
          <SheetTitle id="notifications-title" title="התראות" onClose={onClose} />
          <button type="button" className="btn-ghost self-start" onClick={readAll} disabled={!data?.some((n) => !n.read_at)}>
            סימון הכל כנקרא
          </button>
        </>
      }
    >
      <Status loading={!data} error={error} />
      {data?.length === 0 && <EmptyState text="אין התראות." />}
      <ul className="flex flex-col gap-2">
        {data?.map((n) => (
          <li key={n.id}>
            <button type="button" onClick={() => openOne(n)} className={`card flex min-h-14 w-full items-start gap-3 p-3.5 text-start ${n.read_at ? "opacity-60" : ""}`}>
              <span className={`flex size-[34px] shrink-0 items-center justify-center rounded-[11px] ${n.severity === "info" ? "bg-brand-soft text-brand" : n.severity === "critical" ? "bg-danger-soft text-danger" : "bg-sun-soft text-sun-strong"}`}>
                {n.severity === "info" ? <Info size={18} aria-hidden /> : <TriangleAlert size={18} aria-hidden />}
              </span>
              <span className="block min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <span className={`flex-1 ${n.read_at ? "" : "font-bold"}`}>{n.title}</span>
                  <span dir="ltr" className="shrink-0 text-xs text-faint">
                    {formatDate(n.created_at)}
                  </span>
                </span>
                {n.body && <span className="block text-sm text-muted">{n.body}</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}
