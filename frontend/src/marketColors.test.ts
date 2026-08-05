import { describe, expect, it } from "vitest";

import { marketToneForDirection, marketToneForSignedValue } from "./marketColors";

describe("market color semantics", () => {
  it("maps long and short to market movement without choosing red or green", () => {
    expect(marketToneForDirection("LONG")).toBe("up");
    expect(marketToneForDirection("SHORT")).toBe("down");
    expect(marketToneForDirection("UNKNOWN")).toBeUndefined();
  });

  it("keeps zero and unknown neutral while preserving signed direction", () => {
    expect(marketToneForSignedValue("1.25")).toBe("up");
    expect(marketToneForSignedValue("-0.1")).toBe("down");
    expect(marketToneForSignedValue("0")).toBeUndefined();
    expect(marketToneForSignedValue("UNKNOWN")).toBeUndefined();
  });
});
