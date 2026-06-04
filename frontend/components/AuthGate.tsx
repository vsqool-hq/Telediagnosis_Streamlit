"use client";

import { useEffect, useState } from "react";
import { Lock, LogIn, Activity, Loader2 } from "lucide-react";
import { api, setToken, clearToken } from "@/lib/api";

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
          <div className="flex flex-col items-center gap-2 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-accent/20 text-brand-accent">
              <Activity size={24} />
            </div>
            <h1 className="text-lg font-bold">Automatyzator Rozliczeń</h1>
            <p className="text-sm text-slate-400">Podaj hasło dostępu.</p>
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
        </form>
      </div>
    );
  }

  return <>{children}</>;
}
