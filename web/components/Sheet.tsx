"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

/** Bottom sheet (native modal <dialog>: focus trap + Escape); backdrop tap or swipe-down on the header closes too.
 * header: rendered in the swipe handle area (under the grab bar); children scroll. */
export function Sheet({ labelledBy, onClose, header, children }: { labelledBy: string; onClose: () => void; header?: React.ReactNode; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [dy, setDy] = useState<number | null>(null);
  const startY = useRef<number | null>(null);

  useEffect(() => {
    const d = ref.current!;
    const opener = document.activeElement as HTMLElement | null;
    d.showModal();
    return () => {
      d.close();
      opener?.focus();
    };
  }, []);

  const swipe = {
    onPointerDown: (e: React.PointerEvent) => void (startY.current = e.clientY),
    onPointerMove: (e: React.PointerEvent) => startY.current != null && setDy(Math.max(0, e.clientY - startY.current)),
    onPointerUp: () => {
      startY.current = null;
      if ((dy ?? 0) > 80) onClose();
      setDy(null);
    },
    onPointerCancel: () => ((startY.current = null), setDy(null)),
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby={labelledBy}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => e.target === ref.current && onClose()}
      style={dy != null ? { translate: `0 ${dy}px`, transition: "none" } : undefined}
      className="mx-auto mt-auto mb-0 max-h-[90dvh] w-full max-w-lg overflow-hidden rounded-t-[28px] border-0 bg-bg p-0 text-text shadow-[0_-10px_40px_rgb(0_0_0/0.25)] transition-[translate] duration-300 ease-out backdrop:bg-(--backdrop) starting:translate-y-full motion-reduce:transition-none"
    >
      <div className="flex max-h-[90dvh] flex-col">
        <header className="flex touch-none flex-col gap-3.5 px-5 pt-2.5 pb-4" {...swipe}>
          <div className="mx-auto h-[5px] w-11 rounded-full bg-border" aria-hidden />
          {header}
        </header>
        <div className="overflow-y-auto px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">{children}</div>
      </div>
    </dialog>
  );
}

/** Title row for a Sheet header: title, an optional action, close button. */
export function SheetTitle({ id, title, action, onClose }: { id: string; title: React.ReactNode; action?: React.ReactNode; onClose: () => void }) {
  return (
    <div className="flex items-center gap-2">
      <h2 id={id} className="min-w-0 flex-1 truncate font-display text-[19px] font-bold">
        {title}
      </h2>
      {action}
      <button type="button" className="icon-btn ms-auto size-11" aria-label="סגירה" onClick={onClose}>
        <X size={18} />
      </button>
    </div>
  );
}
