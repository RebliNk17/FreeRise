"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { Check, ChevronDown, Search } from "lucide-react";
import { filterOptions, moveIndex, typeahead, type Option } from "@/lib/listbox";

export type { Option } from "@/lib/listbox";

const SHEET = "(max-width: 479px)";
const SEARCH_MIN = 9; // search box when > 8 options

/**
 * Custom single-select (WAI-ARIA listbox pattern). Desktop: a fixed popover under (or above) the trigger,
 * so it escapes overflow/clipping in cards and dialogs. Under 480px: a bottom sheet.
 */
export function Select({
  value,
  onChange,
  options,
  label,
  placeholder = "בחירה…",
  className = "",
  autoFocus,
}: {
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  /** Accessible name; announced together with the selected value. */
  label: string;
  placeholder?: string;
  className?: string;
  autoFocus?: boolean;
}) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const searchBox = useRef<HTMLInputElement>(null);
  const typed = useRef({ q: "", t: 0 });
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(-1);
  const [pos, setPos] = useState<CSSProperties | null>(null); // null = sheet

  const searchable = options.length >= SEARCH_MIN;
  const shown = searchable ? filterOptions(options, query) : options;
  const selected = options.find((o) => o.value === value);

  function show() {
    setQuery("");
    const i = options.findIndex((o) => o.value === value);
    setActive(i >= 0 && !options[i].disabled ? i : moveIndex(options, -1, "Home"));
    setOpen(true);
  }
  function close(refocus = true) {
    setOpen(false);
    if (refocus) button.current?.focus();
  }
  function pick(o: Option | undefined) {
    if (!o || o.disabled) return;
    if (o.value !== value) onChange(o.value);
    close();
  }

  useEffect(() => {
    if (autoFocus) button.current?.focus();
  }, [autoFocus]);

  // Placement: below the trigger, flipped up when there's no room; recomputed on scroll/resize.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const r = button.current!.getBoundingClientRect();
      if (matchMedia(SHEET).matches) return setPos(null);
      const below = innerHeight - r.bottom;
      const up = below < 320 && r.top > below;
      const maxHeight = Math.min(320, (up ? r.top : below) - 12);
      setPos({ left: r.left, width: r.width, maxHeight, ...(up ? { bottom: innerHeight - r.top + 4 } : { top: r.bottom + 4 }) });
    };
    place();
    (searchable ? searchBox : list).current?.focus({ preventScroll: true });
    addEventListener("resize", place);
    addEventListener("scroll", place, true);
    const outside = (e: PointerEvent) => !root.current?.contains(e.target as Node) && close(false);
    document.addEventListener("pointerdown", outside);
    return () => {
      removeEventListener("resize", place);
      removeEventListener("scroll", place, true);
      document.removeEventListener("pointerdown", outside);
    };
  }, [open, searchable]);

  useEffect(() => {
    if (open && active >= 0) document.getElementById(`${id}-o${active}`)?.scrollIntoView({ block: "nearest" });
  }, [open, active, id]);

  function onListKey(e: KeyboardEvent) {
    const k = e.key;
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(k)) {
      // In the search box Home/End move the caret.
      if (e.target === searchBox.current && (k === "Home" || k === "End")) return;
      e.preventDefault();
      setActive(moveIndex(shown, active, k));
    } else if (k === "Enter" || (k === " " && !searchable)) {
      e.preventDefault();
      pick(shown[active]);
    } else if (k === "Escape") {
      e.preventDefault(); // keep an enclosing <dialog> open
      e.stopPropagation();
      close();
    } else if (k === "Tab") {
      close(false);
    } else if (!searchable && k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const now = e.timeStamp;
      typed.current = { q: (now - typed.current.t < 600 ? typed.current.q : "") + k, t: now };
      const i = typeahead(shown, typed.current.q, active);
      if (i >= 0) setActive(i);
    }
  }

  return (
    <div ref={root} className={`relative ${className}`}>
      <span id={`${id}-l`} className="sr-only">
        {label}
      </span>
      <button
        ref={button}
        type="button"
        className={`input flex items-center gap-2.5 text-start ${open ? "border-brand ring-1 ring-brand" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-lb`}
        aria-labelledby={`${id}-l ${id}-v`}
        onClick={() => (open ? close() : show())}
        onKeyDown={(e) => {
          if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
            e.preventDefault();
            show();
          }
        }}
      >
        {selected?.icon && <span className="-my-1 -ms-1 size-8 shrink-0">{selected.icon}</span>}
        <span id={`${id}-v`} className={`min-w-0 flex-1 truncate ${selected ? (selected.icon ? "font-bold" : "") : "text-faint"}`}>
          {selected?.label ?? placeholder}
        </span>
        <ChevronDown size={16} aria-hidden className={`shrink-0 text-muted transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <>
          {!pos && <div className="fixed inset-0 z-50 bg-(--backdrop)" aria-hidden onClick={() => close()} />}
          <div
            style={pos ?? undefined}
            className={`select-pop fixed z-50 flex flex-col overflow-hidden bg-surface text-text shadow-card ${
              pos ? "rounded-2xl border border-border" : "inset-x-0 bottom-0 max-h-[70dvh] rounded-t-[28px] pt-2 pb-[env(safe-area-inset-bottom)]"
            }`}
            onKeyDown={onListKey}
          >
            {searchable && (
              <div className="relative border-b border-hairline p-2">
                <Search size={16} aria-hidden className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 text-muted" />
                <input
                  ref={searchBox}
                  type="search"
                  className="min-h-10 w-full rounded-xl bg-sunken py-2 pr-8 pl-2 text-sm outline-none placeholder:text-faint"
                  placeholder="חיפוש…"
                  aria-label={`חיפוש: ${label}`}
                  role="combobox"
                  aria-expanded
                  aria-controls={`${id}-lb`}
                  aria-autocomplete="list"
                  aria-activedescendant={active >= 0 ? `${id}-o${active}` : undefined}
                  value={query}
                  onChange={(e) => {
                    const next = filterOptions(options, e.target.value);
                    setQuery(e.target.value);
                    setActive(moveIndex(next, -1, "Home"));
                  }}
                />
              </div>
            )}
            <ul
              ref={list}
              id={`${id}-lb`}
              role="listbox"
              tabIndex={-1}
              aria-labelledby={`${id}-l`}
              aria-activedescendant={!searchable && active >= 0 ? `${id}-o${active}` : undefined}
              className="min-h-0 flex-1 overflow-y-auto p-1 outline-none"
            >
              {shown.length === 0 && <li className="px-3 py-2 text-sm text-muted">אין תוצאות</li>}
              {shown.map((o, i) => {
                const header = o.group && o.group !== shown[i - 1]?.group ? o.group : null;
                return [
                  header && (
                    <li key={`g:${header}`} role="presentation" className="px-3 pt-2.5 pb-1 text-xs font-semibold text-muted">
                      {header}
                    </li>
                  ),
                  <li
                    key={o.value}
                    id={`${id}-o${i}`}
                    role="option"
                    aria-selected={o.value === value}
                    aria-disabled={o.disabled || undefined}
                    className={`flex cursor-pointer items-center gap-3 rounded-xl px-3 text-[15px] ${o.icon ? "min-h-13 py-1.5" : "min-h-11 py-2"} ${i === active ? "bg-sunken" : ""} ${
                      o.disabled ? "cursor-default opacity-50" : ""
                    } ${o.value === value ? "font-bold text-brand" : ""}`}
                    onPointerMove={() => !o.disabled && i !== active && setActive(i)}
                    onClick={() => pick(o)}
                  >
                    {o.icon && <span className="size-10 shrink-0">{o.icon}</span>}
                    <span className="min-w-0 flex-1 truncate">{o.label}</span>
                    {o.value === value && <Check size={16} aria-hidden className="shrink-0" />}
                  </li>,
                ];
              })}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
