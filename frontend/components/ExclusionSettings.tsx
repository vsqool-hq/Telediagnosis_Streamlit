"use client";

// Wspólna sekcja „wyłączanie z rozliczenia" (lekarze / jednostki): lista z
// wyszukiwarką, auto-zapis przy zmianie, cache listy (zestaw jest stały dla
// wgranego pliku — czytamy raz, nie przy każdym wejściu na Ustawienia).
import { useEffect, useMemo, useState } from "react";
import { Save, Loader2, CheckCircle2, Search } from "lucide-react";
import { useCachedData, invalidateCache } from "@/lib/cache";

type Item = { name: string; key: string; excluded: boolean };

export default function ExclusionSettings({
  icon, title, description, cacheKey, load, save, savedMsg, searchPlaceholder, emptyMsg,
  excludedPill = "wyłączone", mode = "exclude", counterLabel = "Wyłączonych",
}: {
  icon: React.ReactNode;
  title: string;
  description: React.ReactNode;
  cacheKey: string;
  load: () => Promise<Item[]>;
  save: (keys: string[]) => Promise<unknown>;
  savedMsg: string;
  searchPlaceholder: string;
  emptyMsg: string;
  excludedPill?: string;
  // "exclude" (zaznaczone = wyłączone, przekreślone) | "include" (zaznaczone = włączone)
  mode?: "exclude" | "include";
  counterLabel?: string;
}) {
  const isInclude = mode === "include";
  // Lista jest stała per wgrany plik → długi TTL; backend i tak trzyma ją w cache.
  const { data: items, loading, error } = useCachedData<Item[]>(cacheKey, load, 600_000);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (items) setExcluded(new Set(items.filter((d) => d.excluded).map((d) => d.key)));
  }, [items]);

  const shown = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const all = items ?? [];
    return f ? all.filter((d) => d.name.toLowerCase().includes(f)) : all;
  }, [items, filter]);

  async function persist(next: Set<string>) {
    setSaving(true); setErr(null); setMsg(null);
    try {
      await save([...next]);
      setMsg(savedMsg);
      invalidateCache(cacheKey);   // świeże flagi przy następnym wejściu
    } catch (e: any) { setErr(e.message); } finally { setSaving(false); }
  }

  function toggle(key: string) {
    setExcluded((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      persist(next);   // auto-zapis przy każdej zmianie — nie trzeba klikać „Zapisz"
      return next;
    });
  }

  return (
    <div className="card">
      <h2 className="flex items-center gap-2 text-base font-bold">{icon} {title}</h2>
      <p className="mt-1 text-[13px] leading-relaxed text-slate-400">{description}</p>

      {loading && !items ? (
        <div className="mt-4 flex items-center gap-2 text-slate-400"><Loader2 className="animate-spin" size={16} /> Wczytywanie…</div>
      ) : !items || items.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">{error ?? emptyMsg}</p>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={15} />
              <input className="input pl-9 sm:w-64" placeholder={searchPlaceholder}
                value={filter} onChange={(e) => setFilter(e.target.value)} />
            </div>
            <span className="text-xs text-slate-400">{counterLabel}: {excluded.size} z {items.length}</span>
            <span className="ml-auto flex items-center gap-1.5 text-xs text-slate-400">
              {saving
                ? <><Loader2 className="animate-spin" size={14} /> Zapisywanie…</>
                : <><Save size={14} /> Zmiany zapisują się automatycznie</>}
            </span>
          </div>

          {msg && <div className="mt-3 flex items-center gap-2 text-sm text-brand-accent2"><CheckCircle2 size={16} /> {msg}</div>}
          {err && <div className="mt-3 text-sm text-red-300">{err}</div>}

          <div className="mt-3 max-h-80 overflow-auto rounded-xl border border-white/10">
            {shown.map((d) => (
              <label key={d.key}
                className="flex cursor-pointer items-center gap-3 border-b border-white/5 px-4 py-2 text-sm last:border-0 hover:bg-white/[0.03]">
                <input type="checkbox" className="h-4 w-4 accent-brand-accent"
                  checked={excluded.has(d.key)} onChange={() => toggle(d.key)} />
                <span className={excluded.has(d.key) && !isInclude ? "text-slate-500 line-through" : ""}>{d.name}</span>
                {excluded.has(d.key) && (
                  <span className={`pill ml-auto ${isInclude ? "pill-ok" : "pill-muted"}`}>{excludedPill}</span>
                )}
              </label>
            ))}
            {shown.length === 0 && <p className="px-4 py-3 text-sm text-slate-500">Brak pasujących pozycji.</p>}
          </div>
        </>
      )}
    </div>
  );
}
