import Link from "next/link";
import { ArrowLeftRight, Bell, ChevronLeft, CreditCard, FlaskConical, KeyRound, Receipt, Settings, Target, TrendingUp, Wallet } from "lucide-react";

const LINKS = [
  { href: "/plans", label: "יעדי חיסכון", icon: Target },
  { href: "/cost", label: "חיפוש הוצאות", icon: Receipt },
  { href: "/whatif", label: "תרחישים", icon: FlaskConical },
  { href: "/progress", label: "המגמות שלי", icon: TrendingUp },
  { href: "/transactions", label: "עסקאות", icon: ArrowLeftRight },
  { href: "/accounts", label: "חשבונות", icon: Wallet },
  { href: "/reconcile", label: "התאמת חיובי אשראי", icon: CreditCard },
  { href: "/settings/credentials", label: "חיבורים לבנקים ואשראי", icon: KeyRound },
  { href: "/notifications", label: "התראות", icon: Bell },
  { href: "/settings", label: "הגדרות", icon: Settings },
];

export default function MorePage() {
  return (
    <div className="flex flex-col gap-3">
      <h1 className="page-title">עוד</h1>
      <ul className="card divide-y divide-hairline overflow-hidden">
        {LINKS.map(({ href, label, icon: Icon }) => (
          <li key={href}>
            <Link href={href} className="flex min-h-14 items-center gap-3 px-4 py-2.5 text-[15px] hover:bg-sunken/60">
              <span className="flex size-[34px] shrink-0 items-center justify-center rounded-[11px] bg-brand-soft text-brand">
                <Icon size={18} aria-hidden />
              </span>
              <span className="flex-1 font-semibold">{label}</span>
              <ChevronLeft size={18} className="text-faint" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
