import { describe, expect, it } from "vitest";

import { cookieValue } from "./client";

describe("cookieValue", () => {
  it("returns only the requested exact cookie", () => {
    expect(cookieValue("a=1; halpha_csrf=signed%3Dtoken; x=2", "halpha_csrf")).toBe(
      "signed=token",
    );
    expect(cookieValue("halpha_csrf_extra=no", "halpha_csrf")).toBeNull();
  });
});
