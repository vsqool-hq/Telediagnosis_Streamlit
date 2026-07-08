"use client";

import { useEffect, useState } from "react";
import { Lock, LogIn, Loader2, User } from "lucide-react";
import { api, setToken, clearToken, Me } from "@/lib/api";
import { AuthContext } from "@/lib/auth";
import BackendSwitcher from "@/components/BackendSwitcher";

type State = "checking" | "locked" | "open";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>("checking");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [me, setMe] = useState<Me | null>(null);

  function check() {
    api.me()
      .then((m) => { setMe(m); setState("open"); })
      .catch(() => setState("locked"));
  }
  useEffect(check, []);

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (username.trim()) {
        // Konto z rolą (nowe logowanie).
        const res = await api.login(username.trim(), password);
        setToken(res.token);
      } else {
        // Zgodność wstecz: samo hasło = wspólny token (master-admin).
        setToken(password.trim());
      }
      const m = await api.me();
      setMe(m);
      setState("open");
      setPassword("");
    } catch {
      clearToken();
      setError("Nieprawidłowy login lub hasło.");
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    api.logout();
    clearToken();
    setMe(null);
    setUsername("");
    setState("locked");
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
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="Telediagnosis" className="h-14 w-14 rounded-2xl" />
            <div>
              <h1 className="text-xl font-extrabold tracking-tight">Automatyzator Rozliczeń</h1>
              <p className="text-sm text-slate-400">Telediagnosis · panel wewnętrzny</p>
            </div>
          </div>

          <div className="relative">
            <User className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
            <input
              autoFocus
              className="input pl-9"
              placeholder="Login (puste = hasło główne)"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </div>

          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
            <input
              type="password"
              className="input pl-9"
              placeholder="Hasło"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
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

  const role = me?.role ?? (me && !me.auth_enabled ? "admin" : null);
  return (
    <AuthContext.Provider
      value={{
        role,
        username: me?.username ?? null,
        authEnabled: me?.auth_enabled ?? true,
        isAdmin: role === "admin",
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
