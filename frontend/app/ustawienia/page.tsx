"use client";

import { useEffect, useMemo, useState } from "react";
import { Save, RotateCcw, Plus, Trash2, X, ArrowRight, CheckCircle2, Cpu, Sliders, Download } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import BackendSwitcher from "@/components/BackendSwitcher";
import DoctorsSettings from "@/components/DoctorsSettings";
import UnitsSettings from "@/components/UnitsSettings";
import PaymentTermsSettings from "@/components/PaymentTermsSettings";
import TeamupSettings from "@/components/TeamupSettings";

type MapPair = { from: string; to: string };
type AdjRule = { base: string; factor: number };
type AdjMap = Record<string, Record<string, AdjRule>>;

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
function ChipEditor({
  items, setItems, placeholder = "dodaj słowo…", emptyText = "Brak słów.",
}: { items: string[]; setItems: (x: string[]) => void; placeholder?: string; emptyText?: string }) {
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
        {items.length === 0 && <p className="text-sm text-slate-500">{emptyText}</p>}
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
        <input className="input" placeholder={placeholder} value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()} />
        <button className="btn-secondary" onClick={add}><Plus size={16} /></button>
      </div>
    </div>
  );
}

/* ---------- Edytor grup jednostek (łączenie na Pulpicie/Porównaniu) ---------- */
type UnitGroup = { name: string; units: string[] };

function GroupsEditor({ groups, setGroups }: { groups: UnitGroup[]; setGroups: (g: UnitGroup[]) => void }) {
  const [newName, setNewName] = useState("");
  function addGroup() {
    const n = newName.trim();
    if (!n || groups.some((g) => g.name.toLowerCase() === n.toLowerCase())) { setNewName(""); return; }
    setGroups([...groups, { name: n, units: [] }]);
    setNewName("");
  }
  const update = (i: number, g: UnitGroup) => setGroups(groups.map((x, j) => (j === i ? g : x)));
  const remove = (i: number) => setGroups(groups.filter((_, j) => j !== i));
  return (
    <div className="space-y-4">
      {groups.length === 0 && <p className="text-sm text-slate-500">Brak grup. Dodaj pierwszą poniżej.</p>}
      {groups.map((g, i) => (
        <div key={i} className="space-y-3 rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="flex items-center gap-2">
            <input className="input flex-1 font-semibold" value={g.name} placeholder="Nazwa grupy"
              onChange={(e) => update(i, { ...g, name: e.target.value })} />
            <button className="btn-secondary hover:border-red-500 hover:text-red-300"
              onClick={() => remove(i)} aria-label="Usuń grupę"><Trash2 size={16} /></button>
          </div>
          <ChipEditor
            items={g.units}
            setItems={(u) => update(i, { ...g, units: u })}
            placeholder="dodaj jednostkę (np. wsswroclaw)…"
            emptyText="Brak jednostek w tej grupie."
          />
        </div>
      ))}
      <div className="flex gap-2">
        <input className="input" placeholder="nazwa nowej grupy…" value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addGroup()} />
        <button className="btn-secondary" onClick={addGroup}><Plus size={16} /> Dodaj grupę</button>
      </div>
    </div>
  );
}

