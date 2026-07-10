"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Loader2, Plus, Trash2, Save, Wallet, CheckCircle2,
  AlertTriangle, Clock, Pencil,
} from "lucide-react";
import { api, Receivable, Installment } from "@/lib/api";
import { toast } from "@/lib/toast";

function zl(n: number | null | undefined) {
  return (n ?? 0).toLocaleString("pl-PL", { style: "currency", currency: "PLN" });
}

type EditableInstallment = { id?: string; label: string; amount: string; due_date: string; note?: string };

const STATUS_OPTIONS = [
  { value: "wystawiona", label: "Wystawiona" },
  { value: "czesciowo_oplacona", label: "Częściowo opłacona" },
  { value: "oplacona", label: "Opłacona" },
  { value: "sporna", label: "Sporna" },
  { value: "odpisana", label: "Odpisana" },
];

export default function ReceivableDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [rec, setRec] = useState<Receivable | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editAmount, setEditAmount] = useState("");
  const [editDue, setEditDue] = useState("");
  const [editStatus, setEditStatus] = useState("wystawiona");
  const [editNote, setEditNote] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);

  const [items, setItems] = useState<EditableInstallment[]>([]);
  const [savingInstallments, setSavingInstallments] = useState(false);
  const [instError, setInstError] = useState<string | null>(null);

  const [payAmounts, setPayAmounts] = useState<Record<string, string>>({});

  function hydrate(r: Receivable) {
    setRec(r);
    setEditAmount(String(r.amount_due));
    setEditDue(r.due_date ?? "");
    setEditStatus(r.status);
    setEditNote(r.note ?? "");
    setItems(r.installments.map((i) => ({
      id: i.id, label: i.label ?? "", amount: String(i.amount), due_date: i.due_date ?? "", note: i.note ?? "",
    })));
  }

  async function load() {
    setError(null);
    try {
      const r = await api.windykacjaGet(id);
      hydrate(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, [id]);

  async function saveEdit() {
    if (!rec) return;
    setSavingEdit(true);
    try {
      const amt = parseFloat(editAmount.replace(",", "."));
      const r = await api.windykacjaEdit(rec.id, {
        amount_due: Number.isFinite(amt) ? amt : rec.amount_due,
        due_date: editDue || undefined,
        status: editStatus,
        note: editNote,
      });
      hydrate(r);
      toast("Zapisano zmiany.");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSavingEdit(false);
    }
  }

  const instSum = items.reduce((s, it) => s + (parseFloat(it.amount.replace(",", ".")) || 0), 0);
  const dueNum = rec ? Number(rec.amount_due) : 0;
  const balanced = Math.abs(instSum - dueNum) < 0.01;

  function addRow() {
    setItems((prev) => [...prev, { label: `Rata ${prev.length + 1}`, amount: "", due_date: "" }]);
  }
  function removeRow(idx: number) {
    setItems((prev) => prev.filter((_, i) => i !== idx));
  }
  function splitEqually(n: number) {
    if (!rec || n <= 0) return;
    const base = Math.floor((dueNum / n) * 100) / 100;
    const rows: EditableInstallment[] = Array.from({ length: n }, (_, i) => ({
      label: `Rata ${i + 1}`,
      amount: i === n - 1 ? (dueNum - base * (n - 1)).toFixed(2) : base.toFixed(2),
      due_date: "",
    }));
    setItems(rows);
  }

  async function saveInstallments() {
    if (!rec) return;
    setInstError(null);
    const parsed = items.map((it) => ({
      id: it.id, label: it.label, due_date: it.due_date || undefined, note: it.note,
      amount: parseFloat(it.amount.replace(",", ".")),
    }));
    if (parsed.some((p) => !Number.isFinite(p.amount) || p.amount <= 0)) {
      setInstError("Każda rata musi mieć prawidłową kwotę większą od zera.");
      return;
    }
    setSavingInstallments(true);
    try {
      const r = await api.windykacjaSetInstallments(rec.id, parsed);
      hydrate(r);
      toast("Zapisano harmonogram rat.");
    } catch (e: any) {
      setInstError(e.message);
    } finally {
      setSavingInstallments(false);
    }
  }

  async function payInstallment(inst: Installment) {
    if (!rec) return;
    const raw = payAmounts[inst.id];
    const amt = raw ? parseFloat(raw.replace(",", ".")) : (inst.amount - inst.paid_amount);
    if (!Number.isFinite(amt) || amt <= 0) return;
    try {
      const r = await api.windykacjaPayInstallment(rec.id, inst.id, amt);
      hydrate(r);
      setPayAmounts((p) => ({ ...p, [inst.id]: "" }));
      toast("Odnotowano wpłatę.");
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  async function payLumpSum(amt: number) {
    if (!rec) return;
    try {
      const r = await api.windykacjaPay(rec.id, amt);
      hydrate(r);
      toast("Odnotowano wpłatę.");
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (loading) return <div className="flex items-center gap-2 text-slate-400"><Loader2 className="animate-spin" size={16} /> Wczytywanie…</div>;
  if (error || !rec) return <p className="text-sm text-red-300">{error ?? "Nie znaleziono."}</p>;

  return (
    <div className="space-y-5">
      <button onClick={() => router.push("/windykacja")} className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-white">
        <ArrowLeft size={15} /> Wróć do listy
      </button>

      <div className="card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold">{rec.unit_name}</h1>
            <p className="text-sm text-slate-400">{rec.period ?? "bez okresu"} {rec.source_run_id ? "· z rozliczenia" : "· wpis ręczny"}</p>
          </div>
          {rec.is_overdue && (
            <span className="pill pill-bad"><AlertTriangle size={12} /> po terminie ({rec.days_overdue} dni)</span>
          )}
          {rec.status === "oplacona" && <span className="pill pill-ok"><CheckCircle2 size={12} /> opłacona</span>}
        </div>

        {!!rec.source_changed && (
          <div className="mt-3 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3.5 py-2.5 text-[13px] text-amber-200/90">
            Kwota z ostatniego przeliczenia jednostek zmieniła się (referencja: {zl(rec.source_amount)}), ale nie
            nadpisaliśmy Twojej ręcznej edycji. Zdecyduj, czy zaktualizować kwotę należną poniżej.
          </div>
        )}

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block text-slate-400">Kwota należna (zł)</span>
            <input className="input" value={editAmount} onChange={(e) => setEditAmount(e.target.value)} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-400">Termin płatności</span>
            <input className="input" type="date" value={editDue} onChange={(e) => setEditDue(e.target.value)} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-400">Status</span>
            <select className="input" value={editStatus} onChange={(e) => setEditStatus(e.target.value)}>
              {STATUS_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </label>
          <label className="text-sm sm:col-span-2 lg:col-span-1">
            <span className="mb-1 block text-slate-400">Notatka</span>
            <input className="input" value={editNote} onChange={(e) => setEditNote(e.target.value)} placeholder="np. ustalenia z klientem" />
          </label>
        </div>
        <button className="btn-primary mt-4" onClick={saveEdit} disabled={savingEdit}>
          {savingEdit ? <Loader2 className="animate-spin" size={16} /> : <Pencil size={16} />} Zapisz zmiany
        </button>

        <div className="mt-4 grid grid-cols-3 gap-3 border-t border-white/10 pt-4 text-sm">
          <div><span className="text-slate-400">Wpłacono</span><div className="font-semibold">{zl(rec.paid_amount)}</div></div>
          <div><span className="text-slate-400">Pozostało</span><div className="font-semibold">{zl(rec.remaining)}</div></div>
          <div><span className="text-slate-400">Referencja z rozliczenia</span><div className="font-semibold">{zl(rec.source_amount)}</div></div>
        </div>
      </div>

      {/* Prosta wpłata bez rat */}
      {rec.installments_count === 0 && rec.remaining > 0.01 && (
        <div className="card">
          <h2 className="text-base font-bold">Odnotuj wpłatę</h2>
          <p className="mt-1 text-[13px] text-slate-400">Bez podziału na raty — jedna kwota od razu zamyka lub pomniejsza saldo.</p>
          <button className="btn-secondary mt-3" onClick={() => payLumpSum(rec.remaining)}>
            <Wallet size={16} /> Zapłacono w całości ({zl(rec.remaining)})
          </button>
        </div>
      )}

      {/* Harmonogram rat */}
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold">Harmonogram spłat (raty)</h2>
          <div className="flex items-center gap-2">
            <button className="btn-secondary text-xs" onClick={() => splitEqually(2)}>Podziel na 2</button>
            <button className="btn-secondary text-xs" onClick={() => splitEqually(3)}>Podziel na 3</button>
            <button className="btn-secondary text-xs" onClick={addRow}><Plus size={14} /> Dodaj ratę</button>
          </div>
        </div>

        <div className="mt-3 space-y-2">
          {items.length === 0 && <p className="text-sm text-slate-500">Brak rat — cała kwota jest jedną należnością.</p>}
          {items.map((it, idx) => {
            const inst = rec.installments.find((i) => i.id === it.id);
            return (
              <div key={it.id ?? idx} className="soft space-y-2 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <input className="input sm:w-40" placeholder="Etykieta" value={it.label}
                    onChange={(e) => setItems((prev) => prev.map((p, i) => i === idx ? { ...p, label: e.target.value } : p))} />
                  <input className="input sm:w-32" placeholder="Kwota" value={it.amount}
                    onChange={(e) => setItems((prev) => prev.map((p, i) => i === idx ? { ...p, amount: e.target.value } : p))} />
                  <input className="input sm:w-40" type="date" value={it.due_date}
                    onChange={(e) => setItems((prev) => prev.map((p, i) => i === idx ? { ...p, due_date: e.target.value } : p))} />
                  {inst && <span className="pill pill-muted ml-1">{zl(inst.paid_amount)} / {zl(inst.amount)} wpłacono</span>}
                  <button className="btn-secondary ml-auto !px-2 !py-1.5" onClick={() => removeRow(idx)}
                    disabled={!!inst && inst.paid_amount > 0.01} title={inst && inst.paid_amount > 0.01 ? "Ma odnotowaną wpłatę — nie można usunąć" : "Usuń"}>
                    <Trash2 size={14} />
                  </button>
                </div>
                {inst && inst.amount - inst.paid_amount > 0.01 && (
                  <div className="flex items-center gap-2 pl-1">
                    <input className="input !w-32 !py-1.5 text-xs" placeholder={`do ${zl(inst.amount - inst.paid_amount)}`}
                      value={payAmounts[inst.id] ?? ""} onChange={(e) => setPayAmounts((p) => ({ ...p, [inst.id]: e.target.value }))} />
                    <button className="btn-secondary !py-1.5 text-xs" onClick={() => payInstallment(inst)}>
                      <Wallet size={13} /> Odnotuj wpłatę
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-3 flex items-center gap-2 text-sm">
          <span className={balanced ? "text-brand-accent2" : "text-amber-300"}>
            Rozpisano {instSum.toFixed(2)} zł / {dueNum.toFixed(2)} zł
            {!balanced && ` (różnica ${(instSum - dueNum).toFixed(2)} zł)`}
          </span>
        </div>
        {instError && <p className="mt-2 text-sm text-red-300">{instError}</p>}
        <button className="btn-primary mt-3" onClick={saveInstallments} disabled={savingInstallments || !balanced}>
          {savingInstallments ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />} Zapisz harmonogram
        </button>
        {!balanced && items.length > 0 && (
          <p className="mt-1 text-xs text-slate-500">Suma rat musi się zgadzać dokładnie z kwotą należną, żeby zapisać.</p>
        )}
      </div>

      {/* Historia */}
      <div className="card">
        <h2 className="flex items-center gap-2 text-base font-bold"><Clock size={16} /> Historia</h2>
        <div className="mt-3 space-y-2">
          {(!rec.history || rec.history.length === 0) && <p className="text-sm text-slate-500">Brak zmian.</p>}
          {rec.history?.map((h) => (
            <div key={h.id} className="soft px-3 py-2 text-[13px]">
              <span className="text-slate-500">{h.changed_at}</span> —{" "}
              <span className="font-semibold">{h.field}</span>{": "}
              {h.old_value ?? "—"} → {h.new_value ?? "—"}
              {h.reason && <span className="text-slate-400"> ({h.reason})</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
