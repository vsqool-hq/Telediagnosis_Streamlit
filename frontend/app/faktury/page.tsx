"use client";

import { useEffect, useMemo, useState } from "react";
import {
  FileSpreadsheet, Download, Loader2, AlertTriangle, CheckCircle2,
  Plus, Trash2, Search, Save, CalendarClock, Link2, X,
} from "lucide-react";
import { api, InvoiceMonth, InvoiceUnit, InvoicePreview } from "@/lib/api";
import { toast } from "@/lib/toast";

function zl(n: number | null | undefined) {
  return (n ?? 0).toLocaleString("pl-PL", { style: "currency", currency: "PLN" });
}

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function FakturyPage() {
  const [tab, setTab] = useState<"wystaw" | "slownik">("wystaw");
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Faktury</h1>
        <p className="text-sm text-slate-400">
          Wystawianie zbiorczego pliku importowego (SaldeoSMART) z rozbiciem każdej jednostki na pozycje
          rozliczonych badań. Dane nabywców i terminy płatności trzymane są w Słowniku jednostek.
        </p>
      </header>

      <div className="flex gap-2">
        <button
          className={tab === "wystaw" ? "btn-primary" : "btn-secondary"}
          onClick={() => setTab("wystaw")}
        >
          <FileSpreadsheet size={18} /> Wystaw faktury
        </button>
        <button
          className={tab === "slownik" ? "btn-primary" : "btn-secondary"}
          onClick={() => setTab("slownik")}
        >
          <CalendarClock size={18} /> Słownik jednostek
        </button>
      </div>

      {tab === "wystaw" ? <WystawTab /> : <SlownikTab />}
    </div>
  );
}

