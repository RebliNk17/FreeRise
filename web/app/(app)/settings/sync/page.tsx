"use client";

import { Moon, Sun } from "lucide-react";
import { Switch } from "@/components/Switch";
import { hh, range, Section, SettingsScreen, type Patch } from "../parts";

export default function SyncSettingsPage() {
  return (
    <SettingsScreen title="סנכרון אוטומטי">
      {(data, patch) => (
        <Section id="sync" action={<SyncSwitch hours={data.sync_hours} patch={patch} />} hint="בשעות המסומנות FreeRise מושך תנועות חדשות מכל החיבורים.">
          <SyncTimeline hours={data.sync_hours} onChange={(sync_hours) => patch({ sync_hours })} />
        </Section>
      )}
    </SettingsScreen>
  );
}

const DEFAULT_SYNC = [7, 14, 21];

/** Off = no hours (manual sync only). On restores the default; ponytail: remember the last custom hours if turning it back on loses them too often. */
function SyncSwitch({ hours, patch }: { hours: number[]; patch: Patch }) {
  return <Switch label={hours.length ? "פעיל" : "כבוי"} checked={hours.length > 0} onChange={(on) => patch({ sync_hours: on ? DEFAULT_SYNC : [] })} />;
}

function SyncSummary({ hours }: { hours: number[] }) {
  if (!hours.length) return <p className="text-[13px] text-muted">אין סנכרון אוטומטי. אפשר לסנכרן ידנית ממסך החיבורים.</p>;
  const now = new Date().getHours();
  const next = hours.find((h) => h > now) ?? hours[0];
  return (
    <p className="text-[13px] text-muted">
      {hours.length === 1 ? "סנכרון אחד" : `${hours.length} סנכרונים`} ביום · הבא ב-<span className="font-bold text-text tabular-nums">{hh(next)}</span>
      {hours.length > 4 && <span className="text-sun-strong"> · בנקים מסוימים חוסמים כניסות תכופות, עדיף לא יותר מ-4</span>}
    </p>
  );
}

/** The day as one strip (two rows of 12 on phones, so each hour is tappable); night hours shaded, picked hours filled and labelled. */
function SyncTimeline({ hours, onChange }: { hours: number[]; onChange: (h: number[]) => void }) {
  const toggle = (h: number) => onChange(hours.includes(h) ? hours.filter((x) => x !== h) : [...hours, h].sort((a, b) => a - b));
  if (!hours.length) return <SyncSummary hours={hours} />;
  return (
    <div className="flex flex-col gap-4">
      <div dir="ltr">
        <div className="relative hidden h-6 text-[13px] font-bold text-brand tabular-nums sm:block">
          {hours.map((h) => (
            <span key={h} className="absolute -translate-x-1/2" style={{ left: `${((h + 0.5) / 24) * 100}%` }}>
              {hh(h)}
            </span>
          ))}
        </div>
        <div role="group" aria-label="שעות סנכרון" className="grid grid-cols-12 gap-x-0.5 gap-y-1.5 sm:grid-cols-24">
          {range(0, 23).map((h) => {
            const on = hours.includes(h);
            const ends = h === 0 ? "rounded-l-xl" : h === 23 ? "rounded-r-xl" : h === 11 ? "max-sm:rounded-r-xl" : h === 12 ? "max-sm:rounded-l-xl" : "";
            return (
              <button
                key={h}
                type="button"
                data-tip={hh(h)}
                aria-pressed={on}
                aria-label={`סנכרון בשעה ${hh(h)}`}
                onClick={() => toggle(h)}
                className={`h-11 min-w-0 rounded-[4px] sm:h-12 ${ends} ${on ? "bg-brand-fill" : `${h < 6 || h >= 22 ? "bg-border" : "bg-sunken"} hover:bg-brand-soft`}`}
              >
                <span aria-hidden className={`text-xs font-bold tabular-nums sm:hidden ${on ? "text-brand-fg" : "text-muted"}`}>
                  {String(h).padStart(2, "0")}
                </span>
              </button>
            );
          })}
        </div>
        <div className="mt-1.5 hidden justify-between text-xs text-faint tabular-nums sm:flex">
          <span className="flex items-center gap-1"><Moon size={12} aria-hidden /> 00:00</span>
          <span>06:00</span>
          <span className="flex items-center gap-1"><Sun size={12} aria-hidden /> 12:00</span>
          <span>18:00</span>
          <span>24:00</span>
        </div>
      </div>
      <SyncSummary hours={hours} />
    </div>
  );
}
