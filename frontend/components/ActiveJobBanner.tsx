"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Loader2, ArrowRight } from "lucide-react";
import { api, Job } from "@/lib/api";

/**
 * Baner widoczny na każdej stronie, gdy trwa rozliczenie. Odpytywanie co 7 s
 * pełni dwie role: pokazuje aktywne zadanie ORAZ — bo leci przez proxy Fly —
 * podtrzymuje „obudzoną" maszynę, gdy aplikacja jest otwarta na jakimkolwiek
 * urządzeniu. Samo liczenie i tak biegnie po stronie serwera niezależnie.
 */
export default function ActiveJobBanner() {
  const [job, setJob] = useState<Job | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    let alive = true;
    const tick = () =>
      api.activeJob().then((j) => { if (alive) setJob(j); }).catch(() => {});
    tick();
    const id = setInterval(tick, 7000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (!job) return null;
  // Na stronie rozliczenia mamy już pełny podgląd — baner zbędny.
  if (pathname === "/rozliczenie") return null;

  return (
    <Link
      href={`/rozliczenie?job=${job.id}`}
      className="mb-4 flex items-center gap-3 rounded-2xl border border-brand-accent/40 bg-brand-accent/10 px-4 py-3 text-sm transition-colors hover:bg-brand-accent/15"
    >
      <Loader2 className="animate-spin text-brand-accent2" size={18} />
      <span className="font-semibold text-brand-accent2">Trwa rozliczenie…</span>
      <span className="truncate text-slate-300">{job.input_name}</span>
      <ArrowRight className="ml-auto text-slate-400" size={16} />
    </Link>
  );
}
