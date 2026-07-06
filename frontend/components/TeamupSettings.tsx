"use client";

// Integracja TeamUp (grafik gotowości + triaż): klucz API, kalendarze, test połączenia.
import { useEffect, useState } from "react";
import { CalendarClock, Loader2, CheckCircle2, XCircle, PlugZap, Save } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";

export default function TeamupSettings() {
  const [cfg, setCfg] = useState<{ has_key: boolean; key_from_env: boolean; key_source: string; env_names: string[]; cal_gotowosc: string; cal_triaz: string } | null>(null);
  const [notDeployed, setNotDeployed] = useState(false);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<Record<string, { ok: boolean; events?: number; sample?: string[]; error?: string }> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.teamupConfig().then(setCfg).catch((e) => {
      // 404 = backend bez wdrożonej integracji (stary obraz przed fly deploy).
      if (String(e.message).includes("404")) setNotDeployed(true);
      else setErr(e.message);
    });
  }, []);

  async function saveKey() {
    if (!key.trim()) return;
    setBusy(true); setErr(null);
    try {
      await api.saveTeamupConfig({ api_key: key.trim() });
      setKey("");
      setCfg(await api.teamupConfig());
      toast("Zapisano klucz TeamUp.");
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  async function runTest() {
    setTesting(true); setTest(null); setErr(null);
    try { setTest(await api.teamupTest()); }
    catch (e: any) { setErr(e.message); }
    finally { setTesting(false); }
  }

  return (
    <div className="card">
      <h2 className="flex items-center gap-2 text-base font-bold">
        <CalendarClock size={18} className="text-brand-accent" /> Integracja TeamUp (gotowość i triaż)
      </h2>
      <p className="mt-1 text-[13px] leading-relaxed text-slate-400">
        Godziny gotowości i triażu pobierane są z grafików TeamUp i mnożone przez stawki
        z pliku ZOBOWIĄZAŃ (dół zakładki lekarza). Wynik dolicza się przy rozliczeniu lekarzy
        (arkusz „Gotowość" w pliku każdego lekarza) i w Porównaniu.
        Zalecane: klucz jako sekret <code className="text-slate-300">TEAMUP_API_KEY</code> na Fly —
        pole poniżej to alternatywa (zapis na dysku serwera).
      </p>

      {notDeployed && (
        <div className="mt-3 rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[13px] text-amber-200">
          Backend nie ma jeszcze wdrożonej integracji TeamUp (endpoint nie istnieje).
          Zrób <code className="text-amber-100">fly deploy</code> najnowszego kodu — sam sekret nie wystarczy.
        </div>
      )}

      {cfg && (
        <div className="mt-3 space-y-1 text-sm">
          <p>
            Status klucza:{" "}
            {cfg.has_key
              ? <span className="pill pill-ok">{cfg.key_from_env ? "ustawiony (sekret Fly)" : "ustawiony (na serwerze)"}</span>
              : <span className="pill pill-warn">brak klucza</span>}
          </p>
          {!cfg.has_key && cfg.env_names.length > 0 && (
            <p className="text-[13px] text-amber-300">
              Uwaga: backend widzi zmienną {cfg.env_names.map((n) => <code key={n} className="mx-1 text-amber-100">{n}</code>)}
              — ale nazwa musi być <b>dokładnie</b> <code className="text-amber-100">TEAMUP_API_KEY</code> (wielkość liter ma znaczenie).
              Ustaw: <code className="text-amber-100">fly secrets set TEAMUP_API_KEY="…"</code>.
            </p>
          )}
          {!cfg.has_key && cfg.env_names.length === 0 && (
            <p className="text-[13px] text-slate-400">
              Backend nie widzi żadnego sekretu „teamup". Sprawdź <code>fly secrets list</code> (czy jest <code>TEAMUP_API_KEY</code>)
              i czy po jego dodaniu apka wstała z nowym obrazem. Alternatywnie wpisz klucz w polu poniżej.
            </p>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input type="password" className="input sm:w-72" placeholder="Klucz API TeamUp…"
          value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" />
        <button className="btn-secondary" disabled={busy || !key.trim()} onClick={saveKey}>
          {busy ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />} Zapisz klucz
        </button>
        <button className="btn-secondary" disabled={testing || !cfg?.has_key} onClick={runTest}>
          {testing ? <Loader2 className="animate-spin" size={16} /> : <PlugZap size={16} />} Testuj połączenie
        </button>
      </div>

      {err && <p className="mt-3 text-sm text-red-300">{err}</p>}

      {test && (
        <div className="mt-3 space-y-2 text-sm">
          {Object.entries(test).map(([name, r]) => (
            <div key={name} className="soft flex flex-wrap items-center gap-2 px-3 py-2">
              {r.ok ? <CheckCircle2 className="text-brand-accent2" size={16} /> : <XCircle className="text-red-300" size={16} />}
              <b>{name === "gotowosc" ? "Grafik gotowości" : "Triaż"}</b>
              {r.ok
                ? <span className="text-slate-300">wydarzeń (7 dni): {r.events}{r.sample && r.sample.length > 0 ? ` · np. ${r.sample.slice(0, 3).join(", ")}` : ""}</span>
                : <span className="text-red-300">{r.error}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
