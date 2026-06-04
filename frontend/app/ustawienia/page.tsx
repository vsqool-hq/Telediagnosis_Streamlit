"use client";

import { useEffect, useState } from "react";
import { Save, RotateCcw, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";

export default function UstawieniaPage() {
  const [settings, setSettings] = useState<any>(null);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    api.getSettings().then(({ settings }) => {
      setSettings(settings);
      setText(JSON.stringify(settings, null, 2));
    }).catch((e) => setError(e.message));
  }
  useEffect(load, []);

  function field(key: string, value: number) {
    setSettings((s: any) => {
      const next = { ...s, [key]: value };
      setText(JSON.stringify(next, null, 2));
      return next;
    });
  }

  async function save() {
    setMsg(null);
    setError(null);
    let payload: any;
    try {
      payload = JSON.parse(text);
    } catch {
      setError("Nieprawidłowy JSON — popraw treść w edytorze zaawansowanym.");
      return;
    }
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
    await api.resetSettings().catch((e) => setError(e.message));
    load();
    setMsg("Przywrócono ustawienia domyślne.");
  }

  if (!settings) return <div className="card">Wczytywanie…</div>;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Ustawienia silnika</h1>
        <p className="text-sm text-slate-400">
          Wartości używane przy rozliczeniach (priorytety, słowa kluczowe, kolory, liczba rdzeni).
        </p>
      </header>

      {msg && <div className="card border-brand-accent/50 text-brand-accent">{msg}</div>}
      {error && <div className="card border-red-500/40 text-red-300">{error}</div>}

      <div className="card grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="space-y-1.5">
          <span className="text-sm font-medium">Rdzenie — etap weryfikacji</span>
          <input type="number" min={1} max={32} className="input"
            value={settings.num_processes_verify}
            onChange={(e) => field("num_processes_verify", parseInt(e.target.value || "1"))} />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium">Rdzenie — etap rozliczeń</span>
          <input type="number" min={1} max={32} className="input"
            value={settings.num_processes_billing}
            onChange={(e) => field("num_processes_billing", parseInt(e.target.value || "1"))} />
        </label>
      </div>

      <div className="card space-y-3">
        <div className="flex items-center gap-2 text-amber-300">
          <AlertTriangle size={16} />
          <h2 className="text-sm font-semibold">Edytor zaawansowany (JSON)</h2>
        </div>
        <p className="text-xs text-slate-400">
          Pełna konfiguracja: słowniki priorytetów, mapy sufiksów, listy słów kluczowych MR, kolory raportu.
          Zmiany zapisz przyciskiem poniżej.
        </p>
        <textarea
          className="input h-96 font-mono text-xs"
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
        />
        <div className="flex gap-3">
          <button className="btn-primary" onClick={save}><Save size={18} /> Zapisz</button>
          <button className="btn-secondary" onClick={reset}><RotateCcw size={18} /> Przywróć domyślne</button>
        </div>
      </div>
    </div>
  );
}
