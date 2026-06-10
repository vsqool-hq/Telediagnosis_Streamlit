"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Loader2, ArrowRight } from "lucide-react";
import { api, Job } from "@/lib/api";

/**
 * Baner widoczny, gdy trwa rozliczenie.
 *
 * WAŻNE (koszty / scale-to-zero): NIE odpytujemy w kółko, gdy nic się nie liczy —
 * inaczej otwarta karta budziłaby maszynę Fly 24/7. Robimy więc:
 *   • pojedyncze sprawdzenie przy wejściu i przy powrocie na kartę (focus),
 *   • dopiero gdy WYKRYJEMY aktywne zadanie, odpytujemy co 5 s aż do końca,
 *   • brak aktywnego zadania → zero pętli (maszyna może spokojnie zasnąć).
 */
export default function ActiveJobBanner() {
  const [job, setJob] = useState<Job | null>(null);
  const pathname = usePathname();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;

    const clear = () => { if (timer.current) { clearTimeout(timer.current); timer.current = null; } };

    const check = async () => {
      try {
        const j = await api.activeJob();
        if (!alive.current) return;
        setJob(j);
        clear();
        // Pętlę utrzymujemy TYLKO dopóki realnie coś się liczy.
        if (j) timer.current = setTimeout(check, 5000);
      } catch {
        /* offline/uśpiona maszyna — nie ponawiamy w pętli */
      }
    };

    check(); // jednorazowo po wejściu
    const onFocus = () => { if (!timer.current) check(); };
    window.addEventListener("focus", onFocus);

    return () => {
      alive.current = false;
      clear();
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  if (!job) return null;
  if (pathname === "/rozliczenie") return null; // tam jest pełny podgląd

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
