/** Copy of `list` with item `i` moved by `delta` places (clamped to the ends). */
export function moveItem<T>(list: T[], i: number, delta: number): T[] {
  const j = Math.max(0, Math.min(list.length - 1, i + delta));
  if (i === j || i < 0 || i >= list.length) return list;
  const out = [...list];
  const [x] = out.splice(i, 1);
  out.splice(j, 0, x);
  return out;
}
