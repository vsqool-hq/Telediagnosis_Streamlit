"use client";

import { useEffect, useState } from "react";
import { Stethoscope, Play, Loader2, AlertTriangle, CheckCircle2, Download, RefreshCw } from "lucide-react";
import { api, Job, DoctorBilling, DoctorCoverage } from "@/lib/api";

const zl = (n: number) =>
  n.toLocaleString("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });

export default function RozliczenieLekarzyPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState<string>("");
  const [coverage, setCoverage] = useState<DoctorCoverage | null>(null);
  const [result, setResult] = useState<DoctorBilling | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.doctorsCoverage().then(setCoverage).catch(() => {});
    api.listJobs().then((all) => {
      const done = all.filter((j) => j.status === "done" && j.mode === "full");
      setJobs(done);
      if (done.length) setJobId(done[0].id);
    }).catch((e) => setError(e.message));
  }, []);

  // Po wyborze zadania wczytaj ZAPISANY wynik (bez liczenia) — dzięki temu po
  // powrocie na zakładkę rozliczenie jest od razu, nie znika.
  useEffect(() => {
    if (!jobId) { setResult(null); return; }
    setResult(null); setError(null);
    api.doctorsBilling(jobId, { peek: true })
      .then((r) => setResult(r && (r as any).reason === "not_computed" ? null : r))
      .catch(() => {});
  }, [jobId]);

  async function run(recompute = false) {
    if (!jobId) return;
    setBusy(true); setError(null); setResult(null);
    try {
      setResult(await api.doctorsBilling(jobId, { recompute }));
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Rozliczenie lekarzy</h1>
        <p className="text-sm text-slate-400">
          Per lekarz (kolumna „Opisujący"), na podstawie tych samych zweryfikowanych badań co
          rozliczenie jednostek. Kategoria badania pobierana ze słownika („Rodzaj procedury lekarz"),
          stawka z aktywnego cennika lekarzy.
        </p>
      </header>

      {coverage && (
        <div className={`card flex flex-wrap items-center gap-3 ${coverage.ready ? "border-brand-accent/40" : "border-amber-400/40"}`}>
          {coverage.ready
            ? <CheckCircle2 className="text-brand-accent2" size={20} />
            : <AlertTriangle className="text-amber-300" size={20} />}
          <div className="text-sm">
            <span className="font-semibold">{coverage.ready ? "Moduł gotowy." : "Moduł nie jest jeszcze gotowy."}</span>{" "}
            Cennik lekarzy: {coverage.doctor_cennik ? `${coverage.doctor_cennik.doctors} lekarzy / ${coverage.doctor_cennik.rows} stawek` : "brak aktywnego"}.{" "}
            Słownik „Rodzaj procedury lekarz": {coverage.slownik_lekarz_filled}/{coverage.slownik_total} wypełnione.
          </div>
        </div>
      )}

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
          Policz rozliczenie lekarzy
        </button>
        {result && !result.empty && (
          <>
            <a className="btn-secondary" href={api.doctorsBillingDownloadUrl(jobId)}>
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
        <div className="card text-amber-300">
          <AlertTriangle className="mb-1 inline" size={16} /> {result.reason}
        </div>
      )}

      {result && !result.empty && result.validation && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="card"><p className="text-sm text-slate-400">Wartość dla lekarzy</p><p className="mt-2 text-2xl font-extrabold">{zl(result.validation.total_value)}</p></div>
            <div className="card"><p className="text-sm text-slate-400">Lekarzy</p><p className="mt-2 text-2xl font-extrabold">{result.validation.n_doctors}</p></div>
            <div className="card"><p className="text-sm text-slate-400">Wycenione badania</p><p className="mt-2 text-2xl font-extrabold">{result.validation.priced_studies}/{result.validation.total_studies}</p></div>
            <div className="card"><p className="text-sm text-slate-400">Bez kategorii</p><p className="mt-2 text-2xl font-extrabold text-amber-300">{result.validation.studies_without_category}</p></div>
          </div>

          {(result.validation.doctors_unmatched.length > 0 || result.validation.pairs_without_price.length > 0) && (
            <div className="card space-y-3 border-amber-400/30">
              <h2 className="flex items-center gap-2 text-base font-bold text-amber-300"><AlertTriangle size={18} /> Niedopasowania (do przeglądu)</h2>
              {result.validation.doctors_unmatched.length > 0 && (
                <p className="text-[13px] text-slate-300"><b>Lekarze bez stawki w cenniku ({result.validation.doctors_unmatched.length}):</b> {result.validation.doctors_unmatched.join(", ")}</p>
              )}
              {result.validation.pairs_without_price.length > 0 && (
                <div className="text-[13px] text-slate-300">
                  <b>Pary lekarz+kategoria bez stawki ({result.validation.pairs_without_price.length}):</b>
                  <div className="mt-1 max-h-40 overflow-auto">
                    {result.validation.pairs_without_price.map((p, i) => (
                      <div key={i} className="text-slate-400">{p._lek_disp} — {p._kategoria} ({p.n})</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="card">
            <h2 className="mb-3 text-base font-bold">Rozliczenie per lekarz</h2>
            <div className="max-h-[28rem] overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-brand-surface text-slate-400">
                  <tr><th className="px-3 py-2 text-left text-xs uppercase">Lekarz</th><th className="px-3 py-2 text-right text-xs uppercase">Badania</th><th className="px-3 py-2 text-right text-xs uppercase">Wartość</th></tr>
                </thead>
                <tbody>
                  {result.by_doctor!.map((d, i) => (
                    <tr key={i} className="border-t border-white/10">
                      <td className="px-3 py-2">{d.lekarz}</td>
                      <td className="px-3 py-2 text-right text-slate-400">{d.ilosc}</td>
                      <td className="px-3 py-2 text-right font-semibold">{zl(d.wartosc)}</td>
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
