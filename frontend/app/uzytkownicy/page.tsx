"use client";

import { useEffect, useState } from "react";
import { Users, UserPlus, Trash2, Loader2, ShieldCheck, Eye } from "lucide-react";
import { api, Account } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "@/lib/toast";

export default function UzytkownicyPage() {
  const { isAdmin, username: mySelf } = useAuth();
  const [users, setUsers] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [nu, setNu] = useState("");
  const [np, setNp] = useState("");
  const [nr, setNr] = useState("user");
  const [busy, setBusy] = useState(false);

  function reload() {
    setLoading(true);
    api.listUsers().then(setUsers).catch((e) => setErr(e.message)).finally(() => setLoading(false));
  }
  useEffect(() => { if (isAdmin) reload(); else setLoading(false); }, [isAdmin]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await api.createUser(nu.trim(), np, nr);
      setNu(""); setNp(""); setNr("user");
      toast("Utworzono konto.");
      reload();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  async function remove(u: Account) {
    if (!confirm(`Usunąć konto „${u.username}"?`)) return;
    try { await api.deleteUser(u.id); toast("Usunięto konto."); reload(); }
    catch (e: any) { setErr(e.message); }
  }

  async function changeRole(u: Account, role: string) {
    try { await api.updateUser(u.id, { role }); reload(); }
    catch (e: any) { setErr(e.message); }
  }

  if (!isAdmin) {
    return (
      <div className="card text-sm text-slate-400">
        Ta sekcja jest dostępna tylko dla administratora.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-[26px] font-extrabold tracking-tight">
          <Users size={24} className="text-brand-accent" /> Użytkownicy
        </h1>
        <p className="text-sm text-slate-400">
          Konta i role. <b>Administrator</b> może wgrywać pliki, uruchamiać przeliczenia i usuwać dane;
          <b> użytkownik</b> tylko przegląda wyniki.
        </p>
      </header>

      {err && <div className="card border-red-500/40 text-red-300">{err}</div>}

      <form onSubmit={create} className="card space-y-3">
        <h2 className="flex items-center gap-2 font-bold"><UserPlus size={18} className="text-brand-accent" /> Nowe konto</h2>
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1">
            <span className="text-[13px] text-slate-300">Login</span>
            <input className="input sm:w-48" value={nu} onChange={(e) => setNu(e.target.value)} autoComplete="off" />
          </label>
          <label className="space-y-1">
            <span className="text-[13px] text-slate-300">Hasło (min. 4 znaki)</span>
            <input className="input sm:w-48" type="password" value={np} onChange={(e) => setNp(e.target.value)} autoComplete="new-password" />
          </label>
          <label className="space-y-1">
            <span className="text-[13px] text-slate-300">Rola</span>
            <select className="input sm:w-40" value={nr} onChange={(e) => setNr(e.target.value)}>
              <option value="user">Użytkownik (podgląd)</option>
              <option value="admin">Administrator</option>
            </select>
          </label>
          <button className="btn-primary" disabled={busy || !nu.trim() || np.length < 4}>
            {busy ? <Loader2 className="animate-spin" size={18} /> : <UserPlus size={18} />} Utwórz
          </button>
        </div>
      </form>

      <div className="card">
        <h2 className="mb-3 font-bold">Konta ({users.length})</h2>
        {loading ? (
          <div className="flex items-center gap-2 text-slate-400"><Loader2 className="animate-spin" size={16} /> Wczytuję…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-400">
                <tr><th className="py-2 pr-4">Login</th><th className="py-2 pr-4">Rola</th><th className="py-2 pr-4">Utworzono</th><th className="py-2 pr-4"></th></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-t border-white/10">
                    <td className="py-2 pr-4 font-semibold">{u.username}</td>
                    <td className="py-2 pr-4">
                      <select className="input !py-1 !text-xs" value={u.role} onChange={(e) => changeRole(u, e.target.value)}>
                        <option value="user">Użytkownik</option>
                        <option value="admin">Administrator</option>
                      </select>
                    </td>
                    <td className="py-2 pr-4 text-slate-400">{new Date(u.created_at).toLocaleString("pl-PL")}</td>
                    <td className="py-2 pr-4 text-right">
                      <button className="btn-secondary !px-2 !py-1 hover:border-red-500 hover:text-red-300"
                        onClick={() => remove(u)} aria-label="Usuń">
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr><td colSpan={4} className="py-3 text-slate-500">Brak kont. Logowanie działa też wspólnym hasłem głównym (administrator).</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Wspólne „hasło główne" (dotychczasowe) nadal działa jako administrator — konta poniżej są dodatkowe.
        </p>
      </div>
    </div>
  );
}
