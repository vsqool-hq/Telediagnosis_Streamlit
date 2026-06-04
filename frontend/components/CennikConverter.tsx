"use client";

import { useState } from "react";
import {
  UploadCloud, Wand2, Download, Save, Loader2, CheckCircle2,
  AlertTriangle, XCircle, Copy,
} from "lucide-react";
import { api, CennikConversion } from "@/lib/api";

function Metric({ label, value, tone = "default" }: { label: string; value: string | number; tone?: "default" | "warn" | "error" | "ok" }) {
  const tones = {
    default: "text-slate-100",
    ok: "text-brand-accent",
    warn: "text-amber-300",
    error: "text-red-300",
  };
  return (
    <div className="rounded-xl border border-brand-border/60 bg-brand-bg/30 px-4 py-3">
      <p className={`text-xl font-bold ${tones[tone]}`}>{value}</p>
      <p className="text-xs text-slate-400">{label}</p>
    </div>
  );
}

function Collapsible({ title, count, tone, children }: { title: string; count: number; tone: "warn" | "error"; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  if (count === 0) return null;
  const color = tone === "error" ? "text-red-300" : "text-amber-300";
  return (
    <div className="rounded-xl border border-brand-border/60 bg-brand-bg/30">
      <button onClick={() => setOpen((o) => !o)} className={`flex w-full items-center gap-2 px-4 py-2.5 text-sm font-medium ${color}`}>
        {tone === "error" ? <XCircle size={16} /> : <AlertTriangle size={16} />}
        {title} ({count}) <span className="ml-auto text-xs text-slate-500">{open ? "ukryj" : "pokaż"}</span>
      </button>
      {open && <div className="max-h-60 overflow-auto border-t border-brand-border/60 px-4 py-2 text-xs text-slate-300">{children}</div>}
    </div>
  );
}

export default function CennikConverter() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [conv, setConv] = useState<CennikConversion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function convert() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setConv(null);
    setSaved(false);
    try {
      const res = await api.convertCennik(file);
      setConv(res);
      setLabel(res.source_name.replace(/\.(xlsx|xls)$/i, ""));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!conv) return;
    setSaving(true);
    setError(null);
    try {
      await api.saveConvertedCennik(conv.id, label, label.replace(/[^\w\-]+/g, "_") + ".csv");
      setSaved(true);
      setTimeout(() => window.location.reload(), 900);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const v = conv?.validation;

  return (
    <div className="card space-y-4">
      <div>
        <h2 className="flex items-center gap-2 font-semibold"><Wand2 size={18} className="text-brand-accent" /> Konwerter cennika zbiorczego</h2>
        <p className="text-sm text-slate-400">
          Wgraj szeroki Excel (badania w wierszach, jednostki w kolumnach). Aplikacja rozbije go na cennik
          3-kolumnowy (BADANIE;Jednostka;Cena), zwaliduje kwoty i pozwoli zapisać jako aktywny cennik.
        </p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <input type="file" accept=".xlsx,.xls" className="input sm:max-w-xs"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button className="btn-primary" disabled={!file || busy} onClick={convert}>
          {busy ? <Loader2 className="animate-spin" size={18} /> : <UploadCloud size={18} />}
          Wczytaj i konwertuj
        </button>
      </div>

      {error && <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-2.5 text-sm text-red-300">{error}</div>}

      {conv && v && (
        <div className="space-y-5">
          {/* Metryki */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            <Metric label="Wierszy" value={v.n_rows} tone="ok" />
            <Metric label="Badań" value={v.n_badania} />
            <Metric label="Jednostek" value={v.n_units} />
            <Metric label="Ceny 0 zł" value={v.n_zeros} tone={v.n_zeros ? "warn" : "default"} />
            <Metric label="Naprawione" value={v.n_repaired} tone={v.n_repaired ? "warn" : "default"} />
            <Metric label="Duplikaty" value={v.n_duplicates} tone={v.n_duplicates ? "error" : "ok"} />
            <Metric label="Błędy" value={v.n_errors} tone={v.n_errors ? "error" : "ok"} />
          </div>
          <p className="text-xs text-slate-400">
            Zakres cen: {v.price_min} – {v.price_max} zł. Pominięte wiersze (nagłówki/etykiety):{" "}
            {v.excluded_rows.length ? v.excluded_rows.join(", ") : "—"}.
          </p>

          {/* Ostrzeżenia */}
          <div className="space-y-2">
            <Collapsible title="Duplikaty (badanie + jednostka)" count={v.n_duplicates} tone="error">
              {v.duplicates.map((d, i) => <div key={i}>{d.badanie} — {d.jednostka}</div>)}
            </Collapsible>
            <Collapsible title="Wartości niemożliwe do odczytania" count={v.n_errors} tone="error">
              {v.errors.map((d, i) => <div key={i}>{d.badanie} — {d.jednostka}: „{d.wartosc}"</div>)}
            </Collapsible>
            <Collapsible title="Automatycznie naprawione kwoty" count={v.n_repaired} tone="warn">
              {v.repaired.map((d, i) => <div key={i}>{d.badanie} — {d.jednostka}: „{d.z}" → {d.na}</div>)}
            </Collapsible>
            <Collapsible title="Pozycje z ceną 0 zł (nieoferowane)" count={v.n_zeros} tone="warn">
              {v.zeros_sample.map((z, i) => <div key={i}>{z[0]} — {z[1]}</div>)}
              {v.n_zeros > v.zeros_sample.length && <div className="text-slate-500">… i {v.n_zeros - v.zeros_sample.length} więcej</div>}
            </Collapsible>
          </div>

          {/* Podgląd źródła */}
          <div>
            <p className="mb-2 text-sm font-semibold">Podgląd wczytanego zestawienia (fragment)</p>
            <div className="overflow-x-auto rounded-xl border border-brand-border/60">
              <table className="w-full text-xs">
                <thead className="bg-brand-bg/40 text-slate-400">
                  <tr>{conv.source_preview.header.map((h, i) => <th key={i} className="px-2 py-1.5 text-left font-medium">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {conv.source_preview.rows.map((r, i) => (
                    <tr key={i} className="border-t border-brand-border/30">
                      {r.map((c, j) => <td key={j} className={`px-2 py-1 ${j === 0 ? "font-medium text-slate-200" : "text-slate-400"}`}>{c}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Podgląd wyniku */}
          <div>
            <p className="mb-2 text-sm font-semibold">Podgląd wyniku (pierwsze 50 wierszy)</p>
            <div className="max-h-64 overflow-auto rounded-xl border border-brand-border/60">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-brand-bg/60 text-slate-400">
                  <tr><th className="px-3 py-1.5 text-left font-medium">BADANIE</th><th className="px-3 py-1.5 text-left font-medium">Jednostka</th><th className="px-3 py-1.5 text-right font-medium">Cena</th></tr>
                </thead>
                <tbody>
                  {conv.result_preview.map((r, i) => (
                    <tr key={i} className="border-t border-brand-border/30">
                      <td className="px-3 py-1 text-slate-200">{r.badanie}</td>
                      <td className="px-3 py-1 text-slate-400">{r.jednostka}</td>
                      <td className="px-3 py-1 text-right">{r.cena} zł</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Akcje */}
          <div className="flex flex-col gap-3 border-t border-brand-border/60 pt-4 sm:flex-row sm:items-center">
            <input className="input sm:flex-1" placeholder="Nazwa/opis wersji cennika" value={label} onChange={(e) => setLabel(e.target.value)} />
            <a className="btn-secondary" href={api.convertedDownloadUrl(conv.id)}><Download size={18} /> Pobierz CSV</a>
            <button className="btn-primary" disabled={saving || saved} onClick={save}>
              {saved ? <CheckCircle2 size={18} /> : saving ? <Loader2 className="animate-spin" size={18} /> : <Save size={18} />}
              {saved ? "Zapisano — odświeżam…" : "Zapisz jako cennik"}
            </button>
          </div>
          {v.n_duplicates > 0 && (
            <p className="flex items-center gap-2 text-xs text-red-300"><Copy size={14} /> Uwaga: wykryto duplikaty — przed zapisem warto poprawić plik źródłowy.</p>
          )}
        </div>
      )}
    </div>
  );
}
