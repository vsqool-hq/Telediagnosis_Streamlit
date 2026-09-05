"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Stethoscope, Play, Loader2, AlertTriangle, CheckCircle2, Download, RefreshCw, UploadCloud } from "lucide-react";
import { api, DoctorMonth, DoctorBilling, DoctorCoverage } from "@/lib/api";
import { useCachedData } from "@/lib/cache";
import { useAuth } from "@/lib/auth";

const zl = (n: number) =>
  n.toLocaleString("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });

const MONTHS_PL = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"];
const periodLabel = (p: string) =>
  /^\d{4}-\d{2}$/.test(p) ? `${MONTHS_PL[parseInt(p.slice(5)) - 1]} ${p.slice(0, 4)}` : p;

export default function RozliczenieLekarzyPage() {
  const { isAdmin } = useAuth();
  const [jobId, setJobId] = useState<string>("");
  const [result, setResult] = useState<DoctorBilling | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Aktywne odpytywanie (gdy liczenie biegnie w tle) — id interwału do sprzątania.
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cache: coverage i lista miesięcy pojawiają się od razu po powrocie na zakładkę.
  const { data: coverage } = useCachedData<DoctorCoverage>("doctorsCoverage", () => api.doctorsCoverage());
  // Do wyboru: MIESIĄCE (unikalne pliki miesięczne — ostatnie przeliczenie miesiąca),
  // a nie surowe zadania mnożone przez kolejne przeliczenia.
  const { data: monthsData, refresh: refreshMonths } = useCachedData<{ months: DoctorMonth[] }>(
    "doctorsMonths", () => api.doctorsMonths());
  const months = useMemo(() => monthsData?.months ?? [], [monthsData]);

  // Trwa złożony przepływ „Nowy plik → tylko lekarze" (wgranie → Etap 1 → liczenie).
  // W jego trakcie zmiana jobId jest NASZA, więc efekt poniżej nie może go przerwać.
  const flowRef = useRef(false);

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }
  useEffect(() => stopPolling, []);

  // Domyślnie wybierz najnowszy miesiąc, gdy lista się pojawi.
  useEffect(() => {
    if (!jobId && months.length) setJobId(months[0].job_id);
  }, [months, jobId]);

  // Po wyborze zadania: zatrzymaj ewentualne odpytywanie i wczytaj ZAPISANY wynik
  // (bez liczenia) — dzięki temu po powrocie na zakładkę rozliczenie jest od razu.
  useEffect(() => {
    if (flowRef.current) return;   // wybór ustawiony przez uploadAndRun — nie przerywaj
    stopPolling(); setBusy(false);
    if (!jobId) { setResult(null); return; }
    setResult(null); setError(null);
    api.doctorsBilling(jobId, { peek: true })
      .then((r) => setResult(r && (r as any).reason === "not_computed" ? null : r))
      .catch(() => {});
  }, [jobId]);

  // Liczenie biegnie w OSOBNYM procesie (jak główne rozliczenie). Start → odpytywanie
  // o status → po „done" wczytanie zapisanego wyniku. Brak długiego żądania = brak
  // „failed to fetch" przy większych danych / scale-to-zero.
  async function run(recompute = false, jid: string = jobId) {
    if (!jid) return;
    stopPolling();
    setBusy(true); setError(null); setResult(null);
    try {
      const started = await api.doctorsBillingRun(jid, recompute);
      if (started.status === "done") {
        const r = await api.doctorsBilling(jid, { peek: true });
        setResult(r && (r as any).reason === "not_computed" ? null : r);
        setBusy(false);
        return;
      }
      const id = jid;
      pollRef.current = setInterval(async () => {
        try {
          const st = await api.doctorsBillingStatus(id);
          if (st.status === "running") return;
          stopPolling();
          if (st.status === "error") { setError(st.error || "Liczenie nie powiodło się."); setBusy(false); return; }
          const r = await api.doctorsBilling(id, { peek: true });
          setResult(r && (r as any).reason === "not_computed" ? null : r);
          setBusy(false);
        } catch {
          // Pojedynczy nieudany ping nie przerywa — maszyna mogła się budzić.
        }
      }, 2500);
    } catch (e: any) {
      stopPolling(); setError(e.message); setBusy(false);
    }
  }

  // „Tylko lekarze" na NOWO wgranym pliku: tworzymy zadanie w trybie „doctors"
  // (Etap 1 = weryfikacja, bez wyceny jednostek), czekamy aż się zweryfikuje,
  // po czym liczymy rozliczenie lekarzy na tym zadaniu.
  async function uploadAndRun(file: File) {
    stopPolling();
    flowRef.current = true;
    setBusy(true); setError(null); setResult(null);
    try {
      const job = await api.createJob(file, "doctors");
      setJobId(job.id);
      await new Promise<void>((resolve, reject) => {
        pollRef.current = setInterval(async () => {
          try {
            const j = await api.getJob(job.id);
            const st = ((j as any).live_status || j.status) as string;
            if (st === "done") { stopPolling(); resolve(); }
            else if (st === "error") { stopPolling(); reject(new Error("Weryfikacja pliku (Etap 1) nie powiodła się.")); }
          } catch { /* przejściowy błąd pingu — próbujemy dalej */ }
        }, 2500);
      });
      // Zadanie „tylko lekarze" musi trafić na listę wyboru, inaczej pole pokazywałoby
      // inny miesiąc niż ten faktycznie liczony (i po odświeżeniu nie dałoby się wrócić).
      refreshMonths();
      await run(false, job.id);
    } catch (e: any) {
      stopPolling(); setError(e.message || "Nie udało się przetworzyć pliku."); setBusy(false);
    } finally {
      flowRef.current = false;
    }
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
          <span className="text-[13px] font-semibold text-slate-200">Miesiąc rozliczenia</span>
          <select className="input min-w-[280px]" value={jobId} onChange={(e) => setJobId(e.target.value)}>
            {months.length === 0 && <option value="">brak rozliczeń miesięcznych</option>}
            {months.map((m) => (
              <option key={m.job_id} value={m.job_id}>
                {m.mode === "doctors"
                  ? `${m.period ? periodLabel(m.period) : (m.input_name || "wgrany plik")} · tylko lekarze`
                  : `${periodLabel(m.period || "")} · ${zl(m.revenue)}`}
              </option>
            ))}
          </select>
        </label>
        {isAdmin && (
          <button className="btn-primary" disabled={!jobId || busy} onClick={() => run(false)}>
            {busy ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} />}
            Policz rozliczenie lekarzy
          </button>
        )}
        {isAdmin && (
          <label className={`btn-secondary cursor-pointer ${busy ? "pointer-events-none opacity-50" : ""}`}
                 title="Wgraj nowy plik miesięczny i policz TYLKO lekarzy (bez rozliczenia jednostek)">
            <UploadCloud size={18} /> Nowy plik → tylko lekarze
            <input type="file" accept=".xlsx,.xls" className="hidden" disabled={busy}
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) uploadAndRun(f); }} />
          </label>
        )}
        {result && !result.empty && (
          <>
            {!!result.files_count && (
              <a className="btn-primary" href={api.doctorsBillingFilesUrl(jobId)}>
                <Download size={18} /> Pobierz pliki lekarzy (ZIP · {result.files_count})
              </a>
            )}
            <a className="btn-secondary" href={api.doctorsBillingDownloadUrl(jobId)}>
              <Download size={18} /> Podsumowanie badań (Excel)
            </a>
            {isAdmin && (
              <button className="btn-secondary" disabled={busy} onClick={() => run(true)}>
                <RefreshCw size={18} /> Przelicz ponownie
              </button>
            )}
            {result.computed_at && (
              <span className="text-xs text-slate-400">
                Zapisano: {new Date(result.computed_at).toLocaleString("pl-PL")}
              </span>
            )}
          </>
        )}
      </div>

      {busy && (
        <div className="card flex items-center gap-3 border-brand-accent/40 text-sm text-slate-300">
          <Loader2 className="animate-spin text-brand-accent2" size={18} />
          Liczę rozliczenie lekarzy w tle (osobny proces — możesz zostawić tę zakładkę otwartą).
          Generowanie plików per lekarz może potrwać przy większej liczbie badań.
        </div>
      )}

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

          {/* Bez kategorii lekarskiej — brak wpisu „Rodzaj procedury lekarz" w słowniku. */}
          {(result.validation.categories_missing?.length ?? 0) > 0 && (
            <div className="card space-y-3 border-amber-400/30">
              <h2 className="flex items-center gap-2 text-base font-bold text-amber-300">
                <AlertTriangle size={18} /> Bez kategorii lekarskiej ({result.validation.studies_without_category} badań)
              </h2>
              <p className="text-[13px] text-slate-400">
                Poniższe pary <b>Procedura + Rodzaj procedury rozlicz.</b> nie mają przypisanej kategorii lekarskiej.
                Uzupełnij dla nich kolumnę <b>„Rodzaj procedury lekarz"</b> w słowniku (np. „TK A", „MR C") — wtedy
                badania zaczną się wyceniać.
              </p>
              <div className="max-h-56 overflow-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-brand-surface text-slate-400">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs uppercase">Modalność</th>
                      <th className="px-3 py-2 text-left text-xs uppercase">Procedura</th>
                      <th className="px-3 py-2 text-left text-xs uppercase">Rodzaj procedury rozlicz.</th>
                      <th className="px-3 py-2 text-right text-xs uppercase">Badania</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.validation.categories_missing!.map((p, i) => (
                      <tr key={i} className="border-t border-white/10">
                        <td className="px-3 py-2 text-slate-300">{p.modalnosc}</td>
                        <td className="px-3 py-2">{p.procedura}</td>
                        <td className="px-3 py-2 text-slate-300">{p.rodzaj}</td>
                        <td className="px-3 py-2 text-right text-slate-400">{p.n}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Badania rozliczone po stawce 0 zł — pozycja jest w cenniku, ale stawka = 0. */}
          {(result.validation.zero_rate_pairs?.length ?? 0) > 0 && (
            <div className="card space-y-3 border-sky-400/30">
              <h2 className="flex items-center gap-2 text-base font-bold text-sky-300">
                <AlertTriangle size={18} /> Rozliczone po stawce 0 zł ({result.validation.zero_rate_studies ?? 0} badań)
              </h2>
              <p className="text-[13px] text-slate-400">
                Pozycja istnieje w cenniku lekarza, ale stawka wynosi 0 zł — badania policzone z wartością 0.
              </p>
              <div className="max-h-56 overflow-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-brand-surface text-slate-400">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs uppercase">Lekarz</th>
                      <th className="px-3 py-2 text-left text-xs uppercase">Kategoria (cennik lekarzy)</th>
                      <th className="px-3 py-2 text-right text-xs uppercase">Badania 0 zł</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.validation.zero_rate_pairs!.map((p, i) => (
                      <tr key={i} className="border-t border-white/10">
                        <td className="px-3 py-2">{p.lekarz}</td>
                        <td className="px-3 py-2 text-slate-300">{p.kategoria}</td>
                        <td className="px-3 py-2 text-right text-slate-400">{p.n}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="card">
            <h2 className="mb-3 text-base font-bold">Rozliczenie per lekarz</h2>
            <div className="max-h-[28rem] overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-brand-surface text-slate-400">
                  <tr><th className="px-3 py-2 text-left text-xs uppercase">Lekarz</th><th className="px-3 py-2 text-right text-xs uppercase">Badania</th><th className="px-3 py-2 text-right text-xs uppercase">w tym konsultacje</th><th className="px-3 py-2 text-right text-xs uppercase">Wartość</th></tr>
                </thead>
                <tbody>
                  {result.by_doctor!.map((d, i) => (
                    <tr key={i} className="border-t border-white/10">
                      <td className="px-3 py-2">{d.lekarz}</td>
                      <td className="px-3 py-2 text-right text-slate-400">{d.ilosc}</td>
                      <td className="px-3 py-2 text-right text-slate-400">{(d.wartosc_konsultacje ?? 0) > 0 ? zl(d.wartosc_konsultacje!) : "—"}</td>
                      <td className="px-3 py-2 text-right font-semibold">{zl(d.wartosc)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Podsumowanie na dole: badania + gotowość/triaż = razem. */}
          {result.availability_error ? (
            <div className="card border-amber-400/30 text-[13px] text-amber-300">
              <AlertTriangle className="mb-0.5 inline" size={14} /> Gotowość (TeamUp) pominięta: {result.availability_error}
            </div>
          ) : ((result.validation.value_availability ?? 0) > 0 || (result.validation.value_consultations ?? 0) > 0) ? (
            <div className="card">
              <div className="ml-auto max-w-xs space-y-1 text-sm">
                <div className="flex justify-between"><span className="text-slate-400">Suma za badania (opisy)</span><span className="font-semibold">{zl(result.validation.value_studies ?? result.validation.value_opis ?? 0)}</span></div>
                {(result.validation.value_consultations ?? 0) > 0 && (
                  <div className="flex justify-between"><span className="text-slate-400">Konsultacje</span><span className="font-semibold">{zl(result.validation.value_consultations!)}</span></div>
                )}
                {(result.validation.value_availability ?? 0) > 0 && (
                  <div className="flex justify-between"><span className="text-slate-400">Gotowość i triaż</span><span className="font-semibold">{zl(result.validation.value_availability!)}</span></div>
                )}
                <div className="flex justify-between border-t border-white/10 pt-1"><span className="font-semibold">Razem</span><span className="font-extrabold text-brand-accent2">{zl(result.validation.total_value)}</span></div>
              </div>
              {(result.validation.value_availability ?? 0) > 0 && (
                <a className="btn-secondary mt-3" href={api.doctorsAvailabilityUrl(jobId)}>
                  <Download size={16} /> Pobierz gotowość — szczegóły (Excel)
                </a>
              )}
              {result.availability && (
                <p className="mt-2 text-[13px] text-slate-400">
                  Triaż: {zl(result.availability.sum_triaz)} ({(result.availability.hours_triaz ?? 0).toLocaleString("pl-PL")} godz.)
                  {(result.availability.unbilled_hours ?? 0) > 0 && (
                    <span className="text-amber-300"> · godzin bez stawki: {result.availability.unbilled_hours!.toLocaleString("pl-PL")} (rozliczone na 0)</span>
                  )}
                  {(result.availability.unmatched_hours ?? 0) > 0 && (
                    <span className="text-amber-300"> · godzin nierozpoznanych: {result.availability.unmatched_hours!.toLocaleString("pl-PL")}</span>
                  )}
                </p>
              )}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
