"use client";

import { useEffect, useState } from "react";
import { Download, FileText, Calendar, Receipt, BookText } from "lucide-react";
import { api, Job, Version } from "@/lib/api";

const MONTHS_PL = [
  "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
];
const monthLabel = (iso: string) => { const d = new Date(iso); return `${MONTHS_PL[d.getMonth()]} ${d.getFullYear()}`; };
const monthKey = (iso: string) => { const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };

export default function HistoriaPage() {
  const [entries, setEntries] = useState<Job[]>([]);
  const [cennikNames, setCennikNames] = useState<Record<string, string>>({});
  const [wzorcoweNames, setWzorcoweNames] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Same metadane z bazy — bez liczenia przychodu (natychmiast).
    api.listJobs()
      .then((jobs) => {
        const done = jobs.filter((j) => j.status === "done" && j.mode === "full");
        // Lista z bazy jest malejąco wg daty → pierwszy w miesiącu = najnowszy (finalny).
        const map = new Map<string, Job>();
        for (const j of done) {
          const k = monthKey(j.finished_at || j.created_at);
          if (!map.has(k)) map.set(k, j);
        }
        setEntries(Array.from(map.values()).sort((a, b) =>
          monthKey(b.finished_at || b.created_at).localeCompare(monthKey(a.finished_at || a.created_at))));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoaded(true));

    api.listVersions("cennik").then((vs: Version[]) =>
      setCennikNames(Object.fromEntries(vs.map((v) => [v.id, v.original_name])))).catch(() => {});
    api.listVersions("wzorcowe").then((vs: Version[]) =>
      setWzorcoweNames(Object.fromEntries(vs.map((v) => [v.id, v.original_name])))).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Historia rozliczeń</h1>
        <p className="text-sm text-slate-400">
          Finalne (ostatnie) rozliczenie z każdego miesiąca: użyte pliki i wyniki do pobrania.
        </p>
      </header>

      {error && <div className="card border-red-500/40 text-red-300">{error}</div>}

      {loaded && entries.length === 0 && (
        <div className="card text-slate-400">
          Brak zarchiwizowanych rozliczeń. Uruchom pełne rozliczenie w zakładce{" "}
          <a href="/rozliczenie" className="text-brand-accent underline">Rozliczenie</a>.
        </div>
      )}

      <div className="space-y-4">
        {entries.map((j, idx) => {
          const latest = idx === 0;
          const cennik = j.cennik_version ? cennikNames[j.cennik_version] : null;
          const wzorcowe = j.wzorcowe_version ? wzorcoweNames[j.wzorcowe_version] : null;
          const when = j.finished_at || j.created_at;
          return (
            <div key={j.id} className="card">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className={`flex h-11 w-11 items-center justify-center rounded-[13px] ${
                    latest ? "bg-brand-accent/15 text-brand-accent" : "bg-white/5 text-slate-400"}`}>
                    <Calendar size={22} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-extrabold">{monthLabel(when)}</h3>
                      <span className={`pill ${latest ? "pill-ok" : "pill-muted"}`}>Finalne</span>
                    </div>
                    <p className="text-xs text-slate-400">Zapisano {new Date(when).toLocaleString("pl-PL")}</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <a className="btn-secondary px-3 py-1.5 text-xs" href={api.inputUrl(j.id)}>
                    <FileText size={14} /> Plik źródłowy
                  </a>
                  <a className="btn-primary px-3 py-1.5 text-xs" href={api.resultUrl(j.id)}>
                    <Download size={14} /> Pobierz wyniki
                  </a>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
                <span className="soft inline-flex items-center gap-2 px-3 py-1.5 text-xs text-slate-300">
                  <FileText size={14} className="text-slate-400" /> źródło: {j.input_name}
                </span>
                {cennik && (
                  <span className="soft inline-flex items-center gap-2 px-3 py-1.5 text-xs text-slate-300">
                    <Receipt size={14} className="text-slate-400" /> cennik: {cennik}
                  </span>
                )}
                {wzorcowe && (
                  <span className="soft inline-flex items-center gap-2 px-3 py-1.5 text-xs text-slate-300">
                    <BookText size={14} className="text-slate-400" /> słownik: {wzorcowe}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
