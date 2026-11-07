const DATABASE = 'fit_hydration_coordination_v1';
const STORE = 'revisions';
const REVISION = '_coordination_revision';
const PREVIOUS_REVISION = '_coordination_previous';
const EPOCH = '_coordination_epoch';
const EPOCH_KEY = '__epoch__';
const TIMEOUT_MS = 45_000;
let cleanup = Promise.resolve();

function randomId(): string {
  return (
    crypto.randomUUID?.() ??
    Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join('')
  );
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      reject(new Error('Не удалось открыть общее хранилище'));
    }, TIMEOUT_MS);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onerror = () => {
      window.clearTimeout(timeout);
      reject(request.error ?? new Error('Общее хранилище недоступно'));
    };
    request.onsuccess = () => {
      window.clearTimeout(timeout);
      if (timedOut) request.result.close();
      else resolve(request.result);
    };
  });
}

export function hydrationRevision(raw: string | null): string | null {
  if (raw === null) return null;
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Некорректное хранилище');
  const revision = (value as Record<string, unknown>)[REVISION];
  if (revision === undefined) return null;
  if (typeof revision !== 'string' || !revision) throw new Error('Некорректное хранилище');
  return revision;
}

async function resetDatabase(retainKey: string | null): Promise<void> {
  if (typeof indexedDB === 'undefined') return;
  const database = await openDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE, 'readwrite');
      const store = transaction.objectStore(STORE);
      const reset = (retained?: unknown) => {
        store.clear();
        store.put({ epoch: randomId(), allowLegacy: false }, EPOCH_KEY);
        if (retainKey) store.put(retained ?? { legacyRetained: true }, retainKey);
      };
      if (retainKey) {
        const request = store.get(retainKey);
        request.onsuccess = () => reset(request.result);
      } else reset();
      transaction.oncomplete = () => resolve();
      transaction.onabort = () => reject(transaction.error);
    });
  } finally {
    database.close();
  }
}

export function resetHydrationFences(retainKey: string | null): Promise<void> {
  cleanup = cleanup.catch(() => undefined).then(() => resetDatabase(retainKey));
  return cleanup;
}

export async function withHydrationFence<T>(key: string, task: () => T): Promise<T> {
  await cleanup;
  if (typeof indexedDB === 'undefined') throw new Error('Общее хранилище недоступно');
  const database = await openDatabase();
  const startedAt = Date.now();
  try {
    while (Date.now() - startedAt < TIMEOUT_MS) {
      const attempt = await new Promise<{ stale: true } | { stale: false; value: T }>(
        (resolve, reject) => {
          const transaction = database.transaction(STORE, 'readwrite');
          const store = transaction.objectStore(STORE);
          const epochRequest = store.get(EPOCH_KEY);
          const request = store.get(key);
          let result: { stale: true } | { stale: false; value: T };
          let failure: unknown;
          const timeout = window.setTimeout(
            () => {
              failure = new Error('Не удалось дождаться общего состояния гидратации');
              transaction.abort();
            },
            Math.max(1, TIMEOUT_MS - (Date.now() - startedAt)),
          );
          request.onsuccess = () => {
            try {
              const before = localStorage.getItem(key);
              const expected = request.result as
                { revision?: string | null; legacyRetained?: boolean } | undefined;
              const metadata = (epochRequest.result as
                { epoch: string; allowLegacy: boolean } | undefined) ?? {
                epoch: randomId(),
                allowLegacy: true,
              };
              if (!epochRequest.result) store.put(metadata, EPOCH_KEY);
              const currentRevision = hydrationRevision(before);
              const dataEpoch = before === null ? undefined : JSON.parse(before)[EPOCH];
              const previous = before === null ? undefined : JSON.parse(before)[PREVIOUS_REVISION];
              const retained =
                expected &&
                ((currentRevision &&
                  (expected.revision === currentRevision || previous === expected.revision)) ||
                  (expected.legacyRetained && !currentRevision));
              if (
                before !== null &&
                dataEpoch !== metadata.epoch &&
                !retained &&
                !(dataEpoch === undefined && !expected && metadata.allowLegacy)
              ) {
                result = { stale: true };
                return;
              }
              if (
                expected &&
                !expected.legacyRetained &&
                (expected.revision !== currentRevision || (before !== null && !currentRevision))
              ) {
                if (!currentRevision || previous !== expected.revision) {
                  result = { stale: true };
                  return;
                }
                // A local write can survive an aborted IndexedDB transaction.
                store.put({ revision: currentRevision }, key);
              }
              const value = task();
              if (value && typeof (value as { then?: unknown }).then === 'function')
                throw new Error('Операция с общим хранилищем должна быть синхронной');
              const after = localStorage.getItem(key);
              if (after !== before || !expected || dataEpoch !== metadata.epoch) {
                const data = after === null ? { entries: {}, confirmed: [] } : JSON.parse(after);
                const revision = randomId();
                localStorage.setItem(
                  key,
                  JSON.stringify({
                    ...data,
                    [REVISION]: revision,
                    [PREVIOUS_REVISION]: currentRevision,
                    [EPOCH]: metadata.epoch,
                  }),
                );
                store.put({ revision }, key);
              }
              result = { stale: false, value };
            } catch (error) {
              failure = error;
              transaction.abort();
            }
          };
          transaction.oncomplete = () => {
            window.clearTimeout(timeout);
            resolve(result);
          };
          transaction.onabort = () => {
            window.clearTimeout(timeout);
            reject(failure ?? transaction.error);
          };
        },
      );
      if (!attempt.stale) return attempt.value;
      await new Promise((resolve) => window.setTimeout(resolve, 20));
    }
    throw new Error('Не удалось дождаться общего состояния гидратации');
  } finally {
    database.close();
  }
}
