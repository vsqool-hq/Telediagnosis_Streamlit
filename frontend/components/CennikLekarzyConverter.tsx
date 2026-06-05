"use client";

import { useState } from "react";
import { UploadCloud, Wand2, Download, Save, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import { api, DoctorConversion } from "@/lib/api";

function Metric({ label, value, tone = "default" }: { label: string; value: string | number; tone?: "default" | "warn" | "ok" }) {
  const tones = { default: "text-slate-100", ok: "text-brand-accent2", warn: "text-amber-300" };
  return (
    <div className="soft px-4 py-3">
      <p className={`text-xl font-extrabold ${tones[tone]}`}>{value}</p>
      <p className="text-xs text-slate-400">{label}</p>
    </div>
  );
}

export default function CennikLekarzyConverter() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [conv, setConv] = useState<DoctorConversion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showNonstd, setShowNonstd] = useState(false);

  async function convert() {
    if (!file) return;
    setBusy(true); setError(null); setConv(null); setSaved(false);
    try {
      const res = await api.convertCennikLekarzy(file);
      setConv(res);
      setLabel(res.source_name.replace(/\.(xlsx|xls)$/i, ""));
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  async function save() {
    if (!conv) return;
    setSaving(true); setError(null);
    try {
      await api.saveConvertedCennikLekarzy(conv.id, label, label.replace(/[^\w\-]+/g, "_") + ".csv");
      setSaved(true);
      setTimeout(() => window.location.reload(), 900);
    } catch (e: any) { setError(e.message); } finally { setSaving(false); }
  }

  const v = conv?.validation;

  return (
    <div className="card space-y-5">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-accent/15 text-brand-accent">
          <Wand2 size={20} />
        </div>
        <div>
          <h2 className="text-base font-bold">Konwerter cennika lekarzy</h2>
          <p className="text-[13px] text-slate-400">
            Wgraj skoroszyt „ZOBOWIĄZANIA LEKARZY" (każda zakładka = lekarz). Aplikacja weźmie
            najnowszy aneks (skrajnie prawy blok stawek) i rozbije go na cennik 3-kolumnowy
            (Lekarz;Kategoria;Cena), gotowy do zapisania jako aktywny cennik lekarzy.
          </p>
        </div>
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
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Metric label="Stawek" value={v.n_rows} tone="ok" />
            <Metric label="Lekarzy" value={v.n_doctors} />
            <Metric label="Kategorii" value={v.n_categories} />
            <Metric label="Stawki 0 zł" value={v.n_zeros} tone={v.n_zeros ? "warn" : "default"} />
            <Metric label="Nietypowe" value={v.n_nonstandard} tone={v.n_nonstandard ? "warn" : "default"} />
            <Metric label="Bez stawek" value={v.n_doctors_empty} tone={v.n_doctors_empty ? "warn" : "ok"} />
          </div>
          <p className="text-xs text-slate-400">
            Zakres stawek: {v.price_min} – {v.price_max} zł. Pominięte zakładki: {v.skipped_sheets.join(", ") || "—"}.
          </p>

          {v.n_nonstandard > 0 && (
            <div className="soft">
              <button onClick={() => setShowNonstd((o) => !o)}
                className="flex w-full items-center gap-2 px-4 py-2.5 text-sm font-semibold text-amber-300">
                <AlertTriangle size={16} /> Nietypowe kategorie do przeglądu ({v.n_nonstandard})
                <span className="ml-auto text-xs text-slate-500">{showNonstd ? "ukryj" : "pokaż"}</span>
              </button>
              {showNonstd && (
                <div className="max-h-56 overflow-auto border-t border-white/10 px-4 py-2 text-xs text-slate-300">
                  {v.nonstandard.map((n, i) => <div key={i}>{n.lekarz}: „{n.kategoria}"</div>)}
                </div>
              )}
            </div>
          )}

          <div>
            <p className="mb-2 text-[13px] font-semibold">Podgląd wyniku (pierwsze wiersze)</p>
            <div className="soft max-h-64 overflow-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-brand-surface text-slate-400">
                  <tr><th className="px-3 py-2 text-left">Lekarz</th><th className="px-3 py-2 text-left">Kategoria</th><th className="px-3 py-2 text-right">Stawka</th></tr>
                </thead>
                <tbody>
                  {conv.result_preview.map((r, i) => (
                    <tr key={i} className="border-t border-white/10">
                      <td className="px-3 py-1.5">{r.lekarz}</td>
                      <td className="px-3 py-1.5 text-slate-400">{r.kategoria}</td>
                      <td className="px-3 py-1.5 text-right">{r.cena} zł</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="flex flex-col gap-3 border-t border-white/10 pt-4 sm:flex-row sm:items-center">
            <input className="input sm:flex-1" placeholder="Nazwa/opis wersji" value={label} onChange={(e) => setLabel(e.target.value)} />
            <a className="btn-secondary" href={api.convertedLekarzyDownloadUrl(conv.id)}><Download size={18} /> Pobierz CSV</a>
            <button className="btn-primary" disabled={saving || saved} onClick={save}>
              {saved ? <CheckCircle2 size={18} /> : saving ? <Loader2 className="animate-spin" size={18} /> : <Save size={18} />}
              {saved ? "Zapisano — odświeżam…" : "Zapisz jako cennik lekarzy"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
