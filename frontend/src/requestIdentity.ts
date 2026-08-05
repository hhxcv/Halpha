export type StableRequestIdentity = Readonly<{
  fingerprint: string;
  idempotencyKey: string;
}>;

type RequestIdentityStorage = Pick<
  Storage,
  "getItem" | "setItem" | "removeItem"
>;

type StoredRequestIdentity = Readonly<{
  version: 1;
  fingerprint: string;
  idempotencyKey: string;
}>;

const REQUEST_IDENTITY_STORAGE_PREFIX = "halpha.pending-request-identity.v1";

function browserSessionStorage(): RequestIdentityStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function storageKey(scope: string): string {
  return `${REQUEST_IDENTITY_STORAGE_PREFIX}:${encodeURIComponent(scope)}`;
}

function validStoredIdentity(value: unknown): value is StoredRequestIdentity {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return record.version === 1
    && typeof record.fingerprint === "string"
    && typeof record.idempotencyKey === "string"
    && record.idempotencyKey.length > 0
    && record.idempotencyKey.length <= 160
    && !/\s/u.test(record.idempotencyKey);
}

function readStoredIdentity(
  scope: string,
  storage: RequestIdentityStorage | null,
): StableRequestIdentity | null {
  if (storage === null) return null;
  try {
    const raw = storage.getItem(storageKey(scope));
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!validStoredIdentity(parsed)) return null;
    return {
      fingerprint: parsed.fingerprint,
      idempotencyKey: parsed.idempotencyKey,
    };
  } catch {
    return null;
  }
}

export function stableRequestIdentity(
  current: StableRequestIdentity | null,
  fingerprint: string,
  createKey: () => string = () => crypto.randomUUID(),
): StableRequestIdentity {
  if (current?.fingerprint === fingerprint) return current;
  return {
    fingerprint,
    idempotencyKey: createKey(),
  };
}

export function persistentRequestIdentity(
  current: StableRequestIdentity | null,
  scope: string,
  fingerprint: string,
  createKey: () => string = () => crypto.randomUUID(),
  storage: RequestIdentityStorage | null = browserSessionStorage(),
): StableRequestIdentity {
  const stored = readStoredIdentity(scope, storage);
  const identity = stableRequestIdentity(
    current?.fingerprint === fingerprint ? current : stored,
    fingerprint,
    createKey,
  );
  if (storage !== null) {
    try {
      storage.setItem(
        storageKey(scope),
        JSON.stringify({
          version: 1,
          fingerprint: identity.fingerprint,
          idempotencyKey: identity.idempotencyKey,
        } satisfies StoredRequestIdentity),
      );
    } catch {
      // A blocked session store must not prevent a mutation attempt.
    }
  }
  return identity;
}

export function clearPersistentRequestIdentity(
  scope: string,
  storage: RequestIdentityStorage | null = browserSessionStorage(),
): void {
  if (storage === null) return;
  try {
    storage.removeItem(storageKey(scope));
  } catch {
    // A blocked session store must not prevent definitive result handling.
  }
}
