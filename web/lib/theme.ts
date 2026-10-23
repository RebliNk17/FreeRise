export type Theme = "system" | "light" | "dark";
const KEY = "freerise-theme";
/** Fired by setTheme so every toggle on the page (header button, settings radios) stays in sync. */
export const THEME_CHANGED = "freerise:theme";
const COLORS = { light: "#fbf7f0", dark: "#171512" };

export function getTheme(): Theme {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(t: Theme) {
  const el = document.documentElement;
  if (t === "system") el.removeAttribute("data-theme");
  else el.setAttribute("data-theme", t);
  const dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  let m = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (!m) {
    m = document.createElement("meta");
    m.name = "theme-color";
    document.head.appendChild(m);
  }
  m.content = dark ? COLORS.dark : COLORS.light;
}

export function setTheme(t: Theme) {
  try {
    if (t === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, t);
  } catch {}
  applyTheme(t);
  window.dispatchEvent(new Event(THEME_CHANGED));
}
