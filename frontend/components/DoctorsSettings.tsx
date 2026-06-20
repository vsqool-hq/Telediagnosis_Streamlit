"use client";

import { useEffect, useMemo, useState } from "react";
import { Stethoscope, Save, Loader2, CheckCircle2, Search } from "lucide-react";
import { api } from "@/lib/api";

type Doc = { name: string; key: string; excluded: boolean };

export default function DoctorsSettings() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.doctorsList()
      .then((r) => {
        setDocs(r.doctors);
        setExcluded(new Set(r.doctors.filter((d) => d.excluded).map((d) => d.key)));
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  const shown = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return f ? docs.filter((d) => d.name.toLowerCase().includes(f)) : docs;
  }, [docs, filter]);

  async function persist(next: Set<string>) {
    setSaving(true); setErr(null); setMsg(null);
    try {
      await api.setDoctorsExcluded([...next]);
      setMsg("Zapisano. Na zakładce „Rozliczenie lekarzy” kliknij „Przelicz ponownie”.");
    } catch (e: any) { setErr(e.message); } finally { setSaving(false); }
  }

  function toggle(key: string) {
    setExcluded((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      persist(next);   // auto-zapis przy każdej zmianie — nie trzeba klikać „Zapisz”
      return next;
    });
  }

  return (
    <div className="card">
      <h2 className="flex items-center gap-2 text-base font-bold">
        <Stethoscope size={18} className="text-brand-accent" /> Ustawienia lekarzy
      </h2>
      <p className="mt-1 text-[13px] leading-relaxed text-slate-400">
        Zaznacz lekarzy (z kolumny „Opisujący" w ostatnio wgranym pliku rozliczeniowym),
        których chcesz <b className="text-slate-200">wyłączyć</b> z rozliczenia lekarzy — np. rozliczanych
        osobno. Ich badania zostaną pominięte przy liczeniu stawek.
      </p>

      {loading ? (
        <div className="mt-4 flex items-center gap-2 text-slate-400"><Loader2 className="animate-spin" size={16} /> Wczytywanie lekarzy…</div>
      ) : docs.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">Brak danych — uruchom najpierw pełne rozliczenie jednostek.</p>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={15} />
              <input className="input pl-9 sm:w-64" placeholder="Szukaj lekarza…"
                value={filter} onChange={(e) => setFilter(e.target.value)} />
            </div>
            <span className="text-xs text-slate-400">Wyłączonych: {excluded.size} z {docs.length}</span>
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
                <span className={excluded.has(d.key) ? "text-slate-500 line-through" : ""}>{d.name}</span>
                {excluded.has(d.key) && <span className="pill pill-muted ml-auto">wyłączony</span>}
              </label>
            ))}
            {shown.length === 0 && <p className="px-4 py-3 text-sm text-slate-500">Brak pasujących lekarzy.</p>}
          </div>
        </>
      )}
    </div>
  );
}
