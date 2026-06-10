"use client";

import { useEffect, useState } from "react";
import { Cloud, Laptop, RefreshCw, AlertTriangle, CheckCircle2, DownloadCloud, Loader2 } from "lucide-react";
import { CLOUD_BASE, LOCAL_BASE, getApiBase, setApiBase, isLocalBackend, api, SyncResult } from "@/lib/api";

type Mode = "cloud" | "local" | "custom";
const SYNC_PENDING = "teledag_sync_pending";
const KIND_LABEL: Record<string, string> = { wzorcowe: "słownik", cennik: "cennik", cennik_lekarzy: "cennik lekarzy" };

function currentMode(): Mode {
  const base = getApiBase();
  if (base === CLOUD_BASE) return "cloud";
  if (/^https?:\/\/(localhost|127\.0\.0\.1)/.test(base)) return "local";
  return "custom";
}

export default function BackendSwitcher({ compact = false }: { compact?: boolean }) {
  const [mode, setMode] = useState<Mode>(currentMode());
  const [custom, setCustom] = useState(mode === "custom" ? getApiBase() : "");
  const [syncing, setSyncing] = useState(false);
  const [syncRes, setSyncRes] = useState<SyncResult | null>(null);
  const [syncErr, setSyncErr] = useState<string | null>(null);
  const local = isLocalBackend();

  async function doSync() {
    setSyncing(true); setSyncErr(null); setSyncRes(null);
    try {
      setSyncRes(await api.syncFromCloud());
    } catch (e: any) {
      setSyncErr(e.message);
    } finally {
      setSyncing(false);
    }
  }

  // Auto-synchronizacja zaraz po przełączeniu na „Ten komputer".
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (local && window.localStorage.getItem(SYNC_PENDING)) {
      window.localStorage.removeItem(SYNC_PENDING);
      doSync();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function apply(next: Mode, customUrl?: string) {
    const url = next === "cloud" ? CLOUD_BASE : next === "local" ? LOCAL_BASE : (customUrl ?? custom).trim();
    if (next === "custom" && !url) return;
    // Po przełączeniu na lokalny — oznacz, by po przeładowaniu pobrać pliki z chmury.
    if (next !== "cloud") window.localStorage.setItem(SYNC_PENDING, "1");
    else window.localStorage.removeItem(SYNC_PENDING);
    setApiBase(url);
    window.location.reload();
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

      {/* Synchronizacja plików z chmury — gdy liczymy lokalnie */}
      {local && !compact && (
        <div className="soft space-y-2 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <DownloadCloud size={16} className="text-brand-accent" />
            <span className="text-[13px] font-semibold">Pliki z chmury (słownik, cennik, cennik lekarzy)</span>
            <button className="btn-secondary ml-auto px-3 py-1.5 text-xs" disabled={syncing} onClick={doSync}>
              {syncing ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
              {syncing ? "Pobieram…" : "Synchronizuj z chmury"}
            </button>
          </div>
          {syncRes && (
            <div className="text-[12.5px] text-slate-300">
              {Object.entries(syncRes.synced).map(([k, v]) => (
                <div key={k} className="flex items-center gap-1.5">
                  {v ? <CheckCircle2 size={13} className="text-brand-accent2" /> : <AlertTriangle size={13} className="text-amber-300" />}
                  {KIND_LABEL[k] || k}: {v ? <span className="text-slate-400">{v}</span> : <span className="text-amber-300">brak aktywnej wersji w chmurze</span>}
                </div>
              ))}
              {Object.entries(syncRes.errors).map(([k, e]) => (
                <div key={k} className="text-red-300">{KIND_LABEL[k] || k}: {e}</div>
              ))}
            </div>
          )}
          {syncErr && <p className="text-[12.5px] text-red-300">Nie udało się pobrać z chmury: {syncErr}. Sprawdź, czy chmura działa i czy hasło jest poprawne.</p>}
        </div>
      )}

      {!compact && (
        <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-3.5 py-2.5 text-[12.5px] text-amber-200/90">
          <p className="flex items-center gap-1.5 font-semibold"><AlertTriangle size={14} /> „Ten komputer" — pamiętaj:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            <li>musi działać lokalny backend (<code className="rounded bg-black/30 px-1">uvicorn app.main:app --port 8080</code> w katalogu <code className="rounded bg-black/30 px-1">backend</code>),</li>
            <li>po przełączeniu pliki z chmury pobierają się automatycznie (możesz też kliknąć „Synchronizuj"),</li>
            <li>najlepiej w <b>Chrome</b>; jeśli zablokuje połączenie ze strony https, otwórz aplikację lokalnie (<code className="rounded bg-black/30 px-1">localhost:3000</code>).</li>
          </ul>
        </div>
      )}
      <p className="text-[12px] text-slate-500">Aktualnie: <b className="text-slate-300">{getApiBase()}</b></p>
    </div>
  );
}
