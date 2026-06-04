"use client";

import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, LineChart, Line, CartesianGrid,
} from "recharts";
import { Building2, Layers, FileCheck2, Coins } from "lucide-react";
import { api, Overview, JobStats, TrendPoint } from "@/lib/api";

const MOD_COLORS: Record<string, string> = {
  RTG: "#1dab5a",
  TK: "#36b9cc",
  MR: "#9b6cf0",
  MMG: "#f0ad4e",
  INNE: "#6b7280",
};

const TOOLTIP_STYLE = { background: "#0e3b49", border: "1px solid #214652", borderRadius: 12 };

const zl = (n?: number) =>
  n === undefined ? "—" : n.toLocaleString("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });

function StatCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="card flex items-center gap-4">
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-brand-accent/15 text-brand-accent">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="truncate text-2xl font-bold">{value}</p>
        <p className="text-sm text-slate-400">{label}</p>
        {sub && <p className="truncate text-xs text-slate-500">{sub}</p>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [stats, setStats] = useState<JobStats | null>(null);
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.overview()
      .then((ov) => {
        setOverview(ov);
        if (ov.last_job && ov.last_job.status === "done" && ov.last_job.mode === "full") {
          api.jobStats(ov.last_job.id).then(setStats).catch(() => {});
        }
      })
      .catch((e) => setError(e.message));
    api.trends().then((t) => setTrends(t.points)).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Pulpit</h1>
        <p className="text-sm text-slate-400">Przegląd ostatniego rozliczenia i trendów.</p>
      </header>

      {error && (
        <div className="card border-red-500/40 text-red-300">
          Nie udało się połączyć z API ({error}). Sprawdź, czy backend jest uruchomiony.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={<Coins size={22} />} label="Wartość ostatniego rozliczenia"
          value={zl(stats?.total_revenue)} />
        <StatCard icon={<Layers size={22} />} label="Jednostek (okolic) w rozliczeniu"
          value={stats?.total_studies?.toLocaleString("pl-PL") ?? "—"} />
        <StatCard icon={<Building2 size={22} />} label="Klientów"
          value={stats?.clients_count?.toString() ?? "—"} />
        <StatCard icon={<FileCheck2 size={22} />} label="Wykonanych rozliczeń"
          value={overview ? `${overview.jobs_done}/${overview.jobs_total}` : "—"}
          sub={overview?.active_wzorcowe?.original_name ?? "brak aktywnego słownika"} />
      </div>

      {trends.length > 1 && (
        <div className="card">
          <h2 className="mb-4 text-lg font-semibold">Trend miesięczny — wartość rozliczeń</h2>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trends} margin={{ left: 10, right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#214652" />
              <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={(v) => (v / 1000).toFixed(0) + "k"} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => zl(v)} />
              <Line type="monotone" dataKey="revenue" name="Wartość" stroke="#1dab5a" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {stats && !stats.empty ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="card">
            <h2 className="mb-4 text-lg font-semibold">Wartość wg modalności</h2>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={stats.by_modality} dataKey="revenue" nameKey="modality"
                  cx="50%" cy="50%" outerRadius={100} label={(e: any) => e.modality}>
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
            <h2 className="mb-4 text-lg font-semibold">Top 15 klientów (wartość)</h2>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={stats.top_clients} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" stroke="#64748b" fontSize={12} tickFormatter={(v) => (v / 1000).toFixed(0) + "k"} />
                <YAxis type="category" dataKey="client" width={120} stroke="#94a3b8" fontSize={11} />
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
