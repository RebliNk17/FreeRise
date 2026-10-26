"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ChartColumn,
  FlaskConical,
  House,
  LogOut,
  Menu,
  MessagesSquare,
  PiggyBank,
  Receipt,
  Search,
  Settings,
  Target,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import { ThemeButton } from "@/components/ThemeToggle";
import { Logo } from "@/components/Logo";
import { send } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { OtpPrompt } from "./sync/OtpPrompt";
import { SyncToasts } from "./sync/SyncToasts";
import { NotificationBell } from "@/components/NotificationBell";

type NavLink = { href: string; label: string; icon: LucideIcon };

const TABS: NavLink[] = [
  { href: "/home", label: "בית", icon: House },
  { href: "/progress", label: "המגמות שלי", icon: ChartColumn },
  { href: "/pension", label: "פנסיה", icon: PiggyBank },
];

const MORE: NavLink[] = [
  { href: "/plans", label: "יעדי חיסכון", icon: Target },
  { href: "/cost", label: "חיפוש הוצאות", icon: Receipt },
  { href: "/whatif", label: "תרחישים", icon: FlaskConical },
  { href: "/chat", label: "שאל אותי על התזרים", icon: MessagesSquare },
  { href: "/search", label: "חיפוש עסקאות", icon: Search },
  { href: "/accounts", label: "חשבונות וחיבורים", icon: Wallet },
  { href: "/settings", label: "הגדרות", icon: Settings },
];

// Secondary screens that light up the mobile עוד button (/review is reached from home, not the drawer).
const MORE_MATCH = [...MORE.map((l) => l.href), "/review"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [drawer, setDrawer] = useState(false);
  const { data: health } = useApi<{ version: string }>("/health");

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
            <span className="flex flex-col leading-none">
              FreeRise
              {health && <span dir="ltr" className="mt-1 font-sans text-[11px] font-semibold text-faint tabular-nums">v{health.version}</span>}
            </span>
          </Link>
          <Link href="/search" className="icon-btn ms-auto" aria-label="חיפוש עסקאות" title="חיפוש עסקאות">
            <Search size={19} strokeWidth={1.8} />
          </Link>
          <NotificationBell />
          <ThemeButton />
          <button onClick={() => setDrawer(true)} className="icon-btn" aria-label="תפריט" title="תפריט" aria-expanded={drawer}>
            <Menu size={19} strokeWidth={1.8} />
          </button>
        </div>
      </header>

      {/* Bottom padding clears the floating nav (64px + 16px gap + safe area). */}
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 pt-2 pb-[calc(6.5rem+env(safe-area-inset-bottom))] md:pb-10">
        <Suspense fallback={<p className="text-muted">טוען…</p>}>{children}</Suspense>
      </main>

      <nav aria-label="ניווט תחתון" className="fixed inset-x-4 bottom-[max(1rem,env(safe-area-inset-bottom))] z-20 mx-auto h-16 max-w-md rounded-[22px] bg-nav shadow-nav md:hidden">
        <ul className="flex h-full items-center justify-around px-2">
          <Suspense fallback={<BottomTabs pathname="" onMore={() => setDrawer(true)} />}>
            <ActiveBottomTabs onMore={() => setDrawer(true)} />
          </Suspense>
        </ul>
      </nav>

      {drawer && (
        <Suspense fallback={null}>
          <NavDrawer onClose={() => setDrawer(false)} onLogout={logout} />
        </Suspense>
      )}

      <OtpPrompt />
      <SyncToasts />
    </div>
  );
}

const isActive = (href: string, pathname: string) => pathname.startsWith(href);

function ActiveBottomTabs({ onMore }: { onMore: () => void }) {
  return <BottomTabs pathname={usePathname()} onMore={onMore} />;
}

function BottomTabs({ pathname, onMore }: { pathname: string; onMore: () => void }) {
  const tab = "flex size-[46px] items-center justify-center rounded-[15px] transition-colors";
  const moreActive = MORE_MATCH.some((m) => isActive(m, pathname));
  return (
    <>
      {TABS.map(({ href, label, icon: Icon }) => {
        const active = isActive(href, pathname);
        return (
          <li key={href}>
            <Link
              href={href}
              title={label}
              className={`${tab} ${active ? "bg-sun text-on-sun" : "text-nav-icon hover:text-white"}`}
              aria-current={active ? "page" : undefined}
            >
              <Icon size={22} strokeWidth={2} aria-hidden />
              <span className="sr-only">{label}</span>
            </Link>
          </li>
        );
      })}
      <li>
        <button onClick={onMore} title="עוד" className={`${tab} ${moreActive ? "bg-sun text-on-sun" : "text-nav-icon hover:text-white"}`}>
          <Menu size={22} strokeWidth={2} aria-hidden />
          <span className="sr-only">עוד</span>
        </button>
      </li>
    </>
  );
}

/** Side drawer (native modal <dialog>: focus trap + Escape); backdrop tap or a link click closes it. */
function NavDrawer({ onClose, onLogout }: { onClose: () => void; onLogout: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const pathname = usePathname();

  useEffect(() => {
    const d = ref.current!;
    const opener = document.activeElement as HTMLElement | null;
    d.showModal();
    return () => {
      d.close();
      opener?.focus();
    };
  }, []);

  const item = (l: NavLink) => {
    const active = isActive(l.href, pathname);
    return (
      <li key={l.href}>
        <Link
          href={l.href}
          onClick={onClose}
          aria-current={active ? "page" : undefined}
          className={`flex min-h-12 items-center gap-3 rounded-xl px-3 py-2 text-[15px] font-semibold ${active ? "bg-sun text-on-sun" : "hover:bg-sunken"}`}
        >
          <span className={`flex size-[32px] shrink-0 items-center justify-center rounded-[10px] ${active ? "" : "bg-brand-soft text-brand"}`}>
            <l.icon size={18} aria-hidden />
          </span>
          {l.label}
        </Link>
      </li>
    );
  };

  return (
    <dialog
      ref={ref}
      aria-label="תפריט"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => e.target === ref.current && onClose()}
      className="ms-0 me-auto h-dvh max-h-dvh w-[min(20rem,85vw)] border-0 bg-bg p-0 text-text shadow-[0_0_40px_rgb(0_0_0/0.3)] transition-[translate] duration-300 ease-out backdrop:bg-(--backdrop) starting:translate-x-full motion-reduce:transition-none"
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between px-4 pt-4 pb-2">
          <span className="font-display text-lg font-extrabold">תפריט</span>
          <button onClick={onClose} className="icon-btn" aria-label="סגירה">
            <X size={19} strokeWidth={1.8} />
          </button>
        </div>
        <nav aria-label="ניווט ראשי" className="flex-1 overflow-y-auto px-3 pb-3">
          <ul className="flex flex-col gap-0.5">{TABS.map(item)}</ul>
          <hr className="my-2 border-hairline" />
          <ul className="flex flex-col gap-0.5">{MORE.map(item)}</ul>
        </nav>
        <div className="border-t border-hairline p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
          <button onClick={onLogout} className="flex min-h-12 w-full items-center gap-3 rounded-xl px-3 py-2 text-[15px] font-semibold text-danger hover:bg-sunken">
            <span className="flex size-[32px] shrink-0 items-center justify-center rounded-[10px] bg-danger-soft">
              <LogOut size={18} aria-hidden />
            </span>
            התנתקות
          </button>
        </div>
      </div>
    </dialog>
  );
}
