export function formatUtc(value: string | null): string {
  if (!value) return "UNKNOWN";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "UNKNOWN";
  return parsed.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
}
export function shortDigest(value: string | null): string {
  if (!value) return "NOT BOUND";
  return value.length > 16 ? `${value.slice(0, 12)}…${value.slice(-4)}` : value;
}
