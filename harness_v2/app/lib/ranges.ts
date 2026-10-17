/** A request's byte range ("bytes=100-199", "bytes=500-", "bytes=-300") in a file of `size` bytes: [start, end]
 * inclusive, "bad" when it cannot be served (416), or undefined when none was asked (the whole file). */
export function rangeOf(header: string | null, size: number): [number, number] | "bad" | undefined {
  const m = /^bytes=(\d*)-(\d*)$/.exec(header ?? "");
  if (!m || (!m[1] && !m[2])) return undefined;
  const start = m[1] ? Number(m[1]) : Math.max(0, size - Number(m[2]));
  const end = m[1] && m[2] ? Math.min(Number(m[2]), size - 1) : size - 1;
  return start > end || start >= size ? "bad" : [start, end];
}
