"use client";

import { Select } from "@/components/ui/Select";
import { NumberField, range, Row, Section, SettingsScreen } from "../parts";

export default function CycleSettingsPage() {
  return (
    <SettingsScreen title="החודש שלי">
      {(data, patch) => (
        <Section id="cycle" hint="איך FreeRise מחלק את הזמן לחודשים ומה נחשב חודש טוב.">
          <Row label="יום תחילת החודש" hint="התזרים, התקציב והתחזית נספרים מהיום הזה. כדאי לבחור את יום המשכורת.">
            <Select label="יום תחילת החודש" className="w-28" value={String(data.cycle_start_day)} onChange={(v) => patch({ cycle_start_day: Number(v) })} options={range(1, 28).map((d) => ({ value: String(d), label: `${d} בחודש` }))} />
          </Row>
          <Row label="יעד לסוף החודש" hint="כמה תרצו שיישאר בסוף כל חודש. אפשר לשנות לכל חודש בנפרד במסך התזרים.">
            <NumberField label="יעד לסוף החודש" value={data.month_end_goal_default} onSave={(v) => patch({ month_end_goal_default: v })} />
          </Row>
          <Row label="גמישות במועד המשכורת" hint="הכנסה קבועה שמגיעה עד כמה ימים לפני או אחרי מועדה עדיין נספרת לחודש שלה.">
            <Select label="גמישות במועד המשכורת" className="w-28" value={String(data.income_grace_days)} onChange={(v) => patch({ income_grace_days: Number(v) })} options={range(0, 15).map((d) => ({ value: String(d), label: d === 0 ? "בלי" : `${d} ימים` }))} />
          </Row>
        </Section>
      )}
    </SettingsScreen>
  );
}
