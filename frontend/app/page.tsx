"use client";

import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, AreaChart, Area, CartesianGrid,
} from "recharts";
import { Building2, Layers, TrendingUp, Coins, AlertTriangle } from "lucide-react";
import { api, Overview, JobStats, TrendPoint } from "@/lib/api";
import { useCachedData } from "@/lib/cache";

const MOD_COLORS: Record<string, string> = {
  RTG: "#1dab5a",
  TK: "#36c5d0",
  MR: "#9b6cf0",
  MMG: "#f6c560",
  INNE: "#6b7280",
};

const TOOLTIP_STYLE = { background: "#0e3b49", border: "1px solid #214652", borderRadius: 12 };

const zl = (n?: number) =>
  n === undefined ? "—" : n.toLocaleString("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });

function StatCard({
  icon, label, value, sub,
}: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">{label}</p>
        <span className="text-brand-accent">{icon}</span>
      </div>
      <p className="mt-2.5 truncate text-[28px] font-extrabold leading-none">{value}</p>
      {sub && <p className="mt-1.5 truncate text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

export default function Dashboard() {
  // Cache po stronie przeglądarki: powrót na Pulpit pokazuje liczby od razu,
  // odświeżenie leci w tle.
  const { data: overview, error } = useCachedData<Overview>("overview", () => api.overview());
  const lastJob = overview?.last_job;
  const statsKey =
    lastJob && lastJob.status === "done" && lastJob.mode === "full" ? `jobStats:${lastJob.id}` : null;
  const { data: stats } = useCachedData<JobStats>(statsKey, () => api.jobStats(lastJob!.id));
  const { data: trendsData } = useCachedData<{ points: TrendPoint[] }>("trends", () => api.trends());
  const trends: TrendPoint[] = trendsData?.points ?? [];

  const avgPerClient =
    stats && !stats.empty && stats.clients_count
      ? zl(Math.round((stats.total_revenue ?? 0) / stats.clients_count))
      : "—";

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-extrabold tracking-tight">Pulpit</h1>
          <p className="text-sm text-slate-400">Przegląd ostatniego rozliczenia i trendów.</p>
        </div>
        {overview?.active_cennik && (
          <span className="pill pill-ok">Aktywny cennik: {overview.active_cennik.original_name}</span>
        )}
      </header>

      {error && (
        <div className="card border-red-500/40 text-red-300">
          Nie udało się połączyć z API ({error}). Sprawdź, czy backend jest uruchomiony.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={<Coins size={20} />} label="Wartość ost. rozliczenia"
          value={zl(stats?.total_revenue)} />
        <StatCard icon={<Layers size={20} />} label="Pozycji rozliczonych"
          value={stats?.total_studies?.toLocaleString("pl-PL") ?? "—"}
          sub={stats?.clients_count ? `w ${stats.clients_count} jednostkach` : undefined} />
        <StatCard icon={<Building2 size={20} />} label="Klientów"
          value={stats?.clients_count?.toString() ?? "—"}
          sub={overview ? `wykonano ${overview.jobs_done}/${overview.jobs_total} rozliczeń` : undefined} />
        <StatCard icon={<TrendingUp size={20} />} label="Średnio / klienta"
          value={avgPerClient} />
      </div>

      {stats?.zero_clients && stats.zero_clients.length > 0 && (
        <div className="card border-amber-400/40">
          <h2 className="flex items-center gap-2 text-base font-bold text-amber-300">
            <AlertTriangle size={18} /> Jednostki z 0 zł za cały miesiąc ({stats.zero_clients.length})
          </h2>
          <p className="mt-1 text-[13px] text-slate-400">
            Te jednostki nie zostały wycenione — najczęściej nazwa w pliku miesięcznym różni się od
            nazwy w cenniku (dokładne dopasowanie). Popraw nazwę w cenniku lub w pliku.
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-400">
                <tr><th className="py-2 pr-4">Jednostka (z pliku)</th><th className="py-2 pr-4">Badań</th><th className="py-2 pr-4">W cenniku?</th><th className="py-2 pr-4">Podobne nazwy w cenniku</th></tr>
              </thead>
              <tbody>
                {stats.zero_clients.map((z) => (
                  <tr key={z.client} className="border-t border-white/10">
                    <td className="py-2 pr-4 font-semibold">{z.client}</td>
                    <td className="py-2 pr-4 text-slate-400">{z.studies}</td>
                    <td className="py-2 pr-4">
                      {z.in_cennik
                        ? <span className="pill pill-muted">jest (sprawdź ceny/klucze)</span>
                        : <span className="pill pill-warn">brak</span>}
                    </td>
                    <td className="py-2 pr-4 text-brand-accent2">{z.suggestions.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {trends.length > 1 && (
        <div className="card">
          <h2 className="mb-4 text-base font-bold">Trend wartości rozliczeń</h2>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={trends} margin={{ left: 10, right: 10 }}>
              <defs>
                <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#1dab5a" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#1dab5a" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" />
              <XAxis dataKey="date" stroke="#8aa0a3" fontSize={12} />
              <YAxis stroke="#8aa0a3" fontSize={12} tickFormatter={(v) => (v / 1000).toFixed(0) + "k"} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => zl(v)} />
              <Area type="monotone" dataKey="revenue" name="Wartość" stroke="#25c96b"
                strokeWidth={3} fill="url(#revFill)" dot={{ r: 3, fill: "#25c96b" }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {stats && !stats.empty ? (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div className="card">
            <h2 className="mb-4 text-base font-bold">Wartość wg modalności</h2>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={stats.by_modality} dataKey="revenue" nameKey="modality"
                  cx="50%" cy="50%" innerRadius={62} outerRadius={100} paddingAngle={2}
                  stroke="#0a2d37" strokeWidth={3}>
                  {stats.by_modality!.map((m) => (
                    <Cell key={m.modality} fill={MOD_COLORS[m.modality] || "#6b7280"} />
                  ))}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => zl(v)} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h2 className="mb-4 text-base font-bold">Top 15 klientów (wartość)</h2>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={stats.top_clients} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" stroke="#8aa0a3" fontSize={12} tickFormatter={(v) => (v / 1000).toFixed(0) + "k"} />
                <YAxis type="category" dataKey="client" width={120} stroke="#8aa0a3" fontSize={11} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => zl(v)} />
                <Bar dataKey="revenue" name="Wartość" fill="#1dab5a" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <div className="card text-slate-400">
          Brak danych do wykresów. Uruchom pełne rozliczenie w zakładce{" "}
          <a href="/rozliczenie" className="text-brand-accent underline">Rozliczenie</a>.
        </div>
      )}
    </div>
  );
}
