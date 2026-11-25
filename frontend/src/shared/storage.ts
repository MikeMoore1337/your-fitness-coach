import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';

export function readStorage<T>(key: string, fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : (JSON.parse(value) as T);
  } catch {
    return fallback;
  }
}

export function writeStorage(key: string, value: unknown): boolean {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function removeStorage(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Storage is optional in restrictive webviews.
  }
}

export function usePersistentState<T>(
  key: string,
  initial: T | (() => T),
  enabled = true,
): [T, Dispatch<SetStateAction<T>>, (nextValue?: T) => void] {
  const resolveInitial = () => (typeof initial === 'function' ? (initial as () => T)() : initial);
  const [value, setValue] = useState<T>(() =>
    enabled ? readStorage(key, resolveInitial()) : resolveInitial(),
  );
  const skipNextWrite = useRef(false);
  const keyRef = useRef(key);
  const enabledRef = useRef(enabled);

  useEffect(() => {
    if (keyRef.current === key && enabledRef.current === enabled) return;
    keyRef.current = key;
    enabledRef.current = enabled;
    const fallback = typeof initial === 'function' ? (initial as () => T)() : initial;
    skipNextWrite.current = true;
    setValue(enabled ? readStorage(key, fallback) : fallback);
  }, [enabled, initial, key]);

  useEffect(() => {
    if (skipNextWrite.current) {
      skipNextWrite.current = false;
      return;
    }
    if (enabled) writeStorage(key, value);
  }, [enabled, key, value]);

  const clear = (nextValue?: T) => {
    if (enabled) removeStorage(key);
    if (nextValue !== undefined) {
      skipNextWrite.current = true;
      setValue(nextValue);
    }
  };
  return [value, setValue, clear];
}
