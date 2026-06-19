"use client";

import { useEffect, useState } from "react";
import { Scale, Play, Loader2, AlertTriangle, Download, RefreshCw } from "lucide-react";
import { api, Job, DoctorComparison } from "@/lib/api";

const zl = (n: number) =>
  n.toLocaleString("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });

export default function PorownaniePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState<string>("");
  const [result, setResult] = useState<DoctorComparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listJobs().then((all) => {
      const done = all.filter((j) => j.status === "done" && j.mode === "full");
      setJobs(done);
      if (done.length) setJobId(done[0].id);
    }).catch((e) => setError(e.message));
  }, []);

  // Wczytaj zapisane porównanie po wyborze zadania (bez liczenia).
  useEffect(() => {
    if (!jobId) { setResult(null); return; }
    setResult(null); setError(null);
    api.doctorsCompare(jobId, { peek: true })
      .then((r) => setResult(r && (r as any).reason === "not_computed" ? null : r))
      .catch(() => {});
  }, [jobId]);

  async function run(recompute = false) {
    if (!jobId) return;
    setBusy(true); setError(null); setResult(null);
    try {
      setResult(await api.doctorsCompare(jobId, { recompute }));
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  const t = result?.totals;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Porównanie lekarze ↔ jednostki</h1>
        <p className="text-sm text-slate-400">
          Marża per kategoria badań: przychód z cennika jednostek minus koszt z cennika lekarzy,
          policzone na tych samych zweryfikowanych badaniach.
        </p>
      </header>

      <div className="card flex flex-wrap items-end gap-3">
        <label className="space-y-1.5">
          <span className="text-[13px] font-semibold text-slate-200">Zadanie (pełne rozliczenie)</span>
          <select className="input min-w-[280px]" value={jobId} onChange={(e) => setJobId(e.target.value)}>
            {jobs.length === 0 && <option value="">brak ukończonych rozliczeń</option>}
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {new Date(j.created_at).toLocaleString("pl-PL")} · {j.input_name}
              </option>
            ))}
          </select>
        </label>
        <button className="btn-primary" disabled={!jobId || busy} onClick={() => run(false)}>
          {busy ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} />}
          Policz porównanie
        </button>
        {result && !result.empty && (
          <>
            <a className="btn-secondary" href={api.doctorsCompareDownloadUrl(jobId)}>
              <Download size={18} /> Pobierz Excel
            </a>
            <button className="btn-secondary" disabled={busy} onClick={() => run(true)}>
              <RefreshCw size={18} /> Przelicz ponownie
            </button>
            {result.computed_at && (
              <span className="text-xs text-slate-400">
                Zapisano: {new Date(result.computed_at).toLocaleString("pl-PL")}
              </span>
            )}
          </>
        )}
      </div>

      {error && <div className="card border-red-500/40 text-red-300">{error}</div>}

      {result?.empty && (
        <div className="card text-amber-300"><AlertTriangle className="mb-1 inline" size={16} /> {result.reason}</div>
      )}

      {result && !result.empty && t && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="card"><p className="text-sm text-slate-400">Przychód (jednostki)</p><p className="mt-2 text-2xl font-extrabold">{zl(t.przychod_jednostki)}</p></div>
            <div className="card"><p className="text-sm text-slate-400">Koszt (lekarze)</p><p className="mt-2 text-2xl font-extrabold">{zl(t.koszt_lekarzy)}</p></div>
            <div className="card border-brand-accent/40"><p className="text-sm text-slate-400">Marża</p><p className="mt-2 text-2xl font-extrabold text-brand-accent2">{zl(t.marza)}</p></div>
          </div>
          {t.studies_without_category > 0 && (
            <p className="text-[13px] text-amber-300">
              <AlertTriangle className="mb-0.5 inline" size={14} /> {t.studies_without_category} badań bez kategorii lekarskiej (pominięte w marży) — uzupełnij słownik.
            </p>
          )}

          <div className="card">
            <h2 className="mb-3 text-base font-bold">Marża per kategoria</h2>
            <div className="max-h-[28rem] overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-brand-surface text-slate-400">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs uppercase">Modalność</th>
                    <th className="px-3 py-2 text-left text-xs uppercase">Kategoria</th>
                    <th className="px-3 py-2 text-right text-xs uppercase">Ilość</th>
                    <th className="px-3 py-2 text-right text-xs uppercase">Jednostki</th>
                    <th className="px-3 py-2 text-right text-xs uppercase">Lekarze</th>
                    <th className="px-3 py-2 text-right text-xs uppercase">Marża</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows!.map((r, i) => (
                    <tr key={i} className="border-t border-white/10">
                      <td className="px-3 py-2 text-slate-400">{r["Modalność"]}</td>
                      <td className="px-3 py-2">{r.kategoria}</td>
                      <td className="px-3 py-2 text-right text-slate-400">{r.ilosc}</td>
                      <td className="px-3 py-2 text-right">{zl(r.przychod_jednostki)}</td>
                      <td className="px-3 py-2 text-right">{zl(r.koszt_lekarzy)}</td>
                      <td className={`px-3 py-2 text-right font-semibold ${r.marza >= 0 ? "text-brand-accent2" : "text-red-300"}`}>{zl(r.marza)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
