"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, Info, TriangleAlert } from "lucide-react";
import { EmptyState, Status } from "@/components/Card";
import { Sheet, SheetTitle } from "@/components/Sheet";
import { api, send, type Notification } from "@/lib/api";
import { formatDate, formatTime } from "@/lib/format";
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

const SHEET_LIMIT = 10;

function NotificationsSheet({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const n = useNotifications(SHEET_LIMIT, onClose);
  return (
    <Sheet
      labelledBy="notifications-title"
      onClose={onClose}
      header={<SheetTitle id="notifications-title" title="התראות" action={<ReadAllButton {...n} />} onClose={onClose} />}
    >
      <NotificationList {...n} />
      {n.data?.length === SHEET_LIMIT && (
        <button
          type="button"
          className="btn-ghost mt-2 w-full"
          onClick={() => {
            onClose();
            router.push("/notifications");
          }}
        >
          הצגת כל ההתראות
        </button>
      )}
    </Sheet>
  );
}

/** The latest `limit` notifications; opening one marks it read and follows its link. */
export function useNotifications(limit: number, onNavigate?: () => void) {
  const router = useRouter();
  const { data, setData, error } = useApi<Notification[]>(`/notifications?limit=${limit}`);
  const now = new Date().toISOString();

  async function open(n: Notification) {
    if (!n.read_at) {
      setData((d) => d?.map((x) => (x.id === n.id ? { ...x, read_at: now } : x)));
      await send("POST", `/notifications/${n.id}/read`).catch(() => {});
      changed();
    }
    if (n.link) {
      onNavigate?.();
      router.push(n.link);
    }
  }

  async function readAll() {
    setData((d) => d?.map((x) => ({ ...x, read_at: x.read_at ?? now })));
    await send("POST", "/notifications/read-all").catch(() => {});
    changed();
  }

  return { data, error, open, readAll };
}

type Notifications = ReturnType<typeof useNotifications>;

export function ReadAllButton({ data, readAll }: Notifications) {
  return (
    <button type="button" className="link min-h-11 shrink-0 px-1 disabled:opacity-40" onClick={readAll} disabled={!data?.some((n) => !n.read_at)}>
      סימון הכל כנקרא
    </button>
  );
}

/** "22:59" today, "24.10" this year, else "24.10.25". */
function when(iso: string) {
  const d = formatDate(iso);
  const today = formatDate(new Date().toISOString());
  return d === today ? formatTime(iso) : d.slice(6) === today.slice(6) ? d.slice(0, 5) : d;
}

/** One card, a row per notification: severity icon, title, time, a two-line body. */
export function NotificationList({ data, error, open }: Notifications) {
  return (
    <>
      <Status loading={!data && !error} error={error} />
      {data?.length === 0 && <EmptyState text="אין התראות." />}
      {!!data?.length && (
        <ul className="card divide-y divide-hairline overflow-hidden">
          {data.map((n) => (
            <li key={n.id}>
              <button type="button" onClick={() => open(n)} className={`flex w-full items-start gap-2.5 px-3 py-2.5 text-start hover:bg-sunken/60 ${n.read_at ? "opacity-60" : ""}`}>
                <span className={`mt-px flex size-7 shrink-0 items-center justify-center rounded-[9px] ${n.severity === "info" ? "bg-brand-soft text-brand" : n.severity === "critical" ? "bg-danger-soft text-danger" : "bg-sun-soft text-sun-strong"}`}>
                  {n.severity === "info" ? <Info size={15} aria-hidden /> : <TriangleAlert size={15} aria-hidden />}
                </span>
                <span className="block min-w-0 flex-1">
                  <span className="flex items-baseline gap-2">
                    <span className={`min-w-0 flex-1 truncate text-sm ${n.read_at ? "font-semibold" : "font-bold"}`}>{n.title}</span>
                    <time dateTime={n.created_at} title={`${formatDate(n.created_at)} ${formatTime(n.created_at)}`} dir="ltr" className="shrink-0 text-[11px] text-faint">
                      {when(n.created_at)}
                    </time>
                  </span>
                  {n.body && <span className="line-clamp-2 text-xs text-muted">{n.body}</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
