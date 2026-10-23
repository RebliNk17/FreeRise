"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { CalendarClock, ChartColumn, House, LogOut, Menu, PiggyBank, type LucideIcon } from "lucide-react";
import { ThemeButton } from "@/components/ThemeToggle";
import { Logo } from "@/components/Logo";
import { send } from "@/lib/api";
import { OtpPrompt } from "./sync/OtpPrompt";
import { NotificationBell } from "./notifications/NotificationBell";

// match: path prefixes that light the tab up (עוד owns every secondary screen).
const TABS: { href: string; label: string; icon: LucideIcon; match: string[] }[] = [
  { href: "/home", label: "בית", icon: House, match: ["/home"] },
  { href: "/cashflow", label: "תזרים", icon: ChartColumn, match: ["/cashflow"] },
  { href: "/forecast", label: "תחזית", icon: CalendarClock, match: ["/forecast"] },
  { href: "/pension", label: "פנסיה", icon: PiggyBank, match: ["/pension"] },
  { href: "/more", label: "עוד", icon: Menu, match: ["/more", "/transactions", "/accounts", "/settings", "/notifications", "/plans", "/cost", "/whatif", "/progress", "/reconcile", "/review"] },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  async function logout() {
    await send("POST", "/auth/logout").catch(() => {});
    router.replace("/login");
  }

  // usePathname/useParams suspend on dynamic routes under cacheComponents, hence the Suspense boundaries.
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-20 bg-bg/90 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-1.5 px-4 pt-4 pb-2 md:px-5">
          <Link href="/home" className="flex items-center gap-2.5 font-display text-[21px] font-extrabold">
            <Logo size={36} />
            FreeRise
          </Link>
          <nav aria-label="ניווט ראשי" className="ms-6 hidden gap-1 md:flex">
            <Suspense fallback={<TopTabs pathname="" />}>
              <ActiveTabs Tabs={TopTabs} />
            </Suspense>
          </nav>
          <NotificationBell className="ms-auto" />
          <ThemeButton />
          <button onClick={logout} className="icon-btn" aria-label="התנתקות" title="התנתקות">
            <LogOut size={19} strokeWidth={1.8} />
          </button>
        </div>
      </header>

      {/* Bottom padding clears the floating nav (64px + 16px gap + safe area). */}
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 pt-2 pb-[calc(6.5rem+env(safe-area-inset-bottom))] md:pb-10">
        <Suspense fallback={<p className="text-muted">טוען…</p>}>{children}</Suspense>
      </main>

      <nav aria-label="ניווט תחתון" className="fixed inset-x-4 bottom-[max(1rem,env(safe-area-inset-bottom))] z-20 mx-auto h-16 max-w-md rounded-[22px] bg-nav shadow-nav md:hidden">
        <ul className="flex h-full items-center justify-around px-2">
          <Suspense fallback={<BottomTabs pathname="" />}>
            <ActiveTabs Tabs={BottomTabs} />
          </Suspense>
        </ul>
      </nav>

      <OtpPrompt />
    </div>
  );
}

const isActive = (match: string[], pathname: string) => match.some((m) => pathname.startsWith(m));

function ActiveTabs({ Tabs }: { Tabs: (p: { pathname: string }) => React.ReactNode }) {
  return <Tabs pathname={usePathname()} />;
}

function TopTabs({ pathname }: { pathname: string }) {
  return TABS.map((t) => (
    <Link
      key={t.href}
      href={t.href}
      className={`rounded-xl px-3 py-2 text-sm font-semibold ${isActive(t.match, pathname) ? "bg-sun text-on-sun" : "text-muted hover:bg-sunken hover:text-text"}`}
    >
      {t.label}
    </Link>
  ));
}

function BottomTabs({ pathname }: { pathname: string }) {
  return TABS.map(({ href, label, icon: Icon, match }) => {
    const active = isActive(match, pathname);
    return (
      <li key={href}>
        <Link
          href={href}
          title={label}
          className={`flex size-[46px] items-center justify-center rounded-[15px] transition-colors ${active ? "bg-sun text-on-sun" : "text-nav-icon hover:text-white"}`}
          aria-current={active ? "page" : undefined}
        >
          <Icon size={22} strokeWidth={2} aria-hidden />
          <span className="sr-only">{label}</span>
        </Link>
      </li>
    );
  });
}
