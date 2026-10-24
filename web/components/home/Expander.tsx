"use client";

import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";

/** Disclosure: button with aria-expanded; content animates height (grid 0fr→1fr) and mounts on first open. */
export function Expander({
  label,
  children,
  className = "",
  buttonClassName = "flex",
  labelClassName = "min-w-0 flex-1",
  rowClassName = "",
  aside,
  chevron = true,
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  buttonClassName?: string;
  labelClassName?: string;
  /** Wrapper of the button + `aside` (a sibling control, e.g. an edit button laid over a grid cell). */
  rowClassName?: string;
  aside?: React.ReactNode;
  chevron?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const id = useId();
  return (
    <div className={className}>
      <div className={rowClassName}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        className={`w-full items-center gap-2 rounded-xl text-start transition-colors hover:bg-sunken/60 active:bg-sunken ${buttonClassName}`}
        onClick={() => {
          setMounted(true);
          setOpen((o) => !o);
        }}
      >
        <span className={labelClassName}>{label}</span>
        {chevron && <ChevronDown size={18} aria-hidden className={`shrink-0 text-muted transition-transform duration-300 motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />}
      </button>
      {aside}
      </div>
      <div id={id} inert={!open} className={`grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
        <div className="min-h-0 overflow-hidden">{mounted && children}</div>
      </div>
    </div>
  );
}
