import { Money } from "@/components/Amount";
import { Card } from "@/components/Card";
import type { HomeData } from "@/lib/home";
import { Item } from "./FixedCard";

// ponytail: keyword match on the fee's description; unknown fees just show no explanation.
const EXPLAIN: [RegExp, string][] = [
  [/ריבית/, "ריבית על יתרת חובה (מינוס) בחשבון."],
  [/המרה|מט"ח|מט״ח|conversion/i, "עמלה על עסקה במטבע חוץ."],
  [/דמי כרטיס/, "דמי כרטיס חודשיים. אפשר לבקש מחברת האשראי לבטל או להנחות אותם."],
  [/משיכ/, "עמלה על משיכת מזומן."],
  [/דמי ניהול|עמלת ניהול|ניהול חשבון/, "דמי ניהול חשבון בבנק. אפשר לבקש מסלול עמלות זול יותר."],
  [/פעולה|ערוץ|העברה/, "עמלה על פעולה בבנק (העברה, הפקדה וכדומה)."],
  [/פנקס|שיק|צ'ק|צ׳ק/, "עמלה על פנקס שיקים או שיק."],
];

export function feeExplanation(label: string): string | null {
  return EXPLAIN.find(([re]) => re.test(label))?.[1] ?? null;
}

/** "עמלות" (#fees): every fee this cycle with its date, account, amount and what it is. Hidden when there are none. */
export function FeesCard({ f }: { f: HomeData["fees"] }) {
  if (!f || !f.items.length) return null;
  const count = f.items.reduce((n, it) => n + Math.max(1, it.transactions.length), 0);
  return (
    <div id="fees" className="scroll-mt-20">
      <Card title="עמלות" action={<span className="text-xs text-muted">{count === 1 ? "חיוב אחד" : `${count} חיובים`}</span>}>
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-xs text-muted">שולם החודש</span>
          <Money value={f.spent} className="text-[28px] leading-tight font-extrabold text-danger" />
        </div>
        <ul className="flex flex-col gap-1 rounded-2xl bg-bg p-1.5">
          {f.items.map((it, i) => {
            const why = feeExplanation(it.label);
            return (
              <li key={it.recurring_id ?? `${it.label}-${i}`}>
                <Item it={it} />
                {why && <p className="px-2 pb-2 text-xs text-muted">{why}</p>}
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}
