const DATABASE = 'fit_hydration_coordination_v1';
const STORE = 'revisions';
const REVISION = '_coordination_revision';
const PREVIOUS_REVISION = '_coordination_previous';
const EPOCH = '_coordination_epoch';
const EPOCH_KEY = '__epoch__';
// A synchronous cross-tab tombstone survives a failed IndexedDB epoch publication.
const RESET_MARKER_KEY = 'fit_hydration_coordination_reset_v1';
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

async function resetDatabase(retainKey: string | null, epoch: string): Promise<void> {
  if (typeof indexedDB === 'undefined') return;
  const database = await openDatabase();
  const metadata = { epoch, allowLegacy: false, retainKey };
  try {
    // Publish the invalidation before attempting to remove account metadata.
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE, 'readwrite');
      transaction.objectStore(STORE).put(metadata, EPOCH_KEY);
      transaction.oncomplete = () => resolve();
      transaction.onabort = () => reject(transaction.error);
    });
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE, 'readwrite');
      const store = transaction.objectStore(STORE);
      let failure: unknown;
      const current = store.get(EPOCH_KEY);
      const retained = retainKey ? store.get(retainKey) : null;
      current.onsuccess = () => {
        if (current.result?.epoch !== metadata.epoch) return;
        const removeOld = () => {
          try {
            store.clear();
            store.put(metadata, EPOCH_KEY);
            if (retainKey) store.put(retained?.result ?? { legacyRetained: true }, retainKey);
          } catch (error) {
            failure = error;
            transaction.abort();
          }
        };
        if (retained) retained.onsuccess = removeOld;
        else removeOld();
      };
      transaction.oncomplete = () => resolve();
      transaction.onabort = () => reject(failure ?? transaction.error);
    });
  } finally {
    database.close();
  }
}

export function resetHydrationFences(retainKey: string | null): Promise<void> {
  const epoch = randomId();
  try {
    // Publish before any asynchronous IndexedDB write: a failed put cannot
    // allow another tab to resurrect pending data cleared during logout.
    localStorage.setItem(RESET_MARKER_KEY, epoch);
  } catch {
    return Promise.reject(new Error('Не удалось защитить очистку состояния гидратации'));
  }
  cleanup = cleanup.catch(() => undefined).then(() => resetDatabase(retainKey, epoch));
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
              const stored = request.result as
                { revision?: string | null; epoch?: string; legacyRetained?: boolean } | undefined;
              const resetEpoch = localStorage.getItem(RESET_MARKER_KEY);
              let metadata = (epochRequest.result as
                { epoch: string; allowLegacy: boolean; retainKey?: string | null } | undefined) ?? {
                epoch: resetEpoch ?? randomId(),
                allowLegacy: resetEpoch === null,
              };
              if (resetEpoch !== null && metadata.epoch !== resetEpoch) {
                // Do not accept a cached pre-logout localStorage snapshot even
                // when the IndexedDB reset transaction was aborted.
                if (before !== null) {
                  result = { stale: true };
                  return;
                }
                metadata = { epoch: resetEpoch, allowLegacy: false, retainKey: null };
                store.put(metadata, EPOCH_KEY);
              } else if (!epochRequest.result) {
                store.put(metadata, EPOCH_KEY);
              }
              const currentRevision = hydrationRevision(before);
              const dataEpoch = before === null ? undefined : JSON.parse(before)[EPOCH];
              const previous = before === null ? undefined : JSON.parse(before)[PREVIOUS_REVISION];
              const expected =
                stored &&
                (stored.epoch === metadata.epoch ||
                  dataEpoch === metadata.epoch ||
                  metadata.retainKey === key)
                  ? stored
                  : undefined;
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
                store.put({ revision: currentRevision, epoch: metadata.epoch }, key);
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
                store.put({ revision, epoch: metadata.epoch }, key);
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
