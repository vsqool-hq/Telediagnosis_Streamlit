"use client";

import { useEffect, useRef, useState } from "react";
import { UploadCloud, CheckCircle2, Download, Trash2, Star, FilePlus2 } from "lucide-react";
import { api, Version, MergeReport, isLocalBackend } from "@/lib/api";
import ReferenceImage from "@/components/ReferenceImage";
import { toast } from "@/lib/toast";

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
  allowAppend = false,
}: {
  kind: "wzorcowe" | "cennik" | "cennik_lekarzy";
  title: string;
  description: string;
  accept: string;
  embedded?: boolean;
  /** Pokaż sekcję „dosyłka" — doklejanie dodatkowego pliku do aktywnej wersji. */
  allowAppend?: boolean;
}) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [label, setLabel] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const addRef = useRef<HTMLInputElement>(null);
  const [appending, setAppending] = useState(false);
  const [merge, setMerge] = useState<MergeReport | null>(null);

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
      const created = await api.uploadVersion(kind, file, label);
      setLabel("");
      if (fileRef.current) fileRef.current.value = "";
      refresh();
      toast("Wgrano nową wersję.");
      // Liczenie „na tym komputerze": wyślij wgrany plik od razu do chmury,
      // żeby był widoczny online (best-effort — nie blokuje wgrania).
      if (isLocalBackend() && created?.id) {
        api.pushVersionToCloud(kind, created.id)
          .then(() => toast("Wysłano do chmury."))
          .catch((e) => toast("Nie wysłano do chmury: " + e.message));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  // Dosyłka: sklejamy wgrany plik z AKTYWNĄ wersją słownika → powstaje nowa wersja.
  async function appendToActive() {
    const file = addRef.current?.files?.[0];
    if (!file) return;
    setAppending(true);
    setError(null);
    setMerge(null);
    try {
      const created = await api.appendWzorcowe(file, label);
      setLabel("");
      if (addRef.current) addRef.current.value = "";
      setMerge(created.merge);
      refresh();
      toast(`Dosyłka wczytana: +${created.merge.added} nowych, ${created.merge.replaced} poprawionych.`);
      if (isLocalBackend() && created?.id) {
        api.pushVersionToCloud("wzorcowe", created.id)
          .then(() => toast("Wysłano do chmury."))
          .catch((e) => toast("Nie wysłano do chmury: " + e.message));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setAppending(false);
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
          <h2 className="text-lg font-bold">{title}</h2>
        ) : (
          <h1 className="text-[26px] font-extrabold tracking-tight">{title}</h1>
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

      {allowAppend && (
        <div className="card space-y-4">
          <div>
            <h2 className="flex items-center gap-2 font-semibold">
              <FilePlus2 size={18} className="text-brand-accent" /> Dosyłka do aktywnego słownika
            </h2>
            <p className="text-sm text-slate-400">
              Wgraj plik z samymi <b>nowymi lub poprawionymi</b> pozycjami — zostanie doklejony do
              aktywnej wersji, a wynik zapisany jako nowa wersja (poprzednia zostaje w historii).
              Jeżeli dosyłka powtarza pozycję po parze <i>Procedura + Rodzaj procedury rozlicz.</i>,
              zastępuje starą — dzięki temu poprawki faktycznie wchodzą w życie.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <input ref={addRef} type="file" accept={accept} className="input sm:max-w-xs" />
            <button className="btn-secondary" disabled={appending} onClick={appendToActive}>
              <FilePlus2 size={18} />
              {appending ? "Doklejanie…" : "Doklej do aktywnego"}
            </button>
          </div>
          {merge && (
            <div className="rounded-xl border border-brand-accent/40 bg-brand-accent/10 px-4 py-3 text-sm">
              <p className="font-medium text-brand-accent">Dosyłka wczytana</p>
              <p className="text-slate-300">
                Aktywny słownik miał <b>{merge.base_rows}</b> pozycji. Z dosyłki
                (<b>{merge.add_rows}</b>) doszło <b>{merge.added}</b> nowych, a <b>{merge.replaced}</b>{" "}
                zastąpiło istniejące wpisy. Nowa wersja ma <b>{merge.final_rows}</b> pozycji i jest już aktywna.
                {merge.new_columns.length > 0 && (
                  <> Doszły też kolumny: {merge.new_columns.join(", ")}.</>
                )}
              </p>
            </div>
          )}
        </div>
      )}

      <div className="card space-y-2">
        <h2 className="font-semibold">Wzór pliku w tym miejscu</h2>
        <p className="text-[13px] text-slate-400">
          Wgraj obrazek-przykład (zrzut ekranu), jaki plik tu wgrywać — osoba zastępująca kliknie
          miniaturkę, powiększy ją na cały ekran i od razu będzie wiedzieć, co tu wgrać.
        </p>
        <ReferenceImage slot={kind} title={`Wzór: ${title}`} />
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
                  v.is_active ? "border-brand-accent/50 bg-brand-accent/10" : "border-white/10 bg-white/[0.02]"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-semibold">{v.original_name}</span>
                    {v.is_active === 1 && (
                      <span className="pill pill-ok">
                        <CheckCircle2 size={12} /> Aktywna
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400">
                    {v.label && <span>{v.label} · </span>}
                    {fmtSize(v.size)} · {new Date(v.uploaded_at).toLocaleString("pl-PL")}
                    {v.uploaded_by && <span> · wgrał(a): {v.uploaded_by}</span>}
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
