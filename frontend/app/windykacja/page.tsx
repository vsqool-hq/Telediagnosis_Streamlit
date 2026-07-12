"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlarmClockCheck, Search, Plus, X, Loader2, CheckCircle2, AlertTriangle,
  Wallet, CalendarClock, TrendingUp, Landmark, Trash2,
} from "lucide-react";
import { api, Receivable, WindykacjaSummary, ReceivableStatus } from "@/lib/api";
import { toast } from "@/lib/toast";

function zl(n: number | null | undefined) {
  return (n ?? 0).toLocaleString("pl-PL", { style: "currency", currency: "PLN" });
}

const STATUS_LABEL: Record<ReceivableStatus, string> = {
  wystawiona: "Wystawiona",
  czesciowo_oplacona: "Częściowo opłacona",
  oplacona: "Opłacona",
  sporna: "Sporna",
  odpisana: "Odpisana",
};

function statusPill(r: Receivable) {
  if (r.is_overdue) return <span className="pill pill-bad"><AlertTriangle size={12} /> po terminie ({r.days_overdue} dni)</span>;
  if (r.status === "oplacona") return <span className="pill pill-ok"><CheckCircle2 size={12} /> opłacona</span>;
  if (r.status === "czesciowo_oplacona") return <span className="pill pill-warn">częściowo opłacona</span>;
  if (r.status === "sporna") return <span className="pill pill-bad">sporna</span>;
  if (r.status === "odpisana") return <span className="pill pill-muted">odpisana</span>;
  return <span className="pill pill-muted">wystawiona</span>;
}

/* ---------- Formularz ręcznego dodania (np. zaległość historyczna) ---------- */
function AddManualForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [unitKey, setUnitKey] = useState("");
  const [unitName, setUnitName] = useState("");
  const [amount, setAmount] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [period, setPeriod] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setErr(null);
    const amt = parseFloat(amount.replace(",", "."));
    if (!unitKey.trim() || !Number.isFinite(amt) || amt <= 0) {
      setErr("Podaj jednostkę i prawidłową kwotę.");
      return;
    }
    setSaving(true);
    try {
      await api.windykacjaCreate({
        unit_key: unitKey.trim().toLowerCase(), unit_name: unitName.trim() || unitKey.trim(),
        amount_due: amt, due_date: dueDate || undefined, period: period || undefined,
        note: note.trim() || undefined,
      });
      toast("Dodano należność.");
      onSaved();
      onClose();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card mb-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold">Dodaj należność ręcznie</h2>
        <button className="btn-secondary !px-2 !py-1.5" onClick={onClose}><X size={15} /></button>
      </div>
      <p className="mt-1 text-[13px] text-slate-400">
        Do wpisania zaległości sprzed wdrożenia modułu albo pozycji spoza automatycznego rozliczenia.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <input className="input" placeholder="Klucz jednostki (np. kartuzy)" value={unitKey} onChange={(e) => setUnitKey(e.target.value)} />
        <input className="input" placeholder="Nazwa do wyświetlenia (opcjonalnie)" value={unitName} onChange={(e) => setUnitName(e.target.value)} />
        <input className="input" placeholder="Kwota (zł)" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <input className="input" type="date" placeholder="Termin płatności" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
        <input className="input" placeholder="Okres (YYYY-MM, opcjonalnie)" value={period} onChange={(e) => setPeriod(e.target.value)} />
        <input className="input" placeholder="Notatka (opcjonalnie)" value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      {err && <p className="mt-2 text-sm text-red-300">{err}</p>}
      <button className="btn-primary mt-4" onClick={save} disabled={saving}>
        {saving ? <Loader2 className="animate-spin" size={16} /> : <Plus size={16} />} Dodaj
      </button>
    </div>
  );
}

