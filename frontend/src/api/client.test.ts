import { describe, expect, it } from "vitest";

import {
  ApiFailure,
  cookieValue,
  csrfCookieNameForLocation,
  isUnknownMutationResult,
} from "./client";

describe("cookieValue", () => {
  it("returns only the requested exact cookie", () => {
    expect(cookieValue(
      "a=1; halpha_csrf_8765=signed%3Dtoken; x=2",
      "halpha_csrf_8765",
    )).toBe("signed=token");
    expect(cookieValue(
      "halpha_csrf_8765_extra=no",
      "halpha_csrf_8765",
    )).toBeNull();
  });
});

describe("csrfCookieNameForLocation", () => {
  it("scopes the browser CSRF token by the current App port", () => {
    expect(csrfCookieNameForLocation({
      protocol: "http:",
      port: "8765",
    })).toBe("halpha_csrf_8765");
    expect(csrfCookieNameForLocation({
      protocol: "http:",
      port: "",
    })).toBe("halpha_csrf_80");
    expect(csrfCookieNameForLocation({
      protocol: "https:",
      port: "",
    })).toBe("halpha_csrf_443");
  });
});

describe("isUnknownMutationResult", () => {
  it("keeps transport and server failures on the original request identity", () => {
    expect(isUnknownMutationResult(new TypeError("network lost"))).toBe(true);
    expect(isUnknownMutationResult(new ApiFailure(201, "PLAN_CREATE_FAILED")))
      .toBe(true);
    expect(isUnknownMutationResult(new ApiFailure(408, "REQUEST_TIMEOUT"))).toBe(true);
    expect(isUnknownMutationResult(new ApiFailure(503, "SERVICE_UNAVAILABLE"))).toBe(true);
  });

  it("treats an explicit client rejection as a completed attempt", () => {
    expect(isUnknownMutationResult(new ApiFailure(409, "PLAN_VERSION_CONFLICT")))
      .toBe(false);
  });
});
