"use client";

// Obrazek-wzór dla miejsca wgrywania pliku: miniaturka + powiększenie na cały
// ekran po kliknięciu, oraz wgrywanie/usuwanie własnego zrzutu ekranu (opcja B).
import { useState } from "react";
import { X, Maximize2, Upload, Trash2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

export default function ReferenceImage({ slot, title }: { slot: string; title: string }) {
  const [v, setV] = useState(0);                       // cache-buster po zmianie/usunięciu
  const [exists, setExists] = useState<boolean | null>(null);  // null = jeszcze nie wiadomo
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const src = api.referenceImageUrl(slot, v);

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true); setErr(null);
    try {
      await api.uploadReferenceImage(slot, file);
      setExists(true);
      setV((x) => x + 1);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  async function remove() {
    if (!confirm("Usunąć obrazek-wzór?")) return;
    await api.deleteReferenceImage(slot).catch((e: any) => setErr(e.message));
    setExists(false);
    setV((x) => x + 1);
  }

  return (
    <div className="space-y-2">
      {exists !== false && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          title="Kliknij, aby powiększyć na cały ekran"
          className="group relative block overflow-hidden rounded-lg border border-white/10 bg-white/[0.02] hover:border-brand-accent"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={title}
            onLoad={() => setExists(true)}
            onError={() => setExists(false)}
            className="max-h-40 max-w-full rounded-lg object-contain"
          />
          <span className="absolute right-1.5 top-1.5 rounded bg-black/50 p-1 text-slate-100 opacity-0 transition-opacity group-hover:opacity-100">
            <Maximize2 size={12} />
          </span>
        </button>
      )}
      {exists === false && <p className="text-xs text-slate-500">Brak obrazka-wzoru. Wgraj poniżej.</p>}

      <div className="flex items-center gap-2">
        <label className="btn-secondary inline-flex cursor-pointer items-center gap-1.5 px-3 py-1.5 text-xs">
          {busy ? <Loader2 className="animate-spin" size={14} /> : <Upload size={14} />}
          {exists ? "Zmień obrazek" : "Wgraj obrazek"}
          <input type="file" accept="image/*" className="hidden" disabled={busy} onChange={upload} />
        </label>
        {exists && (
          <button
            className="btn-secondary px-3 py-1.5 text-xs hover:border-red-500 hover:text-red-300"
            onClick={remove}
            aria-label="Usuń obrazek"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
      {err && <p className="text-xs text-red-300">{err}</p>}

      {open && exists && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" onClick={() => setOpen(false)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={src} alt={title} className="max-h-[92vh] max-w-[92vw] rounded-lg object-contain" onClick={(e) => e.stopPropagation()} />
          <button className="btn-secondary absolute right-4 top-4 px-2 py-1" onClick={() => setOpen(false)} aria-label="Zamknij">
            <X size={18} />
          </button>
        </div>
      )}
    </div>
  );
}
