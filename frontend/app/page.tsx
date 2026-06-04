"use client";

import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { Building2, Layers, FileCheck2, Database } from "lucide-react";
import { api, Overview, JobStats } from "@/lib/api";

const MOD_COLORS: Record<string, string> = {
  RTG: "#1dab5a",
  TK: "#36b9cc",
  MR: "#9b6cf0",
  MMG: "#f0ad4e",
  INNE: "#6b7280",
};

function StatCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="card flex items-center gap-4">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-accent/15 text-brand-accent">
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-sm text-slate-400">{label}</p>
        {sub && <p className="text-xs text-slate-500">{sub}</p>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [stats, setStats] = useState<JobStats | null>(null);
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
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Pulpit</h1>
        <p className="text-sm text-slate-400">Przegląd ostatniego rozliczenia i stanu systemu.</p>
      </header>

      {error && (
        <div className="card border-red-500/40 text-red-300">
          Nie udało się połączyć z API ({error}). Sprawdź, czy backend jest uruchomiony.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={<Layers size={22} />} label="Badań w ostatnim rozliczeniu"
          value={stats?.total_studies?.toLocaleString("pl-PL") ?? "—"} />
        <StatCard icon={<Building2 size={22} />} label="Klientów"
          value={stats?.clients_count?.toString() ?? "—"} />
        <StatCard icon={<FileCheck2 size={22} />} label="Wykonanych rozliczeń"
          value={overview ? `${overview.jobs_done}/${overview.jobs_total}` : "—"} />
        <StatCard icon={<Database size={22} />} label="Aktywny słownik"
          value={overview?.active_wzorcowe ? "✓" : "—"}
          sub={overview?.active_wzorcowe?.original_name ?? "brak aktywnej wersji"} />
      </div>

      {stats && !stats.empty ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="card">
            <h2 className="mb-4 text-lg font-semibold">Badania wg modalności</h2>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={stats.by_modality} dataKey="count" nameKey="modality"
                  cx="50%" cy="50%" outerRadius={100} label>
                  {stats.by_modality!.map((m) => (
                    <Cell key={m.modality} fill={MOD_COLORS[m.modality] || "#6b7280"} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: "#0e3b49", border: "1px solid #214652", borderRadius: 12 }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h2 className="mb-4 text-lg font-semibold">Top 15 klientów (liczba badań)</h2>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={stats.top_clients} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" stroke="#64748b" fontSize={12} />
                <YAxis type="category" dataKey="client" width={120} stroke="#94a3b8" fontSize={11} />
                <Tooltip contentStyle={{ background: "#0e3b49", border: "1px solid #214652", borderRadius: 12 }} />
                <Bar dataKey="count" fill="#1dab5a" radius={[0, 6, 6, 0]} />
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
