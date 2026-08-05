import { describe, expect, it, vi } from "vitest";

import {
  clearPersistentRequestIdentity,
  persistentRequestIdentity,
  stableRequestIdentity,
} from "./requestIdentity";

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
}

describe("stableRequestIdentity", () => {
  it("reuses one key while the user intent fingerprint is unchanged", () => {
    const createKey = vi.fn()
      .mockReturnValueOnce("request-1")
      .mockReturnValueOnce("request-2");

    const first = stableRequestIdentity(null, "same-intent", createKey);
    const retry = stableRequestIdentity(first, "same-intent", createKey);

    expect(retry).toBe(first);
    expect(retry.idempotencyKey).toBe("request-1");
    expect(createKey).toHaveBeenCalledTimes(1);
  });

  it("creates a new key when the user intent fingerprint changes", () => {
    const createKey = vi.fn()
      .mockReturnValueOnce("request-1")
      .mockReturnValueOnce("request-2");

    const first = stableRequestIdentity(null, "intent-a", createKey);
    const next = stableRequestIdentity(first, "intent-b", createKey);

    expect(next.idempotencyKey).toBe("request-2");
    expect(createKey).toHaveBeenCalledTimes(2);
  });

  it("reuses one pending key after a page reload in the same environment operation", () => {
    const storage = memoryStorage();
    const createKey = vi.fn()
      .mockReturnValueOnce("request-1")
      .mockReturnValueOnce("request-2");

    const first = persistentRequestIdentity(
      null,
      "DEMO:demo-main:CREATE_PLAN",
      "same-intent",
      createKey,
      storage,
    );
    const afterReload = persistentRequestIdentity(
      null,
      "DEMO:demo-main:CREATE_PLAN",
      "same-intent",
      createKey,
      storage,
    );

    expect(afterReload).toEqual(first);
    expect(createKey).toHaveBeenCalledTimes(1);
  });

  it("isolates environments and operations and clears definitive results", () => {
    const storage = memoryStorage();
    const createKey = vi.fn()
      .mockReturnValueOnce("request-1")
      .mockReturnValueOnce("request-2")
      .mockReturnValueOnce("request-3");

    persistentRequestIdentity(
      null,
      "DEMO:demo-main:CREATE_PLAN",
      "same-intent",
      createKey,
      storage,
    );
    const live = persistentRequestIdentity(
      null,
      "LIVE:live-main:CREATE_PLAN",
      "same-intent",
      createKey,
      storage,
    );
    clearPersistentRequestIdentity(
      "DEMO:demo-main:CREATE_PLAN",
      storage,
    );
    const afterClear = persistentRequestIdentity(
      null,
      "DEMO:demo-main:CREATE_PLAN",
      "same-intent",
      createKey,
      storage,
    );

    expect(live.idempotencyKey).toBe("request-2");
    expect(afterClear.idempotencyKey).toBe("request-3");
  });

  it("recovers from corrupted or unavailable session storage", () => {
    const corrupted = memoryStorage();
    corrupted.setItem(
      "halpha.pending-request-identity.v1:DEMO%3Ademo-main%3ACREATE_PLAN",
      "{broken",
    );
    const unavailable = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };

    expect(persistentRequestIdentity(
      null,
      "DEMO:demo-main:CREATE_PLAN",
      "intent",
      () => "request-corrupt",
      corrupted,
    ).idempotencyKey).toBe("request-corrupt");
    expect(persistentRequestIdentity(
      null,
      "DEMO:demo-main:CREATE_PLAN",
      "intent",
      () => "request-blocked",
      unavailable,
    ).idempotencyKey).toBe("request-blocked");
    expect(() => clearPersistentRequestIdentity(
      "DEMO:demo-main:CREATE_PLAN",
      unavailable,
    )).not.toThrow();
  });
});
