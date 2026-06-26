"use client";

// Miniaturka zawartości pliku (pierwsze wiersze/kolumny) + powiększenie na cały
// ekran po kliknięciu. Pomaga rozpoznać, jaki plik wgrać w danym miejscu.
import { useState } from "react";
import { X, Maximize2 } from "lucide-react";
import { FilePreviewData } from "@/lib/api";
import { useCachedData } from "@/lib/cache";

export default function FilePreview({
  cacheKey, load, title,
}: {
  cacheKey: string;
  load: () => Promise<FilePreviewData>;
  title: string;
}) {
  const { data, loading } = useCachedData<FilePreviewData>(cacheKey, load, 300_000);
  const [open, setOpen] = useState(false);

  if (loading && !data) return <p className="text-xs text-slate-500">Ładuję podgląd…</p>;
  if (!data || data.empty) return <p className="text-xs text-slate-500">{data?.reason ?? "Brak podglądu."}</p>;

  const thumbCols = data.columns.slice(0, 6);
  const thumbRows = data.rows.slice(0, 4);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Kliknij, aby powiększyć na cały ekran"
        className="group relative block w-full max-w-md overflow-hidden rounded-lg border border-white/10 bg-white/[0.02] p-2 text-left hover:border-brand-accent"
      >
        <div className="overflow-hidden" style={{ maxHeight: 96 }}>
          <table className="w-full border-collapse text-[9px] leading-tight text-slate-300">
            <thead>
              <tr>
                {thumbCols.map((c, i) => (
                  <th key={i} className="max-w-[90px] truncate border border-white/10 px-1 py-0.5 text-left font-semibold">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {thumbRows.map((r, ri) => (
                <tr key={ri}>
                  {r.slice(0, 6).map((c, ci) => (
                    <td key={ci} className="max-w-[90px] truncate border border-white/10 px-1 py-0.5">{c}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <span className="absolute right-1.5 top-1.5 rounded bg-black/50 p-1 text-slate-100 opacity-0 transition-opacity group-hover:opacity-100">
          <Maximize2 size={12} />
        </span>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setOpen(false)}>
          <div
            className="flex max-h-[90vh] w-full max-w-5xl flex-col rounded-2xl border border-white/15 bg-brand-surface p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between gap-2">
              <h3 className="truncate font-bold">
                {title}{data.sheet ? ` · arkusz „${data.sheet}"` : ""}
              </h3>
              <button className="btn-secondary px-2 py-1" onClick={() => setOpen(false)} aria-label="Zamknij">
                <X size={16} />
              </button>
            </div>
            <div className="overflow-auto">
              <table className="w-full border-collapse text-xs">
                <thead className="sticky top-0 bg-brand-surface">
                  <tr>
                    {data.columns.map((c, i) => (
                      <th key={i} className="whitespace-nowrap border border-white/10 px-2 py-1 text-left font-semibold text-slate-300">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, ri) => (
                    <tr key={ri}>
                      {r.map((c, ci) => (
                        <td key={ci} className="whitespace-nowrap border border-white/10 px-2 py-1 text-slate-300">{c}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Podgląd pierwszych {data.rows.length} wierszy{data.more_cols ? ` · +${data.more_cols} dalszych kolumn` : ""}.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
