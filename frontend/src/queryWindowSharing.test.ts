import { describe, expect, it } from "vitest";

import { queryPollingScope } from "./QueryPollingCoordinator";

describe("cross-window query coordination", () => {
  it("shares leadership only between windows on the same business page", () => {
    expect(queryPollingScope("/plans")).toBe(queryPollingScope("/plans/"));
    expect(queryPollingScope("/activations/one")).not.toBe(
      queryPollingScope("/activations/two"),
    );
    expect(queryPollingScope("/plans/new?mode=direct")).not.toBe(
      queryPollingScope("/plans/new?copyFrom=one"),
    );
  });

  it("keeps the root scope stable", () => {
    expect(queryPollingScope("/")).toBe(queryPollingScope(""));
  });
});
