"use client";

// Dopłaty za KONSULTACJE w rozliczeniu lekarzy. Dwie rzeczy:
//  1) Pary: konsultujący → przypisani opisujący. Para zdefiniowana = KONSULTANT
//     liczony 50% swojej stawki, każda inna para = 100%. Dopłata DODATKOWA
//     (opisujący rozliczany bez zmian — 50% NIE dotyczy opisującego).
//  2) Ryczałt: wybrany lekarz ma stałą stawkę za konsultacje = ryczałt × okolice
//     (zamiast logiki par). Nazwiska dopasowywane elastycznie (kolejność/wielkość liter).
// Nazwiska wybiera się z listy (dropdown) — mniej pomyłek. Auto-zapis.
import { useEffect, useId, useState } from "react";
import { Users2, Loader2, Plus, Trash2, X, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";

type Group = { konsultujacy: string; opisujacy: string[] };
type FlatRow = { lekarz: string; stawka: string };

export default function ConsultSettings() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [flat, setFlat] = useState<FlatRow[]>([]);
  const [names, setNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const namesDlId = useId();

  useEffect(() => {
    Promise.all([api.consultConfig(), api.doctorsNames().catch(() => ({ names: [] }))])
      .then(([c, n]) => {
        setGroups(c.groups.map((g) => ({ konsultujacy: g.konsultujacy, opisujacy: [...g.opisujacy] })));
        setFlat(Object.entries(c.flat_rates).map(([lekarz, stawka]) => ({ lekarz, stawka: String(stawka) })));
        setNames(n.names || []);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function persist(nextGroups: Group[], nextFlat: FlatRow[]) {
    const cleanGroups = nextGroups
      .map((g) => ({ konsultujacy: g.konsultujacy.trim(), opisujacy: g.opisujacy.map((o) => o.trim()).filter(Boolean) }))
      .filter((g) => g.konsultujacy && g.opisujacy.length);
    const flat_rates: Record<string, number> = {};
    for (const r of nextFlat) {
      const n = r.lekarz.trim();
      const v = parseFloat(r.stawka.replace(",", "."));
      if (n && Number.isFinite(v) && v > 0) flat_rates[n] = v;
    }
    setSaving(true); setErr(null); setSaved(false);
    try {
      await api.saveConsultConfig({ groups: cleanGroups, flat_rates });
      setSaved(true); setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setErr(e.message); toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  }
  const commit = (g: Group[], f: FlatRow[]) => { setGroups(g); setFlat(f); persist(g, f); };

  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-base font-bold">
          <Users2 size={18} className="text-brand-accent" /> Konsultacje lekarzy (dopłaty)
        </h2>
        {saving ? <span className="flex items-center gap-1.5 text-xs text-slate-400"><Loader2 className="animate-spin" size={13} /> zapis…</span>
          : saved ? <span className="flex items-center gap-1.5 text-xs text-brand-accent2"><CheckCircle2 size={13} /> zapisano</span> : null}
      </div>
      <p className="mt-1 text-[13px] text-slate-400">
        Dopłata dla lekarza w roli <b>Konsultujący</b> (dodatkowa — opisujący rozliczany bez zmian):
        <b> okolice × stawka konsultanta × (50% gdy para zdefiniowana, inaczej 100%)</b>.
        Wyjątek: lekarz z ryczałtem → <b>ryczałt × okolice</b>. Nazwiska wybierasz z listy.
      </p>

      {/* wspólna lista nazwisk do wyboru (konsultujący + ryczałt) */}
      <datalist id={namesDlId}>
        {names.map((n) => <option key={n} value={n} />)}
      </datalist>

      {loading ? (
        <div className="mt-4 flex items-center gap-2 text-slate-400"><Loader2 className="animate-spin" size={16} /> Wczytywanie…</div>
      ) : (
        <div className="mt-4 space-y-6">
          {/* --- Pary konsultujący → opisujący --- */}
          <div>
            <h3 className="mb-1 text-sm font-semibold text-slate-200">Pary: konsultujący → jego opisujący</h3>
            <p className="mb-2 text-xs text-slate-500">
              Do jednego <b>konsultującego</b> możesz przypisać <b>wielu opisujących</b>. Gdy konsultujący
              wystąpi w parze z którymś z nich — konsultant liczony jest <b>50%</b> stawki; z każdym innym opisującym — 100%.
            </p>
            <div className="space-y-3">
              {groups.length === 0 && <p className="text-sm text-slate-500">Brak par. Każdy konsultujący spoza par = 100%.</p>}
              {groups.map((g, i) => (
                <div key={i} className="rounded-xl border border-white/10 bg-white/[0.02] p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400 w-24 shrink-0">Konsultujący:</span>
                    <input className="input flex-1 font-semibold" placeholder="wybierz z listy… (np. Adam Marecki)"
                      list={namesDlId}
                      value={g.konsultujacy}
                      onChange={(e) => setGroups((p) => p.map((x, j) => j === i ? { ...x, konsultujacy: e.target.value } : x))}
                      onBlur={() => persist(groups, flat)} />
                    <button className="btn-secondary !px-2 !py-1.5 hover:!border-red-400 hover:!text-red-300"
                      onClick={() => commit(groups.filter((_, j) => j !== i), flat)} title="Usuń parę"><Trash2 size={14} /></button>
                  </div>
                  <ChipInput
                    label="Opisujący:"
                    items={g.opisujacy}
                    options={names}
                    onChange={(items) => commit(groups.map((x, j) => j === i ? { ...x, opisujacy: items } : x), flat)}
                  />
                </div>
              ))}
              <button className="btn-secondary text-sm" onClick={() => setGroups((p) => [...p, { konsultujacy: "", opisujacy: [] }])}>
                <Plus size={15} /> Dodaj parę
              </button>
            </div>
          </div>

          {/* --- Ryczałty --- */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-200">Ryczałt za konsultacje (wyjątek per lekarz)</h3>
            <div className="space-y-2">
              {flat.length === 0 && <p className="text-sm text-slate-500">Brak ryczałtów.</p>}
              {flat.map((r, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <input className="input sm:w-56" placeholder="wybierz lekarza…" list={namesDlId} value={r.lekarz}
                    onChange={(e) => setFlat((p) => p.map((x, j) => j === i ? { ...x, lekarz: e.target.value } : x))}
                    onBlur={() => persist(groups, flat)} />
                  <input className="input sm:w-32" placeholder="zł / okolicę" value={r.stawka}
                    onChange={(e) => setFlat((p) => p.map((x, j) => j === i ? { ...x, stawka: e.target.value } : x))}
                    onBlur={() => persist(groups, flat)} />
                  <span className="text-xs text-slate-500">× okolice</span>
                  <button className="btn-secondary !px-2 !py-1.5" onClick={() => commit(groups, flat.filter((_, j) => j !== i))} title="Usuń"><Trash2 size={14} /></button>
                </div>
              ))}
              <button className="btn-secondary text-sm" onClick={() => setFlat((p) => [...p, { lekarz: "", stawka: "" }])}>
                <Plus size={15} /> Dodaj ryczałt
              </button>
            </div>
          </div>
        </div>
      )}
      {err && <p className="mt-2 text-sm text-red-300">{err}</p>}
    </div>
  );
}

function ChipInput({ label, items, options, onChange }: { label: string; items: string[]; options: string[]; onChange: (x: string[]) => void }) {
  const [val, setVal] = useState("");
  const dlId = useId();
  const remaining = options.filter((o) => !items.includes(o));
  function add(v: string) {
    v = v.trim();
    if (!v || items.includes(v)) { setVal(""); return; }
    onChange([...items, v]); setVal("");
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-slate-400 w-24 shrink-0">{label}</span>
      {items.map((w, i) => (
        <span key={i} className="chip">{w}
          <button onClick={() => onChange(items.filter((_, j) => j !== i))} className="rounded p-0.5 hover:bg-white/15 hover:text-white"><X size={13} /></button>
        </span>
      ))}
      <input className="input !w-52 !py-1.5 text-sm" placeholder="wybierz opisującego…" list={dlId} value={val}
        onChange={(e) => {
          const v = e.target.value;
          if (options.includes(v)) add(v);   // wybrano pozycję z listy → dodaj od razu
          else setVal(v);
        }}
        onKeyDown={(e) => e.key === "Enter" && add(val)} onBlur={() => add(val)} />
      <datalist id={dlId}>
        {remaining.map((o) => <option key={o} value={o} />)}
      </datalist>
    </div>
  );
}
