import { describe, expect, it } from "vitest";

import { formatUtc, shortDigest } from "./format";

describe("deterministic workbench formatting", () => {
  it("keeps UTC and unknown explicit", () => {
    expect(formatUtc("2026-07-17T00:00:00Z")).toBe("2026-07-17 00:00:00 UTC");
    expect(formatUtc(null)).toBe("UNKNOWN");
    expect(formatUtc("not-a-date")).toBe("UNKNOWN");
  });

  it("shortens digests without implying equality", () => {
    expect(shortDigest("0123456789abcdef0123456789abcdef")).toBe("0123456789ab…cdef");
    expect(shortDigest(null)).toBe("NOT BOUND");
  });
});
