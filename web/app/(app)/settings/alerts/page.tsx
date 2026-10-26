"use client";

import { Select } from "@/components/ui/Select";
import { hh, NumberField, range, Row, Section, SettingsScreen } from "../parts";

export default function AlertSettingsPage() {
  return (
    <SettingsScreen title="התראות">
      {(data, patch) => (
        <Section id="alerts" hint="ההתראות מופיעות בפעמון למעלה, ואפשר לקבל אותן גם בטלגרם.">
          <Row label="בדיקה יומית" hint="שעה שבה נבדקות התראות כמו חריגה מתקציב ותזכורות. נבדקות גם אחרי כל סנכרון.">
            <Select label="שעת הבדיקה היומית" className="w-28" value={String(data.digest_hour)} onChange={(v) => patch({ digest_hour: Number(v) })} options={range(0, 23).map((h) => ({ value: String(h), label: hh(h) }))} />
          </Row>
          <Row label="עסקה גדולה מעל" hint="התראה על חיוב בודד מעל הסכום הזה, או מעל פי 3 מהרגיל בקטגוריה שלו, הגבוה מביניהם.">
            <NumberField label="סף לעסקה גדולה" value={data.large_txn_min} onSave={(v) => patch({ large_txn_min: v })} />
          </Row>
        </Section>
      )}
    </SettingsScreen>
  );
}
