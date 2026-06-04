"use client";

import { useEffect, useState } from "react";
import { Download, CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";
import { api, Job } from "@/lib/api";

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { icon: React.ReactNode; cls: string; label: string }> = {
    done: { icon: <CheckCircle2 size={14} />, cls: "bg-brand-accent/20 text-brand-accent", label: "Gotowe" },
    error: { icon: <XCircle size={14} />, cls: "bg-red-500/20 text-red-300", label: "Błąd" },
    running: { icon: <Loader2 className="animate-spin" size={14} />, cls: "bg-amber-500/20 text-amber-300", label: "W toku" },
    queued: { icon: <Clock size={14} />, cls: "bg-slate-500/20 text-slate-300", label: "W kolejce" },
  };
  const s = map[status] ?? map.queued;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${s.cls}`}>
      {s.icon} {s.label}
    </span>
  );
}

export default function HistoriaPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listJobs().then(setJobs).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Historia rozliczeń</h1>
        <p className="text-sm text-slate-400">Wszystkie uruchomione zadania.</p>
      </header>

      {error && <div className="card border-red-500/40 text-red-300">{error}</div>}

      <div className="card overflow-x-auto">
        {jobs.length === 0 ? (
          <p className="text-sm text-slate-400">Brak zadań w historii.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-400">
              <tr className="border-b border-brand-border/60">
                <th className="py-3 pr-4">Data</th>
                <th className="py-3 pr-4">Plik wejściowy</th>
                <th className="py-3 pr-4">Tryb</th>
                <th className="py-3 pr-4">Status</th>
                <th className="py-3 pr-4">Wynik</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-b border-brand-border/30">
                  <td className="py-3 pr-4 text-slate-300">{new Date(j.created_at).toLocaleString("pl-PL")}</td>
                  <td className="max-w-xs truncate py-3 pr-4">{j.input_name}</td>
                  <td className="py-3 pr-4 text-slate-300">{j.mode === "full" ? "Pełny" : "Braki wzorca"}</td>
                  <td className="py-3 pr-4"><StatusBadge status={j.status} /></td>
                  <td className="py-3 pr-4">
                    {j.status === "done" ? (
                      <a className="inline-flex items-center gap-1 text-brand-accent hover:underline" href={api.resultUrl(j.id)}>
                        <Download size={14} /> Pobierz
                      </a>
                    ) : j.error ? (
                      <span className="text-xs text-red-300" title={j.error}>{j.error.slice(0, 60)}</span>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
