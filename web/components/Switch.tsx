export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
      <input
        type="checkbox"
        role="switch"
        className="peer sr-only"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="relative h-6 w-10 shrink-0 rounded-full bg-border transition peer-checked:bg-brand-fill peer-focus-visible:ring-2 peer-focus-visible:ring-brand after:absolute after:top-0.5 after:right-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:transition peer-checked:after:-translate-x-4" />
      {/* ponytail: min width fits "פעיל"/"כבוי" so an end-aligned switch doesn't shift when the label swaps */}
      <span className="min-w-7">{label}</span>
    </label>
  );
}
