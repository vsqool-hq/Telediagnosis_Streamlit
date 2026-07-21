"use client";

// Scalanie jednostek podległych w główną. Działa U ŹRÓDŁA (zmienia „Klient" przed
// podziałem na pliki), więc badania podległej trafiają do głównej: nie powstaje plik
// podległej i nie pokazuje się ona na Pulpicie/Porównaniach/Mapie. Rozliczana po
// cenniku głównej. Samodzielny komponent — własny endpoint, auto-zapis.
import { useEffect, useMemo, useState } from "react";
import { GitMerge, Loader2, Plus, Trash2, CheckCircle2, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";

type Row = { from: string; to: string };

export default function UnitAliasSettings() {
  const [rows, setRows] = useState<Row[]>([]);
  const [units, setUnits] = useState<{ name: string; key: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    Promise.all([api.unitAliases(), api.unitsList()])
      .then(([a, u]) => {
        setRows(Object.entries(a.aliases).map(([from, to]) => ({ from, to })));
        setUnits(u.units.map(({ name, key }) => ({ name, key })));
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Lista do wyboru: jednostki z ostatniego rozliczenia + klucze już użyte w mapie.
  const options = useMemo(() => {
    const known = new Set(units.map((u) => u.key));
    const extra = rows
      .flatMap((r) => [r.from, r.to])
      .filter((k) => k && !known.has(k))
      .map((k) => ({ name: k, key: k }));
    const seen = new Set<string>();
    return [...units, ...extra].filter((u) => (seen.has(u.key) ? false : (seen.add(u.key), true)));
  }, [units, rows]);

  async function persist(next: Row[]) {
    // Do zapisu bierzemy tylko kompletne, poprawne pary (bez X→X).
    const map: Record<string, string> = {};
    for (const r of next) {
      const f = r.from.trim(), t = r.to.trim();
      if (f && t && f.toLowerCase() !== t.toLowerCase()) map[f] = t;
    }
    setSaving(true); setErr(null); setSaved(false);
    try {
      await api.saveUnitAliases(map);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setErr(e.message);
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  }

  function update(i: number, patch: Partial<Row>) {
    setRows((prev) => {
      const next = prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r));
      persist(next);
      return next;
    });
  }
  function addRow() {
    setRows((prev) => [...prev, { from: "", to: "" }]);
  }
  function removeRow(i: number) {
    setRows((prev) => {
      const next = prev.filter((_, idx) => idx !== i);
      persist(next);
      return next;
    });
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-base font-bold">
          <GitMerge size={18} className="text-brand-accent" /> Scalanie jednostek (podległa → główna)
        </h2>
        {saving ? (
          <span className="flex items-center gap-1.5 text-xs text-slate-400"><Loader2 className="animate-spin" size={13} /> zapis…</span>
        ) : saved ? (
          <span className="flex items-center gap-1.5 text-xs text-brand-accent2"><CheckCircle2 size={13} /> zapisano</span>
        ) : null}
      </div>
      <p className="mt-1 text-[13px] text-slate-400">
        Badania jednostki <b>podległej</b> trafią do <b>głównej</b> już przy liczeniu: nie powstanie
        osobny plik podległej i nie pojawi się ona na Pulpicie, Porównaniach ani Mapie. Rozliczenie
        po cenniku głównej. To NIE to samo co „grupy jednostek" (tamte są tylko wizualne).
      </p>
      <p className="mt-1 text-xs text-amber-300/90">
        Uwaga: dotyczy nowych przeliczeń — żeby zadziałało wstecz, przelicz dany miesiąc ponownie.
      </p>

      {loading ? (
        <div className="mt-4 flex items-center gap-2 text-slate-400"><Loader2 className="animate-spin" size={16} /> Wczytywanie…</div>
      ) : (
        <div className="mt-4 space-y-2">
          {rows.length === 0 && <p className="text-sm text-slate-500">Brak scaleń. Dodaj pierwsze poniżej.</p>}
          {rows.map((r, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <select className="input sm:w-56" value={r.from} onChange={(e) => update(i, { from: e.target.value })}>
                <option value="">— podległa (znika) —</option>
                {options.map((u) => (
                  <option key={u.key} value={u.key}>{u.name}{u.name !== u.key ? ` (${u.key})` : ""}</option>
                ))}
              </select>
              <ArrowRight size={16} className="text-slate-500" />
              <select className="input sm:w-56" value={r.to} onChange={(e) => update(i, { to: e.target.value })}>
                <option value="">— główna (przejmuje) —</option>
                {options.map((u) => (
                  <option key={u.key} value={u.key}>{u.name}{u.name !== u.key ? ` (${u.key})` : ""}</option>
                ))}
              </select>
              <button className="btn-secondary !px-2 !py-1.5" onClick={() => removeRow(i)} title="Usuń">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          <button className="btn-secondary mt-1 text-sm" onClick={addRow}><Plus size={15} /> Dodaj scalenie</button>
        </div>
      )}
      {err && <p className="mt-2 text-sm text-red-300">{err}</p>}
    </div>
  );
}
