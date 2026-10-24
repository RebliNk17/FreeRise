"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { Ellipsis, X } from "lucide-react";
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
const useReducedMotion = () =>
  useSyncExternalStore(
    subscribeRM,
    () => matchMedia(RM).matches,
    () => false,
  );
const subscribeVis = (cb: () => void) => {
  document.addEventListener("visibilitychange", cb);
  return () => document.removeEventListener("visibilitychange", cb);
};
const useHidden = () =>
  useSyncExternalStore(
    subscribeVis,
    () => document.hidden,
    () => false,
  );

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
  const delay = advanceDelay({
    n,
    reduced,
    hover,
    focus,
    hidden,
    interacted,
    dragging: drag !== null,
  });
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
    mutate(
      (d) => d,
      () => send(a.method, a.path),
    );
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
        className="card touch-pan-y overflow-hidden select-none [&>ul]:items-stretch"
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
          style={{
            transform: `translateX(calc(${i * 100}% + ${drag ?? 0}px))`,
            transition: drag !== null || reduced ? "none" : "transform 500ms ease-in-out",
          }}
        >
          {items.map((it, k) => {
            const cta = ctaLabel(it);
            return (
              <li key={it.key} role="group" aria-roledescription="שקופית" aria-label={`${k + 1} מתוך ${n}`} inert={k !== i} className="flex w-full shrink-0 flex-col">
                <div className={`flex h-32 items-center justify-center ${BAND[it.severity]}`}>
                  <div className="h-full w-48 py-2">
                    <Illustration name={illustrationFor(it.kind, it.severity)} active={k === i} />
                  </div>
                </div>
                <div className="flex flex-1 flex-col gap-1 p-5 pt-4">
                  <p className="text-lg leading-snug font-bold">
                    <span className="sr-only">{SEVERITY_WORD[it.severity]}: </span>
                    {it.title}
                  </p>
                  <p className="line-clamp-3 text-[15px] leading-snug text-muted">
                    {splitAmounts(it.body).map((p, j) =>
                      p.bold ? (
                        <strong key={j} className="font-bold text-text">
                          {p.text}
                        </strong>
                      ) : (
                        p.text
                      ),
                    )}
                  </p>
                  <div className="mt-auto flex flex-col gap-2 pt-3">
                    {it.actions?.map((a, j) => (
                      <button key={a.label} type="button" className={`${j === 0 && !(cta && it.link) ? "btn" : "btn-secondary"} min-h-12 w-full`} onClick={() => act(it.key, a)}>
                        {a.label}
                      </button>
                    ))}
                    {cta && it.link && (
                      <Link href={it.link} className="btn min-h-12 w-full" draggable={false}>
                        {cta}
                      </Link>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      <div className="absolute start-2 top-2 flex items-center rounded-xl bg-surface/70">
        <Menu
          label="אפשרויות לתובנה"
          icon={<Ellipsis size={16} />}
          items={[
            {
              label: "תזכיר בעוד שבוע",
              onSelect: () => hide(cur.key, "snooze"),
            },
          ]}
        />
        <button type="button" className="flex size-9 items-center justify-center rounded-xl text-muted hover:bg-sunken hover:text-text" aria-label="הסתרת התובנה" onClick={() => hide(cur.key, "dismiss")}>
          <X size={16} />
        </button>
      </div>
      {n > 1 && (
        <div className="mt-2 flex items-center justify-center gap-2">
          {items.map((it, k) => (
            <button
              key={it.key}
              type="button"
              aria-label={`תובנה ${k + 1} מתוך ${n}`}
              aria-current={k === i}
              className={`size-2 rounded-full transition-colors motion-reduce:transition-none ${k === i ? "bg-brand" : "bg-border"} relative after:absolute after:-inset-2`}
              onClick={() => setIndex(k)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