// ---------------------------------------------------------------------------
function WystawTab() {
  const [months, setMonths] = useState<InvoiceMonth[]>([]);
  const [period, setPeriod] = useState<string>("");
  const [issueDate, setIssueDate] = useState<string>(todayISO());
  const [preview, setPreview] = useState<InvoicePreview | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [loadingPrev, setLoadingPrev] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    api.invoicesMonths()
      .then((r) => {
        setMonths(r.months);
        if (r.months.length) setPeriod(r.months[0].period);
      })
      .catch((e) => toast(e.message, "error"));
  }, []);

  const selected = useMemo(() => months.find((m) => m.period === period), [months, period]);

  useEffect(() => {
    if (!selected) { setPreview(null); return; }
    setLoadingPrev(true);
    setOverrides({});
    api.invoicesPreview(selected.job_id)
      .then(setPreview)
      .catch((e) => { setPreview(null); toast(e.message, "error"); })
      .finally(() => setLoadingPrev(false));
  }, [selected]);

  async function generate() {
    if (!selected) return;
    setGenerating(true);
    try {
      const clean: Record<string, string> = {};
      for (const [k, v] of Object.entries(overrides)) if (v && v.trim()) clean[k] = v.trim();
      const blob = await api.invoicesGenerate({
        job_id: selected.job_id, issue_date: issueDate, overrides: clean,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Faktury_${selected.period}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast("Plik faktur wygenerowany.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="card space-y-4">
        <div className="flex flex-wrap items-end gap-5">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-slate-400">Przeliczony miesiąc</span>
            <select className="input !w-52" value={period} onChange={(e) => setPeriod(e.target.value)}>
              {months.length === 0 && <option value="">— brak rozliczeń —</option>}
              {months.map((m) => (
                <option key={m.period} value={m.period}>
                  {m.period}{m.revenue != null ? ` · ${zl(m.revenue)}` : ""}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-slate-400">Data wystawienia (dla wszystkich)</span>
            <input type="date" className="input !w-44" value={issueDate}
              onChange={(e) => setIssueDate(e.target.value)} />
          </label>

          <div className="flex flex-col gap-1 text-sm">
            <span className="text-slate-400">Data dostawy (koniec miesiąca)</span>
            <span className="input !w-44 !py-1.5 opacity-70">{selected?.delivery_date || "—"}</span>
          </div>

          <button className="btn-primary ml-auto" onClick={generate}
            disabled={!selected || generating || !issueDate}>
            {generating ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
            Wystaw faktury
          </button>
        </div>
        <p className="text-xs text-slate-500">
          Termin płatności liczony automatycznie: data wystawienia + termin [dni] ze Słownika jednostek.
          Dla wybranych jednostek możesz ustawić inną datę wystawienia w kolumnie „Wyjątek — inna data".
        </p>
      </div>

      {loadingPrev && (
        <div className="card flex items-center gap-2 text-slate-400">
          <Loader2 size={18} className="animate-spin" /> Wczytuję podgląd…
        </div>
      )}

      {preview && !loadingPrev && (
        <>
          {preview.missing_slownik.length > 0 && (
            <div className="card border border-amber-500/40 bg-amber-500/10 text-amber-200">
              <div className="flex items-center gap-2 font-semibold">
                <AlertTriangle size={18} /> {preview.missing_slownik.length} jednostek bez danych w Słowniku
              </div>
              <p className="mt-1 text-sm text-amber-100/80">
                Faktury powstaną, ale bez pełnej nazwy/adresu (SaldeoSMART uzupełni po nazwie skróconej, jeśli
                kontrahent już istnieje). Uzupełnij dane w zakładce „Słownik jednostek": {preview.missing_slownik.join(", ")}
              </p>
            </div>
          )}

          <div className="card">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold">Podgląd — {preview.count} faktur do wystawienia</h2>
              <span className="text-sm text-slate-400">
                Razem: {zl(preview.units.reduce((s, u) => s + u.total, 0))}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-400">
                    <th className="py-2 pr-3">Jednostka</th>
                    <th className="py-2 pr-3 text-right">Pozycji</th>
                    <th className="py-2 pr-3 text-right">WSPARCIE</th>
                    <th className="py-2 pr-3 text-right">Wartość faktury</th>
                    <th className="py-2 pr-3">Wyjątek — inna data wystawienia</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.units.map((u) => (
                    <tr key={u.system_name} className="border-t border-white/5">
                      <td className="py-1.5 pr-3">
                        <span className="font-medium">{u.system_name}</span>
                        {!u.in_slownik && (
                          <span className="ml-2 text-xs text-amber-300">(brak w Słowniku)</span>
                        )}
                        {u.merged && u.merged.length > 0 && (
                          <span className="ml-2 inline-flex items-center gap-1 text-xs text-sky-300">
                            <Link2 size={12} /> + {u.merged.join(", ")}
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 pr-3 text-right">{u.positions}</td>
                      <td className="py-1.5 pr-3 text-right">{u.wsparcie ? zl(u.wsparcie) : "—"}</td>
                      <td className="py-1.5 pr-3 text-right">{zl(u.total)}</td>
                      <td className="py-1.5 pr-3">
                        <input type="date" className="input !w-40 !py-1"
                          value={overrides[u.system_name] || ""}
                          onChange={(e) => setOverrides((o) => ({ ...o, [u.system_name]: e.target.value }))} />
                      </td>
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

// ---------------------------------------------------------------------------
const EMPTY_UNIT: InvoiceUnit = {
  system_name: "", full_name: "", address: "", postal_code: "", city: "",
  payment_term_days: 14, alt_name: "", subunits: [],
};

// Wybór podjednostek (innych nazw skróconych) łączonych na TĘ SAMĄ fakturę.
function SubunitsPicker({
  value, candidates, onChange,
}: { value: string[]; candidates: string[]; onChange: (v: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return candidates.filter((c) => !s || c.toLowerCase().includes(s));
  }, [candidates, q]);
  function toggle(name: string) {
    onChange(value.includes(name) ? value.filter((x) => x !== name) : [...value, name]);
  }
  return (
    <div className="relative">
      <button type="button" className="btn-secondary !py-1 !px-2 !text-xs"
        onClick={() => setOpen((o) => !o)}>
        <Link2 size={13} /> {value.length ? `${value.length} podjedn.` : "Dodaj…"}
      </button>
      {value.length > 0 && (
        <div className="mt-1 flex max-w-56 flex-wrap gap-1">
          {value.map((v) => (
            <span key={v} className="inline-flex items-center gap-1 rounded bg-white/10 px-1.5 py-0.5 text-[10px]">
              {v}
              <button type="button" className="text-slate-400 hover:text-red-300" onClick={() => toggle(v)}>
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
      )}
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute z-20 mt-1 max-h-64 w-60 overflow-auto rounded border border-white/10 bg-slate-800 p-2 shadow-xl">
            <input className="input !mb-2 !w-full !py-1 !text-xs" placeholder="Szukaj jednostki…"
              value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
            {filtered.map((c) => (
              <label key={c} className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs hover:bg-white/5">
                <input type="checkbox" checked={value.includes(c)} onChange={() => toggle(c)} />
                {c}
              </label>
            ))}
            {filtered.length === 0 && <div className="px-1 py-2 text-xs text-slate-500">brak jednostek</div>}
          </div>
        </>
      )}
    </div>
  );
}

function SlownikTab() {
  const [units, setUnits] = useState<InvoiceUnit[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.invoicesUnits()
      .then((r) => setUnits(r.units))
      .catch((e) => toast(e.message, "error"))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return units;
    return units.filter((u) =>
      u.system_name.toLowerCase().includes(s) || u.full_name.toLowerCase().includes(s) ||
      u.city.toLowerCase().includes(s));
  }, [units, q]);

  function update(idx: number, field: keyof InvoiceUnit, value: string) {
    setUnits((arr) => {
      const copy = [...arr];
      const real = arr.indexOf(filtered[idx]);
      if (real < 0) return arr;
      copy[real] = {
        ...copy[real],
        [field]: field === "payment_term_days" ? (parseInt(value, 10) || 0) : value,
      };
      return copy;
    });
  }

  function patchUnit(u: InvoiceUnit, patch: Partial<InvoiceUnit>) {
    setUnits((arr) => arr.map((x) => (x === u ? { ...x, ...patch } : x)));
  }

  function addUnit() {
    setUnits((arr) => [{ ...EMPTY_UNIT }, ...arr]);
    setQ("");
  }

  function removeUnit(u: InvoiceUnit) {
    setUnits((arr) => arr.filter((x) => x !== u));
  }

  async function save() {
    const bad = units.find((u) => !u.system_name.trim());
    if (bad) { toast("Każda jednostka musi mieć nazwę systemową.", "error"); return; }
    setSaving(true);
    try {
      const r = await api.invoicesSaveUnits(units);
      toast(`Zapisano Słownik (${r.count} jednostek).`);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input className="input !w-64 !pl-9" placeholder="Szukaj jednostki…"
            value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <button className="btn-secondary" onClick={addUnit}><Plus size={18} /> Dodaj jednostkę</button>
        <span className="text-sm text-slate-400">{units.length} jednostek</span>
        <button className="btn-primary ml-auto" onClick={save} disabled={saving}>
          {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />} Zapisz Słownik
        </button>
      </div>

      <p className="flex items-center gap-1.5 text-xs text-slate-400">
        <Link2 size={13} className="text-sky-300" />
        <span>
          <b className="text-slate-300">Podjednostki</b>: gdy kilka nazw skróconych to ten sam kontrahent,
          dodaj je do jednostki-rodzica — trafią na <b className="text-slate-300">jedną wspólną fakturę</b>
          {" "}(pozycje sklejone, WSPARCIE zsumowane), zamiast osobnych faktur.
        </span>
      </p>

      {loading ? (
        <div className="flex items-center gap-2 text-slate-400"><Loader2 size={18} className="animate-spin" /> Wczytuję…</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400">
                <th className="py-2 pr-2">Nazwa systemowa</th>
                <th className="py-2 pr-2">Pełna nazwa (nabywca)</th>
                <th className="py-2 pr-2">Adres</th>
                <th className="py-2 pr-2">Kod</th>
                <th className="py-2 pr-2">Miejscowość</th>
                <th className="py-2 pr-2 text-right">Termin [dni]</th>
                <th className="py-2 pr-2">Podjednostki (jedna faktura)</th>
                <th className="py-2 pr-2"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u, i) => (
                <tr key={i} className="border-t border-white/5 align-top">
                  <td className="py-1 pr-2">
                    <input className="input !w-36 !py-1 !text-xs" value={u.system_name}
                      onChange={(e) => update(i, "system_name", e.target.value)} />
                  </td>
                  <td className="py-1 pr-2">
                    <input className="input !w-80 !py-1 !text-xs" value={u.full_name}
                      onChange={(e) => update(i, "full_name", e.target.value)} />
                  </td>
                  <td className="py-1 pr-2">
                    <input className="input !w-48 !py-1 !text-xs" value={u.address}
                      onChange={(e) => update(i, "address", e.target.value)} />
                  </td>
                  <td className="py-1 pr-2">
                    <input className="input !w-20 !py-1 !text-xs" value={u.postal_code}
                      onChange={(e) => update(i, "postal_code", e.target.value)} />
                  </td>
                  <td className="py-1 pr-2">
                    <input className="input !w-40 !py-1 !text-xs" value={u.city}
                      onChange={(e) => update(i, "city", e.target.value)} />
                  </td>
                  <td className="py-1 pr-2 text-right">
                    <input type="number" min={0} className="input !w-16 !py-1 !text-xs text-right"
                      value={u.payment_term_days}
                      onChange={(e) => update(i, "payment_term_days", e.target.value)} />
                  </td>
                  <td className="py-1 pr-2">
                    <SubunitsPicker
                      value={u.subunits || []}
                      candidates={units.filter((x) => x !== u && x.system_name.trim())
                        .map((x) => x.system_name).sort((a, b) => a.localeCompare(b))}
                      onChange={(v) => patchUnit(u, { subunits: v })} />
                  </td>
                  <td className="py-1 pr-2">
                    <button className="text-slate-500 hover:text-red-400" title="Usuń"
                      onClick={() => removeUnit(u)}><Trash2 size={16} /></button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={8} className="py-4 text-center text-slate-500">Brak jednostek.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <p className="flex items-center gap-2 text-xs text-slate-500">
        <CheckCircle2 size={14} /> Termin płatności jest współdzielony z Windykacją (jedno źródło prawdy).
      </p>
    </div>
  );
}
