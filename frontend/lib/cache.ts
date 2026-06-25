"use client";

// Lekki cache danych po stronie przeglądarki — bez zewnętrznych bibliotek.
// Cel: przy przełączaniu zakładek liczby/wyniki pojawiają się NATYCHMIAST (z
// pamięci), a w tle są cicho odświeżane ("stale-while-revalidate"). Pamięć żyje
// w module (singleton), więc przetrwa nawigację między stronami w obrębie sesji.

import { useCallback, useEffect, useRef, useState } from "react";

type Entry = { data: unknown; ts: number };
const store = new Map<string, Entry>();

/** Unieważnia cache: bez argumentu czyści wszystko; z prefiksem — pasujące klucze.
 * Wołaj po przeliczeniu, żeby świeże liczby zastąpiły zapamiętane. */
export function invalidateCache(prefix?: string) {
  if (!prefix) {
    store.clear();
    return;
  }
  for (const k of Array.from(store.keys())) {
    if (k.startsWith(prefix)) store.delete(k);
  }
}

/**
 * Pobiera dane z cache (natychmiast, jeśli są) i odświeża w tle.
 * @param key   klucz cache (null = nie pobieraj, np. brak wybranego zadania)
 * @param fetcher  funkcja pobierająca dane
 * @param staleMs  jak długo dane są "świeże" (bez odświeżania w tle); domyślnie 60 s
 */
export function useCachedData<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  staleMs = 60_000,
) {
  const cached = key ? store.get(key) : undefined;
  const [data, setData] = useState<T | null>(cached ? (cached.data as T) : null);
  const [loading, setLoading] = useState<boolean>(!cached);
  const [error, setError] = useState<string | null>(null);

  // fetcher jest tworzony na nowo przy każdym renderze — trzymamy najnowszy w ref,
  // żeby efekt nie zapętlał się od zmiany referencji funkcji.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(
    (force: boolean) => {
      if (!key) {
        setData(null);
        setLoading(false);
        return;
      }
      const entry = store.get(key);
      if (entry) {
        setData(entry.data as T);
        setLoading(false);
      } else {
        setLoading(true);
      }
      const fresh = entry && Date.now() - entry.ts < staleMs;
      if (!force && fresh) return; // świeże → nie ruszamy backendu

      fetcherRef.current()
        .then((d) => {
          store.set(key, { data: d, ts: Date.now() });
          setData(d);
          setError(null);
        })
        .catch((e: unknown) => {
          if (!entry) setError(e instanceof Error ? e.message : "Błąd pobierania");
        })
        .finally(() => setLoading(false));
    },
    [key, staleMs],
  );

  useEffect(() => {
    run(false);
  }, [run]);

  return { data, loading, error, refresh: () => run(true) };
}
