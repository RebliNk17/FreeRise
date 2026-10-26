"use client";

import Link from "next/link";
import { Bell, CalendarRange, ChevronLeft, CircleUserRound, GripVertical, Palette, RefreshCw, Send, Tags, Wallet, type LucideIcon } from "lucide-react";
import { useApi } from "@/lib/useApi";

/** RiseUp-style menu: one card of rows, each opening its own page. */
const ROWS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/settings/account", label: "החשבון שלי", icon: CircleUserRound },
  { href: "/settings/cycle", label: "החודש שלי", icon: CalendarRange },
  { href: "/settings/sync", label: "סנכרון אוטומטי", icon: RefreshCw },
  { href: "/settings/alerts", label: "התראות", icon: Bell },
  { href: "/settings/telegram", label: "טלגרם", icon: Send },
  { href: "/settings/display", label: "תצוגה", icon: Palette },
  { href: "/accounts", label: "חשבונות וחיבורים", icon: Wallet },
  { href: "/home?categorize=1", label: "סיווג עסקאות", icon: Tags },
  { href: "/settings/categories", label: "סדר הקטגוריות בבית", icon: GripVertical },
];

export default function SettingsPage() {
  const { data: health } = useApi<{ version: string }>("/health");
  return (
    <div className="flex flex-col gap-5">
      <h1 className="page-title">הגדרות</h1>
      <nav aria-label="הגדרות" className="card flex flex-col px-4 sm:px-5">
        {ROWS.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className="flex min-h-14 items-center gap-3 border-t border-hairline first:border-t-0">
            <Icon size={20} strokeWidth={1.8} className="text-brand" aria-hidden />
            <span className="flex-1">{label}</span>
            <ChevronLeft size={18} className="text-faint" aria-hidden />
          </Link>
        ))}
      </nav>
      {health && <p dir="ltr" className="text-center text-xs text-faint tabular-nums">FreeRise v{health.version}</p>}
    </div>
  );
}
