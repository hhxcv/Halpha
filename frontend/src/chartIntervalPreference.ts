export type PreferredChartInterval = "1m" | "5m" | "15m" | "1h" | "4h" | "1d";

const SUPPORTED_INTERVALS = new Set<PreferredChartInterval>([
  "1m",
  "5m",
  "15m",
  "1h",
  "4h",
  "1d",
]);

type ChartIntervalStorage = Pick<Storage, "getItem" | "setItem">;

function storageKey(environmentId: string, instrumentRef: string): string {
  return `halpha:chart-interval:${environmentId}:${instrumentRef}`;
}

function browserStorage(): ChartIntervalStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readChartIntervalPreference(
  environmentId: string,
  instrumentRef: string,
  fallback: PreferredChartInterval = "15m",
  storage: ChartIntervalStorage | null = browserStorage(),
): PreferredChartInterval {
  if (!storage || !environmentId || !instrumentRef) {
    return fallback;
  }
  try {
    const stored = storage.getItem(storageKey(environmentId, instrumentRef));
    return SUPPORTED_INTERVALS.has(stored as PreferredChartInterval)
      ? stored as PreferredChartInterval
      : fallback;
  } catch {
    return fallback;
  }
}

export function writeChartIntervalPreference(
  environmentId: string,
  instrumentRef: string,
  interval: PreferredChartInterval,
  storage: ChartIntervalStorage | null = browserStorage(),
): void {
  if (
    !storage
    || !environmentId
    || !instrumentRef
    || !SUPPORTED_INTERVALS.has(interval)
  ) {
    return;
  }
  try {
    storage.setItem(storageKey(environmentId, instrumentRef), interval);
  } catch {
    // Browser storage is optional UI state; trading behavior must not depend on it.
  }
}