export default function WindykacjaPage() {
  const [receivables, setReceivables] = useState<Receivable[] | null>(null);
  const [summary, setSummary] = useState<WindykacjaSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [tileFilter, setTileFilter] = useState<null | "overdue" | "week" | "paid">(null);
  const [showPaid, setShowPaid] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  async function load() {
    setError(null);
    try {
      const [{ receivables }, s] = await Promise.all([api.windykacjaList(), api.windykacjaSummary()]);
      setReceivables(receivables);
      setSummary(s);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  const shown = useMemo(() => {
    let list = receivables ?? [];
    const f = filter.trim().toLowerCase();
    if (f) list = list.filter((r) => r.unit_name.toLowerCase().includes(f) || r.unit_key.includes(f));
    if (tileFilter === "overdue") list = list.filter((r) => r.is_overdue);
    if (tileFilter === "week") {
      const today = new Date(); const weekEnd = new Date(); weekEnd.setDate(today.getDate() + 7);
      list = list.filter((r) => !r.is_overdue && r.due_date && r.remaining > 0.01 &&
        new Date(r.due_date) <= weekEnd && new Date(r.due_date) >= today);
    }
    if (tileFilter === "paid") list = list.filter((r) => r.status === "oplacona");
    else if (!showPaid) list = list.filter((r) => r.status !== "oplacona");
    return list;
  }, [receivables, filter, tileFilter, showPaid]);

  useEffect(() => {
    if (!receivables) return;
    const ids = new Set(receivables.map((r) => r.id));
    setSelected((prev) => {
      const next = new Set<string>();
      prev.forEach((id) => { if (ids.has(id)) next.add(id); });
      return next.size === prev.size ? prev : next;
    });
  }, [receivables]);

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  const allShownSelected = shown.length > 0 && shown.every((r) => selected.has(r.id));

  function toggleAllShown() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allShownSelected) shown.forEach((r) => next.delete(r.id));
      else shown.forEach((r) => next.add(r.id));
      return next;
    });
  }

  async function deleteSelected() {
    if (selected.size === 0) return;
    if (!confirm(`Usunąć ${selected.size} zaznaczonych pozycji? Tej operacji nie można cofnąć.`)) return;
    setDeleting(true);
    try {
      const ids = Array.from(selected);
      const results = await Promise.allSettled(ids.map((id) => api.windykacjaDelete(id)));
      const failed = results.filter((res) => res.status === "rejected").length;
      await load();
      if (failed > 0) toast(`Nie udało się usunąć ${failed} z ${ids.length} pozycji.`, "error");
      else toast(`Usunięto ${ids.length} pozycji.`);
    } finally {
      setDeleting(false);
    }
  }

  async function markPaidFull(r: Receivable) {
    setBusyId(r.id);
    try {
      if (r.installments_count > 0) {
        toast("Ta należność ma harmonogram rat — odnotuj wpłatę przy konkretnej racie.", "error");
        return;
      }
      await api.windykacjaPay(r.id, r.remaining);
      toast("Odnotowano pełną wpłatę.");
      load();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="flex items-center gap-2 text-xl font-bold"><AlarmClockCheck className="text-brand-accent" size={22} /> Windykacja</h1>
        <p className="text-[13px] text-slate-400">
          Odświeża się automatycznie po każdym pełnym przeliczeniu jednostek.
        </p>
        <div className="ml-auto flex items-center gap-2">
          {selected.size > 0 && (
            <button className="btn-secondary !border-red-400/40 !text-red-300 hover:!border-red-400" onClick={deleteSelected} disabled={deleting}>
              {deleting ? <Loader2 className="animate-spin" size={16} /> : <Trash2 size={16} />} Usuń zaznaczone ({selected.size})
            </button>
          )}
          <button className="btn-primary" onClick={() => setShowAdd((v) => !v)}>
            <Plus size={16} /> Dodaj ręcznie
          </button>
        </div>
      </div>

      {showAdd && <AddManualForm onClose={() => setShowAdd(false)} onSaved={load} />}

      {summary && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <button onClick={() => setTileFilter(tileFilter === "overdue" ? null : "overdue")}
            className={`card text-left transition ${tileFilter === "overdue" ? "border-red-400/50" : ""}`}>
            <div className="flex items-center gap-2 text-[13px] text-slate-400"><AlertTriangle size={15} className="text-red-300" /> Przeterminowane</div>
            <div className="mt-1 text-xl font-extrabold text-red-300">{zl(summary.overdue_amount)}</div>
            <div className="text-xs text-slate-500">{summary.overdue_count} pozycji</div>
          </button>
          <button onClick={() => setTileFilter(tileFilter === "week" ? null : "week")}
            className={`card text-left transition ${tileFilter === "week" ? "border-brand-accent/50" : ""}`}>
            <div className="flex items-center gap-2 text-[13px] text-slate-400"><CalendarClock size={15} /> Do zapłaty w tym tygodniu</div>
            <div className="mt-1 text-xl font-extrabold">{zl(summary.due_this_week_amount)}</div>
            <div className="text-xs text-slate-500">{summary.due_this_week_count} pozycji</div>
          </button>
          <button onClick={() => setTileFilter(tileFilter === "paid" ? null : "paid")}
            className={`card text-left transition ${tileFilter === "paid" ? "border-brand-accent/50" : ""}`}>
            <div className="flex items-center gap-2 text-[13px] text-slate-400"><TrendingUp size={15} className="text-brand-accent2" /> Zapłacone w tym miesiącu</div>
            <div className="mt-1 text-xl font-extrabold text-brand-accent2">{zl(summary.paid_this_month_amount)}</div>
            <div className="text-xs text-slate-500">{summary.paid_this_month_count} pozycji</div>
          </button>
          <div className="card">
            <div className="flex items-center gap-2 text-[13px] text-slate-400"><Landmark size={15} /> Saldo całkowite</div>
            <div className="mt-1 text-xl font-extrabold">{zl(summary.total_balance)}</div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={15} />
          <input className="input pl-9 sm:w-72" placeholder="Szukaj jednostki…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        {tileFilter !== "paid" && (
          <label className="flex items-center gap-2 text-[13px] text-slate-400">
            <input type="checkbox" className="accent-brand-accent" checked={showPaid} onChange={(e) => setShowPaid(e.target.checked)} />
            Pokaż zapłacone
          </label>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-slate-400"><Loader2 className="animate-spin" size={16} /> Wczytywanie…</div>
      ) : error ? (
        <p className="text-sm text-red-300">{error}</p>
      ) : shown.length === 0 ? (
        <p className="card text-sm text-slate-400">Brak należności do pokazania.</p>
      ) : (
        <div className="card !p-0 overflow-hidden">
          <div className="max-h-[70vh] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[#0e3b49] text-left text-[12px] uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3 w-8">
                    <input type="checkbox" className="accent-brand-accent" checked={allShownSelected}
                      onChange={toggleAllShown} title="Zaznacz wszystko" />
                  </th>
                  <th className="px-4 py-3">Jednostka / miesiąc</th>
                  <th className="px-4 py-3 text-right">Należność</th>
                  <th className="px-4 py-3 text-right">Wpłacono</th>
                  <th className="px-4 py-3 text-right">Pozostało</th>
                  <th className="px-4 py-3">Termin</th>
                  <th className="px-4 py-3">Postęp</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => {
                  const pct = r.amount_due > 0 ? Math.min(100, Math.round((r.paid_amount / r.amount_due) * 100)) : 0;
                  const borderClass = r.is_overdue ? "border-l-2 border-l-red-400/70" : "border-l-2 border-l-transparent";
                  return (
                    <tr key={r.id} className={`group border-t border-white/5 hover:bg-white/[0.03] ${borderClass} ${selected.has(r.id) ? "bg-brand-accent/[0.06]" : ""}`}>
                      <td className="px-4 py-3">
                        <input type="checkbox" className="accent-brand-accent" checked={selected.has(r.id)}
                          onChange={() => toggleOne(r.id)} />
                      </td>
                      <td className="px-4 py-3">
                        <Link href={`/windykacja/${r.id}`} className="font-semibold hover:text-brand-accent2">
                          {r.unit_name}
                        </Link>
                        <div className="text-xs text-slate-500">
                          {r.period ?? "—"}
                          {!!r.source_changed && <span className="ml-2 pill pill-warn">kwota z rozliczenia się zmieniła</span>}
                          {!r.source_run_id && <span className="ml-2 pill pill-muted">ręczny wpis</span>}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right font-semibold">{zl(r.amount_due)}</td>
                      <td className="px-4 py-3 text-right text-slate-400">{zl(r.paid_amount)}</td>
                      <td className="px-4 py-3 text-right font-semibold">{zl(r.remaining)}</td>
                      <td className="px-4 py-3 text-slate-300">{r.due_date ?? "—"}</td>
                      <td className="px-4 py-3">
                        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-white/10">
                          <div className="h-full bg-brand-accent2" style={{ width: `${pct}%` }} />
                        </div>
                      </td>
                      <td className="px-4 py-3">{statusPill(r)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
                          {r.remaining > 0.01 && r.installments_count === 0 && (
                            <button className="btn-secondary !px-2.5 !py-1.5 text-xs" disabled={busyId === r.id}
                              onClick={() => markPaidFull(r)}>
                              {busyId === r.id ? <Loader2 className="animate-spin" size={13} /> : <Wallet size={13} />} Zapłacono
                            </button>
                          )}
                          <Link href={`/windykacja/${r.id}`} className="btn-secondary !px-2.5 !py-1.5 text-xs">Szczegóły</Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
