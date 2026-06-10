"use client";

import { useEffect, useState } from "react";
import { Lock, LogIn, Plus, Loader2 } from "lucide-react";
import { api, setToken, clearToken } from "@/lib/api";
import BackendSwitcher from "@/components/BackendSwitcher";

type State = "checking" | "locked" | "open";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>("checking");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function check() {
    api.validate()
      .then(() => setState("open"))
      .catch(() => setState("locked"));
  }
  useEffect(check, []);

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setToken(password.trim());
    try {
      await api.validate();
      setState("open");
    } catch {
      clearToken();
      setError("Nieprawidłowe hasło.");
    } finally {
      setBusy(false);
    }
  }

  if (state === "checking") {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-400">
        <Loader2 className="animate-spin" />
      </div>
    );
  }

  if (state === "locked") {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <form onSubmit={login} className="card w-full max-w-sm space-y-5">
          <div className="flex flex-col items-center gap-3 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-b from-brand-accent2 to-brand-accent text-[#04130b]">
              <Plus size={26} strokeWidth={2.6} />
            </div>
            <div>
              <h1 className="text-xl font-extrabold tracking-tight">Automatyzator Rozliczeń</h1>
              <p className="text-sm text-slate-400">Telediagnosis · panel wewnętrzny</p>
            </div>
          </div>

          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
            <input
              type="password"
              autoFocus
              className="input pl-9"
              placeholder="Hasło"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error && <p className="text-sm text-red-300">{error}</p>}

          <button type="submit" className="btn-primary w-full" disabled={busy || !password}>
            {busy ? <Loader2 className="animate-spin" size={18} /> : <LogIn size={18} />}
            Zaloguj
          </button>

          <div className="border-t border-white/10 pt-3">
            <p className="mb-1.5 text-xs text-slate-500">Silnik obliczeń:</p>
            <BackendSwitcher compact />
          </div>
        </form>
      </div>
    );
  }

  return <>{children}</>;
}
