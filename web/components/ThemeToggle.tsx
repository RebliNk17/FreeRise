"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { getTheme, setTheme, THEME_CHANGED, type Theme } from "@/lib/theme";

const OPTIONS: { value: Theme; label: string; aria: string }[] = [
  { value: "system", label: "מערכת", aria: "עיצוב לפי המערכת" },
  { value: "light", label: "בהיר", aria: "עיצוב בהיר" },
  { value: "dark", label: "כהה", aria: "עיצוב כהה" },
];

function useTheme() {
  const [theme, set] = useState<Theme>("system");
  useEffect(() => {
    const sync = () => set(getTheme());
    sync(); // read localStorage after hydration to avoid a mismatch
    window.addEventListener(THEME_CHANGED, sync);
    return () => window.removeEventListener(THEME_CHANGED, sync);
  }, []);
  return [theme, setTheme] as const;
}

export function ThemeToggle() {
  const [theme, set] = useTheme();
  return (
    <div role="radiogroup" aria-label="עיצוב" className="flex rounded-[14px] bg-sunken p-1">
      {OPTIONS.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={theme === o.value}
          aria-label={o.aria}
          onClick={() => set(o.value)}
          className={`min-h-10 flex-1 rounded-[11px] px-3 py-1.5 text-sm font-semibold ${theme === o.value ? "bg-surface text-text shadow-card" : "text-muted"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// Header button: cycles light <-> dark. Icon swap is pure CSS (globals.css) so it follows the OS in "system" too.
export function ThemeButton() {
  const [, set] = useTheme();
  const isDark = () => getComputedStyle(document.documentElement).colorScheme === "dark";
  return (
    <button onClick={() => set(isDark() ? "light" : "dark")} className="icon-btn" aria-label="החלפת מצב בהיר/כהה" title="החלפת עיצוב">
      <Sun size={19} strokeWidth={1.8} className="theme-sun" />
      <Moon size={19} strokeWidth={1.8} className="theme-moon" />
    </button>
  );
}