/* ---------- Edytor współczynników cen jednostek (z filtrem jednostki) ---------- */
function AdjustmentsEditor({
  value, onChange, onReseed,
}: {
  value: AdjMap;
  onChange: (v: AdjMap) => void;
  onReseed: () => void;
}) {
  const units = useMemo(() => Object.keys(value).sort((a, b) => a.localeCompare(b, "pl")), [value]);
  const [unit, setUnit] = useState<string>("");
  const [newUnit, setNewUnit] = useState("");
  const [exam, setExam] = useState("");
  const [base, setBase] = useState("");
  const [factor, setFactor] = useState("");

  // Domyślnie pokaż pierwszą jednostkę; trzymaj wybór w granicach dostępnych.
  useEffect(() => {
    if (units.length && !units.includes(unit)) setUnit(units[0]);
    if (!units.length) setUnit("");
  }, [units, unit]);

  const rules = (unit && value[unit]) || {};
  const ruleKeys = Object.keys(rules).sort((a, b) => a.localeCompare(b, "pl"));
  const total = Object.values(value).reduce((s, r) => s + Object.keys(r).length, 0);

  function setRule(u: string, exKey: string, rule: AdjRule | null) {
    const next: AdjMap = { ...value, [u]: { ...(value[u] || {}) } };
    if (rule === null) delete next[u][exKey];
    else next[u][exKey] = rule;
    if (Object.keys(next[u]).length === 0) delete next[u];
    onChange(next);
  }

  function addUnit() {
    const u = newUnit.trim();
    if (!u) return;
    if (!value[u]) onChange({ ...value, [u]: {} });
    setUnit(u);
    setNewUnit("");
  }

  function addRule() {
    const ex = exam.trim().replace(/\s+/g, " ");
    const bs = base.trim().replace(/\s+/g, " ");
    const f = parseFloat(factor.replace(",", "."));
    if (!unit || !ex || !bs || !isFinite(f)) return;
    setRule(unit, ex, { base: bs, factor: f });
    setExam(""); setBase(""); setFactor("");
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1.5">
          <span className="text-[13px] font-semibold text-slate-200">Jednostka</span>
          <select className="input min-w-[220px]" value={unit} onChange={(e) => setUnit(e.target.value)}>
            {units.length === 0 && <option value="">brak jednostek ze współczynnikami</option>}
            {units.map((u) => (
              <option key={u} value={u}>{u} ({Object.keys(value[u]).length})</option>
            ))}
          </select>
        </label>
        <div className="flex items-end gap-2">
          <label className="space-y-1.5">
            <span className="text-[13px] font-semibold text-slate-200">Dodaj jednostkę</span>
            <input className="input sm:max-w-[200px]" placeholder="np. wsswroclaw" value={newUnit}
              onChange={(e) => setNewUnit(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addUnit()} />
          </label>
          <button className="btn-secondary" onClick={addUnit}><Plus size={16} /> Dodaj</button>
        </div>
        <span className="pill pill-muted ml-auto">{units.length} jednostek · {total} reguł</span>
      </div>

      {unit && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-slate-400">
                <tr>
                  <th className="px-2 py-1.5 text-left text-xs uppercase">Badanie</th>
                  <th className="px-2 py-1.5 text-left text-xs uppercase">= Badanie bazowe</th>
                  <th className="px-2 py-1.5 text-right text-xs uppercase">× Współczynnik</th>
                  <th className="px-2 py-1.5"></th>
                </tr>
              </thead>
              <tbody>
                {ruleKeys.length === 0 && (
                  <tr><td colSpan={4} className="px-2 py-3 text-slate-500">Brak współczynników dla tej jednostki.</td></tr>
                )}
                {ruleKeys.map((ex) => (
                  <tr key={ex} className="border-t border-white/10">
                    <td className="px-2 py-1.5 font-semibold">{ex}</td>
                    <td className="px-2 py-1.5">
                      <input className="input !py-1" value={rules[ex].base}
                        onChange={(e) => setRule(unit, ex, { ...rules[ex], base: e.target.value })} />
                    </td>
                    <td className="px-2 py-1.5">
                      <input className="input !py-1 w-24 text-right" type="number" step="0.01" value={rules[ex].factor}
                        onChange={(e) => setRule(unit, ex, { ...rules[ex], factor: parseFloat(e.target.value) })} />
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <button className="btn-secondary !px-2 !py-1.5" aria-label="Usuń"
                        onClick={() => setRule(unit, ex, null)}><Trash2 size={15} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="soft flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-end">
            <label className="flex-1 space-y-1">
              <span className="text-xs text-slate-400">Badanie (klucz cennikowy)</span>
              <input className="input !py-1.5" placeholder="np. TK CITO ONKO" value={exam}
                onChange={(e) => setExam(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addRule()} />
            </label>
            <label className="flex-1 space-y-1">
              <span className="text-xs text-slate-400">Badanie bazowe</span>
              <input className="input !py-1.5" placeholder="np. TK CITO" value={base}
                onChange={(e) => setBase(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addRule()} />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-slate-400">Współczynnik</span>
              <input className="input !py-1.5 w-28" placeholder="np. 1.25" value={factor}
                onChange={(e) => setFactor(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addRule()} />
            </label>
            <button className="btn-secondary" onClick={addRule}><Plus size={16} /> Dodaj regułę</button>
          </div>
        </>
      )}

      <button className="btn-secondary" onClick={onReseed}>
        <Download size={16} /> Wczytaj współczynniki startowe (z pliku)
      </button>
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
  const [adjustments, setAdjustments] = useState<AdjMap>({});
  const [groups, setGroups] = useState<UnitGroup[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function hydrate(s: any) {
    setSettings(s);
    setNumProc(s.num_processes ?? s.num_processes_verify ?? 0);
    setPriority(objToPairs(s.priority_map));
    setTkSuffix(objToPairs(s.tk_suffix_map));
    setGlkrg(s.mr_glkrg_keywords ?? []);
    setStawy(s.mr_stawy_keywords ?? []);
    setAdjustments(s.unit_adjustments ?? {});
    setGroups(s.unit_groups ?? []);
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
      unit_adjustments: adjustments,
      unit_groups: groups,
    };
    try {
      await api.saveSettings(payload);
      setSettings(payload);
      setMsg("Zapisano ustawienia.");
      toast("Zapisano ustawienia.");
    } catch (e: any) {
      setError(e.message);
      toast("Nie udało się zapisać ustawień.", "error");
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

  async function reseedAdjustments() {
    if (!confirm("Wczytać współczynniki cen z pliku startowego? Nadpisze to bieżącą listę współczynników (pozostałe ustawienia bez zmian).")) return;
    setMsg(null); setError(null);
    try {
      const { unit_adjustments } = await api.reseedAdjustments();
      setAdjustments(unit_adjustments);
      setSettings({ ...settings, unit_adjustments });
      setMsg("Wczytano współczynniki startowe. (Zostały już zapisane.)");
    } catch (e: any) {
      setError(e.message);
    }
  }

  // Przełącznik backendu pokazujemy zawsze (także gdy ustawienia się nie wczytały —
  // np. lokalny backend nie działa — żeby zawsze dało się wrócić na chmurę).
  if (!settings) {
    return (
      <div className="space-y-6">
        <header>
          <h1 className="text-[26px] font-extrabold tracking-tight">Ustawienia</h1>
          <p className="text-sm text-slate-400">Wczytywanie konfiguracji z backendu…</p>
        </header>
        <BackendSwitcher />
        {error && <div className="card border-red-500/40 text-red-300">{error}</div>}
        <div className="card text-slate-400">
          Jeśli to trwa, wybrany backend powyżej może być niedostępny (np. lokalny nie jest uruchomiony).
        </div>
      </div>
    );
  }

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

      <BackendSwitcher />

      {/* Grupy jednostek */}
      <div className="card">
        <h2 className="flex items-center gap-2 text-base font-bold">
          <Sliders size={18} className="text-brand-accent" /> Grupy jednostek
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-slate-400">
          Połącz wybrane jednostki w jedną pozycję na <b className="text-slate-200">Pulpicie</b> (top jednostki)
          i w <b className="text-slate-200">Porównaniu</b> (marża per jednostka). Wpisz nazwę grupy i dodaj
          jednostki po identyfikatorze „Klient" (jak w cenniku, np. <code>wsswroclaw</code>). To tylko widok —
          <b className="text-slate-200"> nie wpływa na rozliczenia ani ceny</b>. Zmiana działa od razu po zapisie.
        </p>
        <div className="mt-4">
          <GroupsEditor groups={groups} setGroups={setGroups} />
        </div>
      </div>

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

      {/* Współczynniki cen jednostek (adjustmenty) */}
      <div className="card">
        <h2 className="flex items-center gap-2 text-base font-bold">
          <Sliders size={18} className="text-brand-accent" /> Współczynniki cen jednostek
        </h2>
        <p className="mb-4 mt-1 text-[13px] leading-relaxed text-slate-400">
          Niektóre jednostki nie mają w cenniku własnej stawki dla danego badania — jest ona liczona
          jako stawka <b className="text-slate-200">innego badania × współczynnik</b> (np. wsswroclaw:
          „TK CITO ONKO" = stawka „TK CITO" × 1,25). Wybierz jednostkę, aby zobaczyć tylko jej reguły.
          Współczynnik ma pierwszeństwo przed dziedziczeniem ceny bazowej, ale nie nadpisuje bezpośredniej
          stawki z cennika.
        </p>
        <AdjustmentsEditor value={adjustments} onChange={setAdjustments} onReseed={reseedAdjustments} />
      </div>

      <div className="flex gap-3">
        <button className="btn-primary" onClick={save}><Save size={18} /> Zapisz ustawienia</button>
        <button className="btn-secondary" onClick={reset}><RotateCcw size={18} /> Przywróć domyślne</button>
      </div>

      <DoctorsSettings />
      <UnitsSettings />
      <PaymentTermsSettings />
      <TeamupSettings />
    </div>
  );
}
