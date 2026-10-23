"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, Ellipsis, X } from "lucide-react";
import { send, type Insight } from "@/lib/api";
import { wrapIndex } from "@/lib/home";
import { advanceDelay, BAND, ctaLabel, illustrationFor, SEVERITY_WORD, splitAmounts } from "@/lib/insights";
import { useHome } from "./context";
import { Illustration } from "./illustrations";
import { useApi } from "@/lib/useApi";
import { Menu } from "./parts";

const RM = "(prefers-reduced-motion: reduce)";
const subscribeRM = (cb: () => void) => {
  const m = matchMedia(RM);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
};
const useReducedMotion = () => useSyncExternalStore(subscribeRM, () => matchMedia(RM).matches, () => false);
const subscribeVis = (cb: () => void) => {
  document.addEventListener("visibilitychange", cb);
  return () => document.removeEventListener("visibilitychange", cb);
};
const useHidden = () => useSyncExternalStore(subscribeVis, () => document.hidden, () => false);

/** One insight at a time: slide (transform), swipe, ‹ ›, dots; auto-advance 12s after the intro, paused on hover/focus/hidden tab, off after any interaction or under reduced motion. */
export function InsightCarousel() {
  const { version, mutate } = useHome();
  const { data, setData } = useApi<Insight[]>("/insights", version);
  const items = data ?? [];
  const n = items.length;
  const [rawIndex, setIndex] = useState(0);
  const i = wrapIndex(rawIndex, n);
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const [interacted, setInteracted] = useState(false);
  const [drag, setDrag] = useState<number | null>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const moved = useRef(false);
  const reduced = useReducedMotion();
  const hidden = useHidden();
  const delay = advanceDelay({ n, reduced, hover, focus, hidden, interacted, dragging: drag !== null });
  const paused = delay === null;

  // Restarts per slide so each card plays its intro before the clock runs.
  useEffect(() => {
    if (delay === null) return;
    const t = setTimeout(() => setIndex((x) => wrapIndex(x + 1, n)), delay);
    return () => clearTimeout(t);
  }, [delay, i, n]);

  if (!n) return null;
  const cur = items[i];

  /** Run a card's own action (e.g. "לא יורדת החודש"), then drop the card; home refetches. */
  function act(key: string, a: NonNullable<Insight["actions"]>[number]) {
    setData((d) => d?.filter((x) => x.key !== key));
    mutate((d) => d, () => send(a.method, a.path));
  }

  function hide(key: string, how: "dismiss" | "snooze") {
    setData((d) => d?.filter((x) => x.key !== key));
    send("POST", `/insights/${encodeURIComponent(key)}/${how}`).catch(() => {});
  }

  function end() {
    const dx = drag ?? 0;
    start.current = null;
    setDrag(null);
    // RTL: the next card sits to the left, so dragging content right reveals it.
    if (Math.abs(dx) > 50) setIndex(wrapIndex(i + (dx > 0 ? 1 : -1), n));
  }

  return (
    <section
      aria-roledescription="קרוסלה"
      aria-label="תובנות"
      className="relative"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setFocus(true)}
      onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setFocus(false)}
      onPointerDownCapture={() => setInteracted(true)}
      onKeyDownCapture={() => setInteracted(true)}
    >
      <div
        className="card touch-pan-y overflow-hidden select-none"
        onPointerDown={(e) => {
          if (n < 2 || (e.pointerType === "mouse" && e.button !== 0)) return;
          start.current = { x: e.clientX, y: e.clientY };
          moved.current = false;
        }}
        onPointerMove={(e) => {
          if (!start.current) return;
          const dx = e.clientX - start.current.x;
          if (!moved.current && Math.abs(dx) < 8) return;
          if (!moved.current && Math.abs(e.clientY - start.current.y) > Math.abs(dx)) return void (start.current = null);
          moved.current = true;
          setDrag(dx);
        }}
        onPointerUp={end}
        onPointerCancel={end}
        onPointerLeave={() => start.current && end()}
        onClickCapture={(e) => {
          if (moved.current) {
            e.preventDefault();
            e.stopPropagation();
            moved.current = false;
          }
        }}
      >
        <ul
          className="flex"
          aria-live={paused ? "polite" : "off"}
          style={{ transform: `translateX(calc(${i * 100}% + ${drag ?? 0}px))`, transition: drag !== null || reduced ? "none" : "transform 500ms ease-in-out" }}
        >
          {items.map((it, k) => {
            const cta = ctaLabel(it);
            return (
              <li key={it.key} role="group" aria-roledescription="שקופית" aria-label={`${k + 1} מתוך ${n}`} inert={k !== i} className="flex w-full shrink-0 items-start gap-3 p-3.5 pe-20">
                <div className={`flex size-13 shrink-0 items-center justify-center overflow-hidden rounded-2xl ${BAND[it.severity]}`}>
                  <Illustration name={illustrationFor(it.kind, it.severity)} active={k === i} />
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <p className="text-[15px] leading-snug font-bold">
                    <span className="sr-only">{SEVERITY_WORD[it.severity]}: </span>
                    {it.title}
                  </p>
                  <p className="line-clamp-3 text-[13px] leading-snug text-muted">
                    {splitAmounts(it.body).map((p, j) => (p.bold ? <strong key={j} className="font-bold text-text">{p.text}</strong> : p.text))}
                  </p>
                  {cta && it.link && (
                    <Link href={it.link} className="link mt-1 self-start" draggable={false}>
                      {cta} ←
                    </Link>
                  )}
                  {it.actions && it.actions.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-2">
                      {it.actions.map((a) => (
                        <button key={a.label} type="button" className="btn-secondary min-h-11" onClick={() => act(it.key, a)}>
                          {a.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      <div className="absolute end-2 top-2 flex items-center">
        <Menu label="אפשרויות לתובנה" icon={<Ellipsis size={16} />} items={[{ label: "תזכיר בעוד שבוע", onSelect: () => hide(cur.key, "snooze") }]} />
        <button type="button" className="flex size-9 items-center justify-center rounded-xl text-muted hover:bg-sunken hover:text-text" aria-label="הסתרת התובנה" onClick={() => hide(cur.key, "dismiss")}>
          <X size={16} />
        </button>
      </div>
      {n > 1 && (
        <span className="pointer-events-none absolute end-3.5 bottom-3 text-xs text-faint tabular-nums" dir="ltr" aria-hidden>
          {i + 1}/{n}
        </span>
      )}
      {n > 1 && (
        <div className="mt-1 flex items-center justify-center gap-1">
          <button type="button" className="flex size-9 items-center justify-center rounded-full text-muted hover:text-text" aria-label="התובנה הקודמת" onClick={() => setIndex(wrapIndex(i - 1, n))}>
            <ChevronRight size={18} />
          </button>
          <div className="flex items-center gap-1.5">
            {items.map((it, k) => (
              <button
                key={it.key}
                type="button"
                aria-label={`תובנה ${k + 1} מתוך ${n}`}
                aria-current={k === i}
                className={`h-1.5 rounded-full transition-all motion-reduce:transition-none ${k === i ? "w-4 bg-brand" : "w-1.5 bg-border"} relative after:absolute after:-inset-2`}
                onClick={() => setIndex(k)}
              />
            ))}
          </div>
          <button type="button" className="flex size-9 items-center justify-center rounded-full text-muted hover:text-text" aria-label="התובנה הבאה" onClick={() => setIndex(wrapIndex(i + 1, n))}>
            <ChevronLeft size={18} />
          </button>
        </div>
      )}
    </section>
  );
}
