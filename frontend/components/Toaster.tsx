"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { ToastItem, subscribeToasts } from "@/lib/toast";

export default function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);
  useEffect(() => subscribeToasts(setItems), []);

  if (items.length === 0) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col gap-2">
      {items.map((t) => (
        <div
          key={t.id}
          style={{ animation: "fade-up 0.2s ease both" }}
          className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold shadow-xl shadow-black/30 backdrop-blur ${
            t.kind === "ok"
              ? "border-brand-accent/40 bg-brand-surface/95 text-brand-accent2"
              : "border-red-500/40 bg-brand-surface/95 text-red-300"
          }`}
        >
          {t.kind === "ok" ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
          {t.msg}
        </div>
      ))}
    </div>
  );
}
