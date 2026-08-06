import { describe, expect, it } from "vitest";

import {
  readChartIntervalPreference,
  writeChartIntervalPreference,
} from "./chartIntervalPreference";

describe("chart interval preference", () => {
  function memoryStorage() {
    const values = new Map<string, string>();
    return {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
  }

  it("keeps the selected interval within one environment and instrument", () => {
    const storage = memoryStorage();
    writeChartIntervalPreference(
      "binance-demo-primary",
      "BTCUSDT-PERP",
      "4h",
      storage,
    );

    expect(
      readChartIntervalPreference(
        "binance-demo-primary",
        "BTCUSDT-PERP",
        "15m",
        storage,
      ),
    ).toBe("4h");
  });

  it("does not mix demo, live, or another instrument", () => {
    const storage = memoryStorage();
    writeChartIntervalPreference(
      "binance-demo-primary",
      "BTCUSDT-PERP",
      "1h",
      storage,
    );

    expect(
      readChartIntervalPreference(
        "binance-live-copy-primary",
        "BTCUSDT-PERP",
        "15m",
        storage,
      ),
    ).toBe("15m");
    expect(
      readChartIntervalPreference(
        "binance-demo-primary",
        "ETHUSDT-PERP",
        "15m",
        storage,
      ),
    ).toBe("15m");
  });

  it("falls back when stored browser state is unsupported", () => {
    const storage = memoryStorage();
    storage.setItem(
      "halpha:chart-interval:binance-demo-primary:BTCUSDT-PERP",
      "2h",
    );

    expect(
      readChartIntervalPreference(
        "binance-demo-primary",
        "BTCUSDT-PERP",
        "5m",
        storage,
      ),
    ).toBe("5m");
  });
});
