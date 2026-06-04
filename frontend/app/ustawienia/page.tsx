"use client";

import { useEffect, useState } from "react";
import { Save, RotateCcw, Plus, Trash2, X, ArrowRight, CheckCircle2, Cpu } from "lucide-react";
import { api } from "@/lib/api";

type MapPair = { from: string; to: string };

/* ---------- Edytor mapowań (źródło → cel) ---------- */
function MapEditor({
  pairs, setPairs, fromPlaceholder, toPlaceholder, addLabel,
}: {
  pairs: MapPair[];
  setPairs: (p: MapPair[]) => void;
  fromPlaceholder: string;
  toPlaceholder: string;
  addLabel: string;
}) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  function add() {
    if (!from.trim() || !to.trim()) return;
    setPairs([...pairs, { from: from.trim(), to: to.trim() }]);
    setFrom("");
    setTo("");
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {pairs.length === 0 && <p className="text-sm text-slate-500">Brak reguł.</p>}
        {pairs.map((p, i) => (
          <div key={i} className="soft flex items-center gap-2.5 px-3 py-2.5">
            <span className="font-semibold">{p.from}</span>
            <ArrowRight size={16} className="text-slate-500" />
            <span className="chip">{p.to || <span className="italic opacity-70">(brak)</span>}</span>
            <button
              className="btn-secondary ml-auto !px-2 !py-1.5"
              onClick={() => setPairs(pairs.filter((_, j) => j !== i))}
              aria-label="Usuń"
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <input className="input sm:max-w-[220px]" placeholder={fromPlaceholder}
          value={from} onChange={(e) => setFrom(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()} />
        <ArrowRight size={16} className="hidden shrink-0 text-slate-500 sm:block" />
        <input className="input sm:max-w-[220px]" placeholder={toPlaceholder}
          value={to} onChange={(e) => setTo(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()} />
        <button className="btn-secondary" onClick={add}><Plus size={16} /> {addLabel}</button>
      </div>
    </div>
  );
}

/* ---------- Edytor tagów (słowa kluczowe) ---------- */
function ChipEditor({ items, setItems }: { items: string[]; setItems: (x: string[]) => void }) {
  const [val, setVal] = useState("");
  function add() {
    const v = val.trim();
    if (!v || items.includes(v)) { setVal(""); return; }
    setItems([...items, v]);
    setVal("");
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {items.length === 0 && <p className="text-sm text-slate-500">Brak słów.</p>}
        {items.map((w, i) => (
          <span key={i} className="chip">
            {w}
            <button onClick={() => setItems(items.filter((_, j) => j !== i))}
              className="rounded p-0.5 hover:bg-white/15 hover:text-white" aria-label="Usuń">
              <X size={13} />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input className="input" placeholder="dodaj słowo…" value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()} />
        <button className="btn-secondary" onClick={add}><Plus size={16} /></button>
      </div>
    </div>
  );
}

const objToPairs = (o: Record<string, string> = {}) =>
  Object.entries(o).map(([from, to]) => ({ from, to }));
const pairsToObj = (p: MapPair[]) =>
  Object.fromEntries(p.map(({ from, to }) => [from, to]));

const CORE_OPTIONS = [0, 2, 4, 6, 8];

export default function UstawieniaPage() {
  const [settings, setSettings] = useState<any>(null);
  const [numProc, setNumProc] = useState(0);
  const [priority, setPriority] = useState<MapPair[]>([]);
  const [tkSuffix, setTkSuffix] = useState<MapPair[]>([]);
  const [glkrg, setGlkrg] = useState<string[]>([]);
  const [stawy, setStawy] = useState<string[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function hydrate(s: any) {
    setSettings(s);
    setNumProc(s.num_processes ?? s.num_processes_verify ?? 0);
    setPriority(objToPairs(s.priority_map));
    setTkSuffix(objToPairs(s.tk_suffix_map));
    setGlkrg(s.mr_glkrg_keywords ?? []);
    setStawy(s.mr_stawy_keywords ?? []);
  }

  function load() {
    api.getSettings().then(({ settings }) => hydrate(settings)).catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function save() {
    setMsg(null);
    setError(null);
    const payload = {
      ...settings,
      num_processes: numProc,
      priority_map: pairsToObj(priority),
      tk_suffix_map: pairsToObj(tkSuffix),
      mr_glkrg_keywords: glkrg,
      mr_stawy_keywords: stawy,
    };
    try {
      await api.saveSettings(payload);
      setSettings(payload);
      setMsg("Zapisano ustawienia.");
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function reset() {
    if (!confirm("Przywrócić ustawienia domyślne?")) return;
    try {
      await api.resetSettings();
      load();
      setMsg("Przywrócono ustawienia domyślne.");
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (!settings) return <div className="card">Wczytywanie…</div>;

  const coreOptions = CORE_OPTIONS.includes(numProc) ? CORE_OPTIONS : [...CORE_OPTIONS, numProc].sort((a, b) => a - b);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Ustawienia silnika</h1>
        <p className="text-sm text-slate-400">
          Reguły używane przy rozliczeniach. Edytuj wszystko klikając — bez znajomości kodu.
        </p>
      </header>

      {msg && (
        <div className="card flex items-center gap-2 border-brand-accent/50 text-brand-accent2">
          <CheckCircle2 size={18} /> {msg}
        </div>
      )}
      {error && <div className="card border-red-500/40 text-red-300">{error}</div>}

      {/* Wydajność */}
      <div className="card">
        <h2 className="flex items-center gap-2 text-base font-bold">
          <Cpu size={18} className="text-brand-accent" /> Wydajność obliczeń
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-slate-400">
          Ustawiane <b className="text-slate-200">raz</b> dla całego procesu (weryfikacja i rozliczenia).
          Wartość jest automatycznie ograniczana do liczby fizycznych rdzeni serwera — wpisanie wyższej
          liczby niż ma maszyna nie przyspieszy obliczeń.
        </p>
        <div className="mt-4 grid items-end gap-4 sm:grid-cols-2">
          <label className="block space-y-2">
            <span className="text-[13px] font-semibold text-slate-200">Liczba rdzeni do obliczeń</span>
            <select className="input" value={numProc} onChange={(e) => setNumProc(parseInt(e.target.value))}>
              {coreOptions.map((n) => (
                <option key={n} value={n}>{n === 0 ? "Auto — wszystkie dostępne (zalecane)" : `${n} rdzenie`}</option>
              ))}
            </select>
          </label>
          <p className="text-[13px] text-slate-400">
            „Auto" wykorzysta wszystkie rdzenie dostępne na serwerze liczącym.
          </p>
        </div>
      </div>

      {/* Priorytety procedur */}
      <div className="card">
        <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold">Priorytety rodzajów procedur</h2>
          <span className="pill pill-muted">źródło → cel</span>
        </div>
        <p className="mb-4 text-[13px] text-slate-400">
          Mapowanie opisu pilności na sufiks cennikowy (np. „Pilny" → PILNE).
        </p>
        <MapEditor pairs={priority} setPairs={setPriority}
          fromPlaceholder="opis (np. Pilny)" toPlaceholder="sufiks (np. PILNE)" addLabel="Dodaj regułę" />
      </div>

      {/* Sufiksy TK */}
      <div className="card">
        <h2 className="text-base font-bold">Mapowanie sufiksów TK</h2>
        <p className="mb-4 mt-1 text-[13px] text-slate-400">
          Dodatkowe oznaczenie doklejane do nazwy badania TK wg rodzaju procedury.
        </p>
        <MapEditor pairs={tkSuffix} setPairs={setTkSuffix}
          fromPlaceholder="rodzaj (np. TK Angiografia)" toPlaceholder="sufiks (np. ANGIO)" addLabel="Dodaj sufiks" />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="card">
          <h2 className="text-base font-bold">Słowa kluczowe MR — głowa / kręgosłup</h2>
          <p className="mb-4 mt-1 text-[13px] text-slate-400">
            Badanie MR zawierające którekolwiek słowo trafia do grupy GŁ/KRG.
          </p>
          <ChipEditor items={glkrg} setItems={setGlkrg} />
        </div>
        <div className="card">
          <h2 className="text-base font-bold">Słowa kluczowe MR — stawy</h2>
          <p className="mb-4 mt-1 text-[13px] text-slate-400">
            Badanie MR zawierające którekolwiek słowo trafia do grupy STAWY.
          </p>
          <ChipEditor items={stawy} setItems={setStawy} />
        </div>
      </div>

      <div className="flex gap-3">
        <button className="btn-primary" onClick={save}><Save size={18} /> Zapisz ustawienia</button>
        <button className="btn-secondary" onClick={reset}><RotateCcw size={18} /> Przywróć domyślne</button>
      </div>
    </div>
  );
}
