"use client";

// Ustawienia modułu Windykacja: domyślny termin płatności + terminy per jednostka
// (dni). Samodzielny komponent — własny endpoint, auto-zapis, jak Teamup/Units.
import { useEffect, useMemo, useState } from "react";
import { AlarmClockCheck, Search, Loader2, Save, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";

export default function PaymentTermsSettings() {
  const [defaultDays, setDefaultDays] = useState(14);
  const [doctorCostDays, setDoctorCostDays] = useState(14);
  const [terms, setTerms] = useState<Record<string, number>>({});
  const [units, setUnits] = useState<{ name: string; key: string }[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.windykacjaPaymentTerms(), api.unitsList()])
      .then(([pt, u]) => {
        setDefaultDays(pt.default_days);
        setDoctorCostDays(pt.doctor_cost_days);
        setTerms(pt.terms);
        setUnits(u.units.map(({ name, key }) => ({ name, key })));
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  const shown = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const known = new Set(units.map((u) => u.key));
    // Jednostki z ostatniego rozliczenia + te, które mają już wpisany termin
    // (na wypadek jednostek spoza bieżącego pliku, np. z pliku Słownik).
    const extra = Object.keys(terms).filter((k) => !known.has(k)).map((k) => ({ name: k, key: k }));
    const all = [...units, ...extra];
    return f ? all.filter((u) => u.name.toLowerCase().includes(f) || u.key.includes(f)) : all;
  }, [units, terms, filter]);

  async function persist(nextTerms: Record<string, number>, nextDefault?: number, nextDoctorCost?: number) {
    setSaving(true); setErr(null); setMsg(null);
    try {
      await api.windykacjaSavePaymentTerms({
        default_days: nextDefault ?? defaultDays,
        doctor_cost_days: nextDoctorCost ?? doctorCostDays,
        terms: nextTerms,
      });
      setMsg("Zapisano.");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  function setUnitDays(key: string, days: number) {
    const next = { ...terms, [key]: days };
    setTerms(next);
    persist(next);
  }

  function saveDefault() {
    persist(terms, defaultDays);
  }

  function saveDoctorCostDays() {
    persist(terms, defaultDays, doctorCostDays);
  }

  return (
    <div className="card">
      <h2 className="flex items-center gap-2 text-base font-bold">
        <AlarmClockCheck size={18} className="text-brand-accent" /> Terminy płatności (Windykacja)
      </h2>
      <p className="mt-1 text-[13px] leading-relaxed text-slate-400">
        Ile dni od wystawienia należności ma jednostka na zapłatę. Wartości startowe wczytane z
        listy kontrahentów; możesz je zmienić dla każdej jednostki osobno.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-slate-400">Domyślny termin (dni), gdy jednostka nie ma własnego:</span>
          <input type="number" className="input !w-24" value={defaultDays}
            onChange={(e) => setDefaultDays(parseInt(e.target.value) || 0)} onBlur={saveDefault} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-slate-400">Założony termin zapłaty lekarzom (dni po końcu miesiąca, Cashflow):</span>
          <input type="number" className="input !w-24" value={doctorCostDays}
            onChange={(e) => setDoctorCostDays(parseInt(e.target.value) || 0)} onBlur={saveDoctorCostDays} />
        </label>
        <span className="ml-auto flex items-center gap-1.5 text-xs text-slate-400">
          {saving ? <><Loader2 className="animate-spin" size={14} /> Zapisywanie…</> : <><Save size={14} /> Zmiany zapisują się automatycznie</>}
        </span>
      </div>

      {loading ? (
        <div className="mt-4 flex items-center gap-2 text-slate-400"><Loader2 className="animate-spin" size={16} /> Wczytywanie…</div>
      ) : (
        <>
          <div className="mt-3 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={15} />
            <input className="input pl-9 sm:w-64" placeholder="Szukaj jednostki…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>

          {msg && <div className="mt-3 flex items-center gap-2 text-sm text-brand-accent2"><CheckCircle2 size={16} /> {msg}</div>}
          {err && <div className="mt-3 text-sm text-red-300">{err}</div>}

          <div className="mt-3 max-h-80 overflow-auto rounded-xl border border-white/10">
            {shown.map((u) => (
              <div key={u.key} className="flex items-center gap-3 border-b border-white/5 px-4 py-2 text-sm last:border-0 hover:bg-white/[0.03]">
                <span className="truncate">{u.name}</span>
                <div className="ml-auto flex items-center gap-1.5">
                  <input type="number" className="input !w-20 !py-1.5 text-right"
                    value={terms[u.key] ?? defaultDays}
                    onChange={(e) => setUnitDays(u.key, parseInt(e.target.value) || 0)} />
                  <span className="text-xs text-slate-500">dni</span>
                </div>
              </div>
            ))}
            {shown.length === 0 && <p className="px-4 py-3 text-sm text-slate-500">Brak pasujących pozycji.</p>}
          </div>
        </>
      )}
    </div>
  );
}
