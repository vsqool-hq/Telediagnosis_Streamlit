"use client";

import { useState } from "react";
import { Cloud, Laptop, RefreshCw, AlertTriangle } from "lucide-react";
import { CLOUD_BASE, LOCAL_BASE, getApiBase, setApiBase } from "@/lib/api";

type Mode = "cloud" | "local" | "custom";

function currentMode(): Mode {
  const base = getApiBase();
  if (base === CLOUD_BASE) return "cloud";
  if (/^https?:\/\/(localhost|127\.0\.0\.1)/.test(base)) return "local";
  return "custom";
}

export default function BackendSwitcher({ compact = false }: { compact?: boolean }) {
  const [mode, setMode] = useState<Mode>(currentMode());
  const [custom, setCustom] = useState(mode === "custom" ? getApiBase() : "");

  function apply(next: Mode, customUrl?: string) {
    const url = next === "cloud" ? CLOUD_BASE : next === "local" ? LOCAL_BASE : (customUrl ?? custom).trim();
    if (next === "custom" && !url) return;
    setApiBase(url);
    window.location.reload(); // czysty restart: re-inicjalizacja API + logowania
  }

  const Btn = ({ m, icon, label }: { m: Mode; icon: React.ReactNode; label: string }) => (
    <button
      onClick={() => { setMode(m); if (m !== "custom") apply(m); }}
      className={`flex flex-1 items-center justify-center gap-2 rounded-xl border px-3 py-2.5 text-sm font-semibold transition ${
        mode === m ? "border-brand-accent/60 bg-brand-accent/15 text-brand-accent2" : "border-white/15 bg-white/[0.03] text-slate-300 hover:border-brand-accent/40"
      }`}
    >
      {icon} {label}
    </button>
  );

  return (
    <div className={compact ? "space-y-2" : "card space-y-3"}>
      {!compact && (
        <div>
          <h2 className="text-base font-bold">Silnik obliczeń (backend)</h2>
          <p className="mt-1 text-[13px] text-slate-400">
            Wybierz, gdzie liczą się rozliczenia: w <b>chmurze (Fly)</b> czy na <b>tym komputerze</b>
            (szybciej, za darmo, bez limitów — wymaga uruchomionego lokalnego backendu).
          </p>
        </div>
      )}
      <div className="flex gap-2">
        <Btn m="cloud" icon={<Cloud size={16} />} label="Chmura (Fly)" />
        <Btn m="local" icon={<Laptop size={16} />} label="Ten komputer" />
      </div>

      {mode === "custom" && (
        <div className="flex gap-2">
          <input className="input" placeholder="https://adres-backendu" value={custom}
            onChange={(e) => setCustom(e.target.value)} />
          <button className="btn-primary" onClick={() => apply("custom")}><RefreshCw size={16} /> Ustaw</button>
        </div>
      )}

      {!compact && (
        <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-3.5 py-2.5 text-[12.5px] text-amber-200/90">
          <p className="flex items-center gap-1.5 font-semibold"><AlertTriangle size={14} /> Zanim wybierzesz „Ten komputer":</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            <li>musi działać lokalny backend (uruchom w terminalu: <code className="rounded bg-black/30 px-1">cd backend &amp;&amp; uvicorn app.main:app --port 8080</code>),</li>
            <li>dane (słownik, cennik, historia) są <b>osobne</b> dla chmury i komputera,</li>
            <li>najlepiej w przeglądarce <b>Chrome</b>; gdyby zablokowała połączenie ze strony https, otwórz aplikację lokalnie (<code className="rounded bg-black/30 px-1">localhost:3000</code>).</li>
          </ul>
        </div>
      )}
      <p className="text-[12px] text-slate-500">Aktualnie: <b className="text-slate-300">{getApiBase()}</b></p>
    </div>
  );
}
