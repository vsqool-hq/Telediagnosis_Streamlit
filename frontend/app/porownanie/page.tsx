"use client";

import { useEffect, useMemo, useState } from "react";
import { Play, Loader2, AlertTriangle, Download, RefreshCw, Search } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid,
} from "recharts";
import { api, CompareMonth, DoctorComparison, doctorKey } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCachedData } from "@/lib/cache";
import { RevenueHistoryHover } from "@/components/RevenueHistoryHover";

const zl = (n: number) =>
  n.toLocaleString("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });

// Marża procentowa = marża / przychód danej pozycji (× 100). Baza to przychód
// jednostek — pokazuje, jaki % przychodu zostaje jako zysk. „—" gdy brak przychodu.
const pct = (marza: number, base: number) =>
  base > 0
    ? (marza / base * 100).toLocaleString("pl-PL", { maximumFractionDigits: 1 }) + "%"
    : "—";

const TOOLTIP_STYLE = { background: "#0e3b49", border: "1px solid #214652", borderRadius: 12 };
const POS = "#1dab5a";
const NEG = "#ef6a6a";

type MarginRow = {
  name: string; ilosc: number;
  przychod_jednostki: number; koszt_lekarzy: number; marza: number;
};

/* ---------- Widok rentowności (wspólny dla lekarzy i jednostek) ---------- */
function MarginView({
  rows, nameLabel, historyFor, historyLabel,
}: {
  rows: MarginRow[]; nameLabel: string;
  historyFor?: (name: string) => Record<string, number> | undefined;
  historyLabel?: string;
}) {
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
          <b className={sum.marza >= 0 ? "text-brand-accent2" : "text-red-300"}>{zl(sum.marza)}</b>{" "}
          <span className="text-slate-500">({pct(sum.marza, sum.przychod)})</span>
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
                <th className="px-3 py-2 text-right text-xs uppercase">Marża %</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-4 text-slate-500">Brak pozycji dla filtra.</td></tr>
              )}
              {filtered.map((r, i) => (
                <tr key={i} className="border-t border-white/10">
                  <td className="px-3 py-2 font-medium">
                    {historyFor ? (
                      <RevenueHistoryHover history={historyFor(r.name)} label={historyLabel}>{r.name}</RevenueHistoryHover>
                    ) : r.name}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-400">{r.ilosc}</td>
                  <td className="px-3 py-2 text-right">{zl(r.przychod_jednostki)}</td>
                  <td className="px-3 py-2 text-right">{zl(r.koszt_lekarzy)}</td>
                  <td className={`px-3 py-2 text-right font-semibold ${r.marza >= 0 ? "text-brand-accent2" : "text-red-300"}`}>{zl(r.marza)}</td>
                  <td className={`px-3 py-2 text-right ${r.marza >= 0 ? "text-brand-accent2" : "text-red-300"}`}>{pct(r.marza, r.przychod_jednostki)}</td>
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
  { id: "priorytet", label: "Per priorytet" },
  { id: "lekarz", label: "Per lekarz" },
  { id: "jednostka", label: "Per jednostka" },
] as const;
type TabId = (typeof TABS)[number]["id"];

// Zapamiętujemy ostatnio oglądany MIESIĄC, żeby po powrocie na kartę pokazać go
// ponownie wraz z zapisanym porównaniem — bez ponownego liczenia.
const LS_PERIOD = "porownanie_period";

const MONTHS_PL = [
  "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
];
const periodLabel = (p: string) =>
  /^\d{4}-\d{2}$/.test(p) ? `${MONTHS_PL[parseInt(p.slice(5)) - 1]} ${p.slice(0, 4)}` : p;

export default function PorownaniePage() {
  const { isAdmin } = useAuth();
  // Miesiące rozliczeniowe — każdy spięty z jego NAJWIĘKSZYM przeliczeniem
  // (jak wykres na Pulpicie). Nowe, większe przeliczenie przejmuje miesiąc.
  const [months, setMonths] = useState<CompareMonth[]>([]);
  const [period, setPeriod] = useState<string>("");
  const [result, setResult] = useState<DoctorComparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("kategoria");
  const [catSource, setCatSource] = useState<"doctor" | "unit">("doctor");

  const selected = months.find((m) => m.period === period);
  const jobId = selected?.job_id ?? "";

  // Historia kwot per jednostka/lekarz (do dymków po najechaniu) — pobrana raz,
  // niezależnie od wybranej zakładki/miesiąca.
  const { data: unitsHistoryData } = useCachedData("units-revenue-history", () => api.unitsRevenueHistory(), 5 * 60_000);
  const { data: doctorsHistoryData } = useCachedData("doctors-revenue-history", () => api.doctorsRevenueHistory(), 5 * 60_000);

  useEffect(() => {
    api.doctorsCompareMonths().then(({ months: ms }) => {
      setMonths(ms);
      if (!ms.length) return;
      // Przywróć ostatnio oglądany miesiąc; inaczej najnowszy z policzonym
      // porównaniem, a gdy żaden nie ma — po prostu najnowszy.
      const saved = typeof window !== "undefined" ? localStorage.getItem(LS_PERIOD) : null;
      if (saved && ms.some((m) => m.period === saved)) { setPeriod(saved); return; }
      setPeriod((ms.find((m) => m.computed) ?? ms[0]).period);
    }).catch((e) => setError(e.message));
  }, []);

  // Wczytaj zapisane porównanie po wyborze miesiąca (bez liczenia) i zapamiętaj wybór.
  useEffect(() => {
    if (!jobId) { setResult(null); return; }
    if (typeof window !== "undefined" && period) localStorage.setItem(LS_PERIOD, period);
    setResult(null); setError(null);
    api.doctorsCompare(jobId, { peek: true })
      .then((r) => setResult(r && (r as any).reason === "not_computed" ? null : r))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  async function run(recompute = false) {
    if (!jobId) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await api.doctorsCompare(jobId, { recompute });
      setResult(r);
      if (!r.empty) {
        // odśwież znacznik „policzone" przy wybranym miesiącu
        setMonths((ms) => ms.map((m) => (m.period === period ? { ...m, computed: true } : m)));
      }
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  const t = result?.totals;
  const docRows: MarginRow[] = (result?.by_doctor ?? []).map((r) => ({ name: r.lekarz, ...r }));
  const unitRows: MarginRow[] = (result?.by_unit ?? []).map((r) => ({ name: r.jednostka, ...r }));
  const prioRows: MarginRow[] = (result?.rows_priority ?? []).map((r) => ({ name: r.priorytet, ...r }));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Porównanie lekarze ↔ jednostki</h1>
        <p className="text-sm text-slate-400">
          Rentowność (marża = przychód z cennika jednostek − koszt z cennika lekarzy), policzona na tych samych
          zweryfikowanych badaniach. „Ile jesteśmy do przodu" per kategoria, per lekarz i per jednostka.
        </p>
      </header>

      <div className="card space-y-3">
        <div>
          <span className="text-[13px] font-semibold text-slate-200">Miesiąc rozliczenia</span>
          <p className="text-xs text-slate-400">
            Każdy miesiąc jest spięty z jego <b className="text-slate-300">ostatnim przeliczeniem</b> (jak
            wykres na Pulpicie). Kropka = porównanie do policzenia.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {months.length === 0 && <span className="text-sm text-slate-500">brak ukończonych rozliczeń</span>}
          {months.map((m) => (
            <button
              key={m.period}
              onClick={() => setPeriod(m.period)}
              className={period === m.period ? "btn-primary" : "btn-secondary"}
              title={m.computed ? "Porównanie policzone" : "Porównanie jeszcze niepoliczone — kliknij i policz"}
            >
              {periodLabel(m.period)}
              {!m.computed && <span className="ml-1 inline-block h-2 w-2 rounded-full bg-amber-400" />}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {isAdmin && (
            <button className="btn-primary" disabled={!jobId || busy} onClick={() => run(false)}>
              {busy ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} />}
              Policz porównanie
            </button>
          )}
        {result && !result.empty && (
          <>
            <a className="btn-secondary" href={api.doctorsCompareDownloadUrl(jobId)}>
              <Download size={18} /> Pobierz Excel
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
      </div>

      {error && <div className="card border-red-500/40 text-red-300">{error}</div>}

      {selected && !selected.computed && !result && !busy && (
        <div className="card text-amber-300">
          <AlertTriangle className="mb-1 inline" size={16} /> Porównanie dla{" "}
          <b>{periodLabel(selected.period)}</b> nie jest jeszcze policzone dla ostatniego
          przeliczenia tego miesiąca — kliknij „Policz porównanie".
        </div>
      )}

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
              <div className="card"><p className="text-sm text-slate-400">Przychód jednostek (z kategorią)</p><p className="mt-2 text-2xl font-extrabold">{zl(t.przychod_jednostki)}</p>
                {(t.wsparcie ?? 0) > 0 && (
                  <p className="mt-1 text-xs text-slate-400">w tym wsparcie: {zl(t.wsparcie!)}
                    {(t.wsparcie_nieprzypisane ?? 0) > 0 && <span className="text-amber-300"> (+{zl(t.wsparcie_nieprzypisane!)} nieprzypisane)</span>}
                  </p>
                )}
              </div>
              <div className="card"><p className="text-sm text-slate-400">Koszt lekarzy</p><p className="mt-2 text-2xl font-extrabold">{zl(t.koszt_lekarzy)}</p>
                {(t.gotowosc_triaz ?? 0) > 0 && (
                  <p className="mt-1 text-xs text-slate-400">w tym gotowość + triaż: {zl(t.gotowosc_triaz!)}
                    {(t.gotowosc_triaz_nieprzypisane ?? 0) > 0 && <span className="text-amber-300"> (+{zl(t.gotowosc_triaz_nieprzypisane!)} nieprzypisane)</span>}
                  </p>
                )}
              </div>
              <div className="card border-brand-accent/40"><p className="text-sm text-slate-400">Marża</p><p className="mt-2 text-2xl font-extrabold text-brand-accent2">{zl(t.marza)} <span className="text-base font-bold text-slate-400">({pct(t.marza, t.przychod_jednostki)})</span></p></div>
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

          {tab === "kategoria" && (() => {
            const catRows = catSource === "unit" ? result.rows_units : result.rows;
            return (
            <div className="card">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-base font-bold">Marża per kategoria</h2>
                <div className="flex gap-2">
                  <button
                    onClick={() => setCatSource("doctor")}
                    className={`px-3 py-1.5 text-xs ${catSource === "doctor" ? "btn-primary" : "btn-secondary"}`}
                  >
                    Kategorie lekarzy
                  </button>
                  <button
                    onClick={() => setCatSource("unit")}
                    className={`px-3 py-1.5 text-xs ${catSource === "unit" ? "btn-primary" : "btn-secondary"}`}
                  >
                    Kategorie jednostek
                  </button>
                </div>
              </div>
              {catSource === "unit" && !result.rows_units ? (
                <p className="text-[13px] text-amber-300">
                  <AlertTriangle className="mb-0.5 inline" size={14} /> Kategorie jednostek dostępne po
                  ponownym przeliczeniu — kliknij „Przelicz ponownie".
                </p>
              ) : (
                <div className="max-h-[28rem] overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-brand-surface text-slate-400">
                      <tr>
                        <th className="px-3 py-2 text-left text-xs uppercase">Modalność</th>
                        <th className="px-3 py-2 text-left text-xs uppercase">
                          {catSource === "unit" ? "Kategoria (jednostki)" : "Kategoria (lekarze)"}
                        </th>
                        <th className="px-3 py-2 text-right text-xs uppercase">Ilość</th>
                        <th className="px-3 py-2 text-right text-xs uppercase">Jednostki</th>
                        <th className="px-3 py-2 text-right text-xs uppercase">Lekarze</th>
                        <th className="px-3 py-2 text-right text-xs uppercase">Marża</th>
                        <th className="px-3 py-2 text-right text-xs uppercase">Marża %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(catRows ?? []).map((r, i) => (
                        <tr key={i} className="border-t border-white/10">
                          <td className="px-3 py-2 text-slate-400">{r["Modalność"]}</td>
                          <td className="px-3 py-2">{r.kategoria}</td>
                          <td className="px-3 py-2 text-right text-slate-400">{r.ilosc}</td>
                          <td className="px-3 py-2 text-right">{zl(r.przychod_jednostki)}</td>
                          <td className="px-3 py-2 text-right">{zl(r.koszt_lekarzy)}</td>
                          <td className={`px-3 py-2 text-right font-semibold ${r.marza >= 0 ? "text-brand-accent2" : "text-red-300"}`}>{zl(r.marza)}</td>
                          <td className={`px-3 py-2 text-right ${r.marza >= 0 ? "text-brand-accent2" : "text-red-300"}`}>{pct(r.marza, r.przychod_jednostki)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            );
          })()}

          {tab === "priorytet" && (
            prioRows.length > 0
              ? <MarginView rows={prioRows} nameLabel="priorytetów" />
              : <div className="card text-sm text-slate-400">
                  Podział per priorytet pojawi się po przeliczeniu porównania nowym silnikiem —
                  kliknij „Przelicz ponownie".
                </div>
          )}
          {tab === "lekarz" && (
            <MarginView
              rows={docRows} nameLabel="lekarzy" historyLabel="Historia wypłaty"
              historyFor={(name) => doctorsHistoryData?.doctors[doctorKey(name)]}
            />
          )}
          {tab === "jednostka" && (
            <MarginView
              rows={unitRows} nameLabel="jednostek" historyLabel="Historia przychodu"
              historyFor={(name) => unitsHistoryData?.units[name]}
            />
          )}
        </>
      )}
    </div>
  );
}
