import { createElement } from "react";
import {
  Baby, Banknote, Bus, Car, CircleDot, Coins, CreditCard, Droplet, Dumbbell, Gift, GraduationCap, HeartPulse, House, Landmark, type LucideIcon,
  Pill, Plane, Receipt, Shield, Shirt, ShoppingBag, ShoppingCart, Smartphone, Ticket, Utensils, Wifi, Zap,
} from "lucide-react";

// ponytail: keyword match on the Hebrew name; unknown categories get a dot. Add entries as categories appear.
const ICONS: [string, LucideIcon][] = [
  ["סופר", ShoppingCart], ["כלכלה", ShoppingCart], ["אוכל", Utensils], ["מסעד", Utensils], ["תחבורה", Bus], ["רכב", Car], ["דלק", Car],
  ["ביגוד", Shirt], ["פארמה", Pill], ["בריאות", HeartPulse], ["תיירות", Plane], ["טיס", Plane], ["מתנ", Gift], ["פנאי", Ticket],
  ["ספורט", Dumbbell], ["חינוך", GraduationCap], ["ילד", Baby], ["משכנתא", House], ["דיור", House], ["ארנונה", Landmark], ["חשמל", Zap],
  ["מים", Droplet], ["תקשורת", Smartphone], ["דיגיטל", Wifi], ["ביטוח", Shield], ["עמלות", Receipt], ["אשראי", CreditCard], ["הלוואה", Banknote],
  ["תשלומים", CreditCard], ["קניות", ShoppingBag], ["משכורת", Coins], ["הכנסות", Coins], ["קצבאות", Coins], ["חיסכון", Coins], ["השקעה", Coins],
];

export function categoryIcon(name: string | null | undefined): LucideIcon {
  return (name && ICONS.find(([k]) => name.includes(k))?.[1]) || CircleDot;
}

/** 40px progress ring (conic) with the category's line icon inside; coral and full when over. */
export function CategoryRing({ name, percent, over }: { name: string | null | undefined; percent: number; over: boolean }) {
  const p = over ? 100 : Math.max(0, Math.min(100, percent));
  const fg = over ? "var(--danger)" : "var(--brand)";
  return (
    <span aria-hidden className="flex size-10 shrink-0 items-center justify-center rounded-full" style={{ background: `conic-gradient(${fg} 0 ${p}%, ${over ? fg : "var(--brand-soft)"} ${p}% 100%)` }}>
      <span className="flex size-[30px] items-center justify-center rounded-full bg-surface" style={{ color: fg }}>
        {/* createElement: the icon is a static lookup, not a component made during render */}
        {createElement(categoryIcon(name), { size: 16, strokeWidth: 2 })}
      </span>
    </span>
  );
}
