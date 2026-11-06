const LOCK_STORAGE_PREFIX = 'fit_cross_context_lock_v1_';
const DEFAULT_LEASE_MS = 30_000;
const DEFAULT_TIMEOUT_MS = 45_000;
const DEFAULT_POLL_MS = 20;

interface LockRecord {
  owner_id: string;
  ticket: number;
  expires_at: number;
}

interface ChoosingRecord {
  owner_id: string;
  expires_at: number;
}

export interface CrossContextCoordinator {
  run<T>(name: string, task: () => T | Promise<T>): Promise<T>;
}

interface CoordinatorOptions {
  storage?: Storage | null;
  nativeLocks?: LockManager | null;
  ownerId?: string;
  leaseMs?: number;
  timeoutMs?: number;
  pollMs?: number;
  requireSharedLock?: boolean;
}

function createOwnerId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `context-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function parseRecord<T extends { owner_id: string; expires_at: number }>(
  raw: string | null,
): T | null {
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<T>;
    if (
      typeof parsed.owner_id !== 'string' ||
      !parsed.owner_id ||
      typeof parsed.expires_at !== 'number' ||
      !Number.isFinite(parsed.expires_at)
    )
      return null;
    return parsed as T;
  } catch {
    return null;
  }
}

function storageEntries(storage: Storage, prefix: string): Array<[string, string]> {
  const keys = Array.from({ length: storage.length }, (_, index) => storage.key(index)).filter(
    (key): key is string => Boolean(key?.startsWith(prefix)),
  );
  const entries: Array<[string, string]> = [];
  for (const key of keys) {
    const value = storage.getItem(key);
    if (value !== null) entries.push([key, value]);
  }
  return entries;
}

function wait(delayMs: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, delayMs));
}

export function createCrossContextCoordinator(
  options: CoordinatorOptions = {},
): CrossContextCoordinator {
  let defaultStorage: Storage | null = null;
  if (options.storage === undefined) {
    try {
      defaultStorage = window.localStorage;
    } catch {
      defaultStorage = null;
    }
  }
  const storage = options.storage === undefined ? defaultStorage : options.storage;
  const configuredNativeLocks = options.nativeLocks;
  const ownerId = options.ownerId ?? createOwnerId();
  const leaseMs = options.leaseMs ?? DEFAULT_LEASE_MS;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const pollMs = options.pollMs ?? DEFAULT_POLL_MS;
  const localTails = new Map<string, Promise<void>>();

  async function runStorageLock<T>(name: string, task: () => T | Promise<T>): Promise<T> {
    if (!storage) {
      if (options.requireSharedLock) throw new Error('Общее хранилище недоступно');
      return task();
    }

    const encodedName = encodeURIComponent(name);
    const choosingPrefix = `${LOCK_STORAGE_PREFIX}${encodedName}_choosing_`;
    const ticketPrefix = `${LOCK_STORAGE_PREFIX}${encodedName}_ticket_`;
    const choosingKey = `${choosingPrefix}${ownerId}`;
    const ticketKey = `${ticketPrefix}${ownerId}`;
    const startedAt = Date.now();
    let ticket = 0;
    let acquired = false;

    const removeOwnRecord = (key: string) => {
      const record = parseRecord<LockRecord | ChoosingRecord>(storage.getItem(key));
      if (record?.owner_id === ownerId) storage.removeItem(key);
    };

    try {
      const now = Date.now();
      storage.setItem(
        choosingKey,
        JSON.stringify({ owner_id: ownerId, expires_at: now + leaseMs } satisfies ChoosingRecord),
      );
      const existingTickets = storageEntries(storage, ticketPrefix);
      for (const [key, raw] of existingTickets) {
        const record = parseRecord<LockRecord>(raw);
        if (!record || record.expires_at <= now || !Number.isInteger(record.ticket)) {
          storage.removeItem(key);
          continue;
        }
        ticket = Math.max(ticket, record.ticket);
      }
      ticket += 1;
      storage.setItem(
        ticketKey,
        JSON.stringify({
          owner_id: ownerId,
          ticket,
          expires_at: now + leaseMs,
        } satisfies LockRecord),
      );
      removeOwnRecord(choosingKey);

      while (!acquired) {
        const checkedAt = Date.now();
        if (checkedAt - startedAt >= timeoutMs) {
          throw new Error(`Не удалось дождаться cross-context lock: ${name}`);
        }

        let anotherContextIsChoosing = false;
        for (const [key, raw] of storageEntries(storage, choosingPrefix)) {
          const record = parseRecord<ChoosingRecord>(raw);
          if (!record || record.expires_at <= checkedAt) {
            storage.removeItem(key);
            continue;
          }
          if (record.owner_id !== ownerId) anotherContextIsChoosing = true;
        }

        let earlierTicketExists = false;
        for (const [key, raw] of storageEntries(storage, ticketPrefix)) {
          const record = parseRecord<LockRecord>(raw);
          if (
            !record ||
            record.expires_at <= checkedAt ||
            !Number.isInteger(record.ticket) ||
            record.ticket < 1
          ) {
            storage.removeItem(key);
            continue;
          }
          if (
            record.owner_id !== ownerId &&
            (record.ticket < ticket || (record.ticket === ticket && record.owner_id < ownerId))
          ) {
            earlierTicketExists = true;
          }
        }

        const ownTicket = parseRecord<LockRecord>(storage.getItem(ticketKey));
        if (
          ownTicket?.owner_id === ownerId &&
          ownTicket.ticket === ticket &&
          ownTicket.expires_at - checkedAt < leaseMs / 2
        ) {
          storage.setItem(
            ticketKey,
            JSON.stringify({ ...ownTicket, expires_at: checkedAt + leaseMs }),
          );
        }
        if (
          ownTicket?.owner_id === ownerId &&
          ownTicket.ticket === ticket &&
          !anotherContextIsChoosing &&
          !earlierTicketExists
        ) {
          acquired = true;
          break;
        }
        await wait(pollMs);
      }

      const heartbeat = window.setInterval(
        () => {
          try {
            const current = parseRecord<LockRecord>(storage.getItem(ticketKey));
            if (current?.owner_id !== ownerId || current.ticket !== ticket) return;
            storage.setItem(
              ticketKey,
              JSON.stringify({ ...current, expires_at: Date.now() + leaseMs }),
            );
          } catch {
            // The current task still owns the in-memory turn; the lease will expire safely.
          }
        },
        Math.max(1000, Math.floor(leaseMs / 3)),
      );
      try {
        return await task();
      } finally {
        window.clearInterval(heartbeat);
      }
    } catch (error) {
      if (!acquired && error instanceof DOMException && !options.requireSharedLock) return task();
      throw error;
    } finally {
      try {
        removeOwnRecord(choosingKey);
        removeOwnRecord(ticketKey);
      } catch {
        // Storage may become unavailable while a WebView is being torn down.
      }
    }
  }

  return {
    async run<T>(name: string, task: () => T | Promise<T>): Promise<T> {
      const previous = localTails.get(name) ?? Promise.resolve();
      let releaseTurn!: () => void;
      const current = new Promise<void>((resolve) => {
        releaseTurn = resolve;
      });
      const tail = previous.catch(() => undefined).then(() => current);
      localTails.set(name, tail);
      await previous.catch(() => undefined);
      try {
        const nativeLocks =
          configuredNativeLocks === undefined ? (navigator.locks ?? null) : configuredNativeLocks;
        if (nativeLocks?.request) return await nativeLocks.request(name, () => task());
        return await runStorageLock(name, task);
      } finally {
        releaseTurn();
        void tail.finally(() => {
          if (localTails.get(name) === tail) localTails.delete(name);
        });
      }
    },
  };
}

export const crossContextCoordinator = createCrossContextCoordinator();
