"use client";

import { useEffect, useRef, useState } from "react";
import { UploadCloud, CheckCircle2, Download, Trash2, Star } from "lucide-react";
import { api, Version } from "@/lib/api";

function fmtSize(bytes: number) {
  if (bytes > 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + " MB";
  if (bytes > 1024) return (bytes / 1024).toFixed(0) + " KB";
  return bytes + " B";
}

export default function VersionManager({
  kind,
  title,
  description,
  accept,
  embedded = false,
}: {
  kind: "wzorcowe" | "cennik";
  title: string;
  description: string;
  accept: string;
  embedded?: boolean;
}) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [label, setLabel] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function refresh() {
    api.listVersions(kind).then(setVersions).catch((e) => setError(e.message));
  }
  useEffect(refresh, [kind]);

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadVersion(kind, file, label);
      setLabel("");
      if (fileRef.current) fileRef.current.value = "";
      refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  async function activate(id: string) {
    await api.activateVersion(kind, id).catch((e) => setError(e.message));
    refresh();
  }
  async function remove(id: string) {
    if (!confirm("Usunąć tę wersję?")) return;
    await api.deleteVersion(kind, id).catch((e) => setError(e.message));
    refresh();
  }

  return (
    <div className="space-y-6">
      <header>
        {embedded ? (
          <h2 className="text-lg font-semibold">{title}</h2>
        ) : (
          <h1 className="text-2xl font-bold">{title}</h1>
        )}
        <p className="text-sm text-slate-400">{description}</p>
      </header>

      <div className="card space-y-4">
        <h2 className="font-semibold">Wgraj nową wersję</h2>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <input ref={fileRef} type="file" accept={accept} className="input sm:max-w-xs" />
          <input
            className="input sm:flex-1"
            placeholder="Opis wersji (opcjonalnie), np. 'Cennik 2026 Q1'"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <button className="btn-primary" disabled={uploading} onClick={upload}>
            <UploadCloud size={18} />
            {uploading ? "Wgrywanie…" : "Wgraj"}
          </button>
        </div>
      </div>

      {error && <div className="card border-red-500/40 text-red-300">{error}</div>}

      <div className="card">
        <h2 className="mb-4 font-semibold">Wersje ({versions.length})</h2>
        {versions.length === 0 ? (
          <p className="text-sm text-slate-400">Brak wgranych wersji.</p>
        ) : (
          <div className="space-y-2">
            {versions.map((v) => (
              <div
                key={v.id}
                className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 ${
                  v.is_active ? "border-brand-accent/60 bg-brand-accent/10" : "border-brand-border/60 bg-brand-bg/30"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{v.original_name}</span>
                    {v.is_active === 1 && (
                      <span className="flex items-center gap-1 rounded-full bg-brand-accent/20 px-2 py-0.5 text-xs text-brand-accent">
                        <CheckCircle2 size={12} /> Aktywna
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400">
                    {v.label && <span>{v.label} · </span>}
                    {fmtSize(v.size)} · {new Date(v.uploaded_at).toLocaleString("pl-PL")}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {v.is_active !== 1 && (
                    <button className="btn-secondary px-3 py-1.5 text-xs" onClick={() => activate(v.id)}>
                      <Star size={14} /> Ustaw aktywną
                    </button>
                  )}
                  <a className="btn-secondary px-3 py-1.5 text-xs" href={api.versionDownloadUrl(kind, v.id)}>
                    <Download size={14} />
                  </a>
                  <button
                    className="btn-secondary px-3 py-1.5 text-xs hover:border-red-500 hover:text-red-300 disabled:opacity-40"
                    disabled={v.is_active === 1}
                    onClick={() => remove(v.id)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
