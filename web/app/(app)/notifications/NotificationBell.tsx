"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bell } from "lucide-react";
import { api } from "@/lib/api";

/** Fired by the notifications page after marking read, so the badge refreshes without waiting for the poll. */
export const NOTIFICATIONS_CHANGED = "freerise:notifications";

export function NotificationBell({ className = "" }: { className?: string }) {
  const [count, setCount] = useState(0);

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
    <Link href="/notifications" className={`icon-btn ${className}`} aria-label={count ? `התראות, ${count} שלא נקראו` : "התראות"} title="התראות">
      <Bell size={19} strokeWidth={1.8} />
      {count > 0 && (
        <span dir="ltr" className="absolute -top-1 -left-1 min-w-[18px] rounded-full border-2 border-bg bg-danger px-1 text-center text-[10px] leading-[14px] font-bold text-white">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}
