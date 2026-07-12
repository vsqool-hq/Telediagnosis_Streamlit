"use client";

import { useState } from "react";

function zl(n: number) {
  return n.toLocaleString("pl-PL", { style: "currency", currency: "PLN" });
}

/** Lista „okres: kwota" (najnowszy na górze, wyróżniony) — treść dymka, używana
 * zarówno przez `RevenueHistoryHover` (zwykłe hover nad tekstem) jak i przez
 * niestandardowy `Tooltip` na wykresach Recharts (inny mechanizm wyzwalania). */
export function HistoryList({ history, label = "Historia przychodu" }: { history?: Record<string, number>; label?: string }) {
  const periods = history ? Object.keys(history).sort().reverse() : [];
  if (!periods.length) return null;
  return (
    <>
      <div className="mb-1 font-semibold text-slate-400">{label}</div>
      {periods.map((p, i) => (
        <div
          key={p}
          className={`flex items-center justify-between gap-4 py-0.5 ${
            i === 0 ? "font-bold text-brand-accent2" : "text-slate-300"
          }`}
        >
          <span>{p}</span>
          <span>{zl(history![p])}</span>
        </div>
      ))}
    </>
  );
}

/** Owija nazwę jednostki/lekarza — po najechaniu pokazuje dymek z historią kwot
 * per miesiąc (zawsze z najlepszego przeliczenia danego miesiąca). Bez historii
 * (np. lekarz, dla którego nigdy nie policzono rozliczenia) renderuje samo dziecko. */
export function RevenueHistoryHover({
  history,
  label,
  children,
}: {
  history?: Record<string, number>;
  label?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const hasHistory = history && Object.keys(history).length > 0;

  if (!hasHistory) return <>{children}</>;

  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <span className="cursor-default border-b border-dotted border-slate-500/60">{children}</span>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 min-w-[190px] whitespace-nowrap rounded-xl border border-white/10 bg-[#0e3b49] p-2.5 text-xs shadow-xl shadow-black/30">
          <HistoryList history={history} label={label} />
        </div>
      )}
    </span>
  );
}
