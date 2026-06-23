"use client";

import { useEffect, useMemo, useState } from "react";
import { Play, Loader2, AlertTriangle, Download, RefreshCw, Search } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid,
} from "recharts";
import { api, Job, DoctorComparison } from "@/lib/api";

const zl = (n: number) =>
  n.toLocaleString("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });

const TOOLTIP_STYLE = { background: "#0e3b49", border: "1px solid #214652", borderRadius: 12 };
const POS = "#1dab5a";
const NEG = "#ef6a6a";

type MarginRow = {
  name: string; ilosc: number;
  przychod_jednostki: number; koszt_lekarzy: number; marza: number;
};

/* ---------- Widok rentowności (wspólny dla lekarzy i jednostek) ---------- */
function MarginView({ rows, nameLabel }: { rows: MarginRow[]; nameLabel: string }) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    const base = s ? rows.filter((r) => r.name.toLowerCase().includes(s)) : rows;
    return [...base].sort((a, b) => b.marza - a.marza);
  }, [rows, q]);

  // Wykres: do 20 pozycji o największej |marży| (czytelność); tabela pokazuje wszystkie.
  const chartData = useMemo(
    () => [...filtered].sort((a, b) => Math.abs(b.marza) - Math.abs(a.marza)).slice(0, 20)
      .map((r) => ({ name: r.name, marza: r.marza })),
    [filtered],
  );

  const sum = filtered.reduce(
    (a, r) => ({
      przychod: a.przychod + r.przychod_jednostki,
      koszt: a.koszt + r.koszt_lekarzy,
      marza: a.marza + r.marza,
    }),
    { przychod: 0, koszt: 0, marza: 0 },
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            className="input min-w-[240px] pl-9"
            placeholder={`Filtruj ${nameLabel}…`}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <span className="text-[13px] text-slate-400">
          {filtered.length} {nameLabel} · marża{" "}
          <b className={sum.marza >= 0 ? "text-brand-accent2" : "text-red-300"}>{zl(sum.marza)}</b>
        </span>
      </div>

      {chartData.length > 0 && (
        <div className="card">
          <h3 className="mb-3 text-sm font-bold text-slate-200">
            Marża „ile do przodu" — {chartData.length === 20 ? "20 największych (wg |marży|)" : `${chartData.length} pozycji`}
          </h3>
          <ResponsiveContainer width="100%" height={Math.max(220, chartData.length * 26)}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 16 }}>
              <CartesianGrid horizontal={false} stroke="#ffffff12" />
              <XAxis type="number" stroke="#8aa0a3" fontSize={12} tickFormatter={(v) => (v / 1000).toFixed(0) + "k"} />
              <YAxis type="category" dataKey="name" width={170} stroke="#8aa0a3" fontSize={11} interval={0} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => zl(v)} cursor={{ fill: "#ffffff0a" }} />
              <Bar dataKey="marza" name="Marża" radius={[0, 6, 6, 0]}>
                {chartData.map((d, i) => (
                  <Cell key={i} fill={d.marza >= 0 ? POS : NEG} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="card">
        <div className="max-h-[28rem] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-brand-surface text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left text-xs uppercase">{nameLabel}</th>
                <th className="px-3 py-2 text-right text-xs uppercase">Ilość</th>
                <th className="px-3 py-2 text-right text-xs uppercase">Jednostki</th>
                <th className="px-3 py-2 text-right text-xs uppercase">Lekarze</th>
                <th className="px-3 py-2 text-right text-xs uppercase">Marża</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-4 text-slate-500">Brak pozycji dla filtra.</td></tr>
              )}
              {filtered.map((r, i) => (
                <tr key={i} className="border-t border-white/10">
                  <td className="px-3 py-2 font-medium">{r.name}</td>
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
    </div>
  );
}

const TABS = [
  { id: "kategoria", label: "Per kategoria" },
  { id: "lekarz", label: "Per lekarz" },
  { id: "jednostka", label: "Per jednostka" },
] as const;
type TabId = (typeof TABS)[number]["id"];

// Zapamiętujemy ostatnio wybrane zadanie, żeby po powrocie na kartę pokazać je
// ponownie wraz z zapisanym (zcache'owanym) porównaniem — bez ponownego liczenia.
const LS_JOB = "porownanie_job_id";

export default function PorownaniePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState<string>("");
  const [result, setResult] = useState<DoctorComparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("kategoria");

  useEffect(() => {
    api.listJobs().then((all) => {
      const done = all.filter((j) => j.status === "done" && j.mode === "full");
      setJobs(done);
      if (done.length) {
        // Przywróć ostatnio oglądane zadanie (jeśli wciąż istnieje), inaczej najnowsze.
        const saved = typeof window !== "undefined" ? localStorage.getItem(LS_JOB) : null;
        setJobId(saved && done.some((j) => j.id === saved) ? saved : done[0].id);
      }
    }).catch((e) => setError(e.message));
  }, []);

  // Wczytaj zapisane porównanie po wyborze zadania (bez liczenia) i zapamiętaj wybór.
  useEffect(() => {
    if (!jobId) { setResult(null); return; }
    if (typeof window !== "undefined") localStorage.setItem(LS_JOB, jobId);
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
  const docRows: MarginRow[] = (result?.by_doctor ?? []).map((r) => ({ name: r.lekarz, ...r }));
  const unitRows: MarginRow[] = (result?.by_unit ?? []).map((r) => ({ name: r.jednostka, ...r }));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Porównanie lekarze ↔ jednostki</h1>
        <p className="text-sm text-slate-400">
          Rentowność (marża = przychód z cennika jednostek − koszt z cennika lekarzy), policzona na tych samych
          zweryfikowanych badaniach. „Ile jesteśmy do przodu" per kategoria, per lekarz i per jednostka.
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
          {/* Pełny przychód jednostek — zgodny z rozliczeniem (Pulpit). */}
          <div className="card border-brand-accent/40">
            <p className="text-sm text-slate-400">Przychód jednostek — całość (jak w rozliczeniu)</p>
            <p className="mt-1 text-3xl font-extrabold">{zl(t.przychod_jednostki_total ?? (t.przychod_jednostki + (t.przychod_jednostki_bez_kategorii ?? 0)))}</p>
          </div>

          {/* Rentowność — TYLKO badania z przypisaną kategorią lekarską (ten sam zbiór po obu stronach). */}
          <div>
            <p className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-slate-400">
              Rentowność na badaniach z kategorią lekarską ({t.studies_with_category ?? "—"} z {t.studies})
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="card"><p className="text-sm text-slate-400">Przychód jednostek (z kategorią)</p><p className="mt-2 text-2xl font-extrabold">{zl(t.przychod_jednostki)}</p></div>
              <div className="card"><p className="text-sm text-slate-400">Koszt lekarzy</p><p className="mt-2 text-2xl font-extrabold">{zl(t.koszt_lekarzy)}</p></div>
              <div className="card border-brand-accent/40"><p className="text-sm text-slate-400">Marża</p><p className="mt-2 text-2xl font-extrabold text-brand-accent2">{zl(t.marza)}</p></div>
            </div>
          </div>
          {t.studies_without_category > 0 && (
            <p className="text-[13px] text-amber-300">
              <AlertTriangle className="mb-0.5 inline" size={14} /> Marża liczona na {t.studies_with_category ?? "—"} badaniach z kategorią lekarską.
              Pozostałe <b>{t.studies_without_category}</b> badań nie ma kategorii (brak w słowniku „Rodzaj procedury lekarz")
              {t.przychod_jednostki_bez_kategorii ? ` — ich przychód jednostek ${zl(t.przychod_jednostki_bez_kategorii)} jest w „całości", ale nieujęty w marży` : ""}. Uzupełnij słownik, by marża objęła wszystko.
            </p>
          )}

          {/* Zakładki */}
          <div className="flex flex-wrap gap-2">
            {TABS.map((x) => (
              <button key={x.id} onClick={() => setTab(x.id)} className={tab === x.id ? "btn-primary" : "btn-secondary"}>
                {x.label}
              </button>
            ))}
          </div>

          {tab === "kategoria" && (
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
          )}

          {tab === "lekarz" && <MarginView rows={docRows} nameLabel="lekarzy" />}
          {tab === "jednostka" && <MarginView rows={unitRows} nameLabel="jednostek" />}
        </>
      )}
    </div>
  );
}
