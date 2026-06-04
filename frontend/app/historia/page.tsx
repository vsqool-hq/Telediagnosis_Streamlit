"use client";

import { useEffect, useState } from "react";
import { Download, FileText, Calendar, Receipt, BookText } from "lucide-react";
import { api, Job, TrendPoint, Version } from "@/lib/api";

const MONTHS_PL = [
  "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
];

function monthLabel(dateISO: string): string {
  const d = new Date(dateISO);
  return `${MONTHS_PL[d.getMonth()]} ${d.getFullYear()}`;
}
function monthKey(dateISO: string): string {
  const d = new Date(dateISO);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

interface MonthEntry {
  key: string;
  label: string;
  point: TrendPoint;
  job?: Job;
}

export default function HistoriaPage() {
  const [entries, setEntries] = useState<MonthEntry[]>([]);
  const [cennikNames, setCennikNames] = useState<Record<string, string>>({});
  const [wzorcoweNames, setWzorcoweNames] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.trends(), api.listJobs()])
      .then(([t, jobs]) => {
        const byId = new Map(jobs.map((j) => [j.id, j]));
        // Trendy są rosnąco wg daty → ostatni wpis w miesiącu nadpisuje wcześniejsze.
        const map = new Map<string, MonthEntry>();
        for (const p of t.points) {
          const key = monthKey(p.date);
          map.set(key, { key, label: monthLabel(p.date), point: p, job: byId.get(p.job_id) });
        }
        setEntries(Array.from(map.values()).sort((a, b) => (a.key < b.key ? 1 : -1)));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoaded(true));

    api.listVersions("cennik").then((vs: Version[]) =>
      setCennikNames(Object.fromEntries(vs.map((v) => [v.id, v.original_name])))).catch(() => {});
    api.listVersions("wzorcowe").then((vs: Version[]) =>
      setWzorcoweNames(Object.fromEntries(vs.map((v) => [v.id, v.original_name])))).catch(() => {});
  }, []);

  const zl = (n: number) =>
    n.toLocaleString("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Historia rozliczeń</h1>
        <p className="text-sm text-slate-400">
          Archiwum finalnego (ostatniego) rozliczenia z każdego miesiąca wraz z plikiem źródłowym
          i użytym cennikiem. Wcześniejsze próby z danego miesiąca są zastępowane przez najnowszą.
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
        {entries.map((e, idx) => {
          const latest = idx === 0;
          const cennik = e.job?.cennik_version ? cennikNames[e.job.cennik_version] : null;
          const wzorcowe = e.job?.wzorcowe_version ? wzorcoweNames[e.job.wzorcowe_version] : null;
          const when = e.job?.finished_at || e.job?.created_at || e.point.date;
          return (
            <div key={e.key} className="card">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className={`flex h-11 w-11 items-center justify-center rounded-[13px] ${
                    latest ? "bg-brand-accent/15 text-brand-accent" : "bg-white/5 text-slate-400"}`}>
                    <Calendar size={22} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-extrabold">{e.label}</h3>
                      <span className={`pill ${latest ? "pill-ok" : "pill-muted"}`}>Finalne</span>
                    </div>
                    <p className="text-xs text-slate-400">
                      Zapisano {new Date(when).toLocaleString("pl-PL")} ·{" "}
                      {e.point.studies.toLocaleString("pl-PL")} pozycji
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-[22px] font-extrabold">{zl(e.point.revenue)}</p>
                  <p className="text-xs text-slate-400">wartość rozliczenia</p>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
                <span className="soft inline-flex items-center gap-2 px-3 py-1.5 text-xs text-slate-300">
                  <FileText size={14} className="text-slate-400" /> źródło: {e.point.label}
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
                <div className="ml-auto flex gap-2">
                  {e.job && (
                    <a className="btn-secondary px-3 py-1.5 text-xs" href={api.inputUrl(e.job.id)}>
                      <FileText size={14} /> Plik źródłowy
                    </a>
                  )}
                  <a className={`px-3 py-1.5 text-xs ${latest ? "btn-primary" : "btn-secondary"}`}
                     href={api.resultUrl(e.point.job_id)}>
                    <Download size={14} /> Pobierz wyniki
                  </a>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
