"use client";

import { useEffect, useRef, useState } from "react";
import { UploadCloud, Play, Search, Download, Loader2, CheckCircle2, XCircle, FileSpreadsheet } from "lucide-react";
import { api, Job } from "@/lib/api";

type Phase = "idle" | "running" | "done" | "error";

export default function RozliczeniePage() {
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [logs, setLogs] = useState<string[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const logBoxRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    logBoxRef.current?.scrollTo(0, logBoxRef.current.scrollHeight);
  }, [logs]);

  useEffect(() => () => esRef.current?.close(), []);

  // Po wejściu na stronę: jeśli z banera przyszedł ?job=ID, albo gdzieś trwa
  // rozliczenie — podłącz się i wznów podgląd logów (odtwarzane z pliku).
  useEffect(() => {
    const qid = new URLSearchParams(window.location.search).get("job");
    if (qid) {
      attach(qid);
      return;
    }
    api.activeJob().then((j) => {
      if (j && (j.live_status === "running" || j.status === "running" ||
                j.live_status === "queued" || j.status === "queued")) {
        attach(j.id);
      }
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Otwiera strumień logów zadania (nowego lub już trwającego) i śledzi go do końca. */
  function attach(jobId: string) {
    esRef.current?.close();
    setPhase("running");
    setLogs([]);
    setError(null);
    api.getJob(jobId).then(setJob).catch(() => {});

    const es = new EventSource(api.logsUrl(jobId));
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        setLogs((prev) => [...prev, JSON.parse(e.data)]);
      } catch {
        setLogs((prev) => [...prev, e.data]);
      }
    };
    es.addEventListener("end", async (e: Event) => {
      es.close();
      const status = JSON.parse((e as MessageEvent).data).status;
      const refreshed = await api.getJob(jobId).catch(() => null);
      if (refreshed) setJob(refreshed);
      setPhase(status === "done" ? "done" : "error");
    });
    es.onerror = () => {
      es.close();
      setPhase((p) => (p === "running" ? "error" : p));
    };
  }

  async function run(mode: "full" | "unmatched") {
    if (!file) return;
    setPhase("running");
    setLogs([]);
    setError(null);
    setJob(null);
    try {
      const created = await api.createJob(file, mode);
      attach(created.id);
    } catch (e: any) {
      setError(e.message);
      setPhase("error");
    }
  }

  const busy = phase === "running";

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Rozliczenie</h1>
        <p className="text-sm text-slate-400">
          Wgraj miesięczny plik z danymi jednostek i uruchom proces. Pliki wzorcowe i cennik
          pobierane są z aktywnych wersji (zakładki obok).
        </p>
      </header>

      <div className="card">
        <label className="flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-brand-border/70 py-10 text-center transition-colors hover:border-brand-accent">
          <UploadCloud className="text-brand-accent" size={36} />
          <span className="text-sm">
            {file ? (
              <span className="font-semibold text-white">{file.name}</span>
            ) : (
              <>Kliknij, aby wybrać plik <span className="text-slate-400">(.xlsx / .xls)</span></>
            )}
          </span>
          <input
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            disabled={busy}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <div className="mt-5 flex flex-wrap gap-3">
          <button className="btn-primary" disabled={!file || busy} onClick={() => run("full")}>
            {busy ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} />}
            Uruchom pełny proces
          </button>
          <button className="btn-secondary" disabled={!file || busy} onClick={() => run("unmatched")}>
            <Search size={18} />
            Tylko braki wzorca
          </button>

          {phase === "done" && job && (
            <div className="ml-auto flex flex-wrap gap-2">
              <a className="btn-primary" href={api.resultUrl(job.id)}>
                <Download size={18} />
                Pobierz wyniki
              </a>
              {job.mode === "full" && (
                <a className="btn-secondary" href={api.importExportUrl(job.id, "xlsx")}>
                  <FileSpreadsheet size={18} />
                  Plik importowy
                </a>
              )}
            </div>
          )}
        </div>
      </div>

      {error && <div className="card border-red-500/40 text-red-300">{error}</div>}

      {(logs.length > 0 || busy) && (
        <div className="card">
          <div className="mb-3 flex items-center gap-2">
            {phase === "running" && <Loader2 className="animate-spin text-brand-accent" size={18} />}
            {phase === "done" && <CheckCircle2 className="text-brand-accent" size={18} />}
            {phase === "error" && <XCircle className="text-red-400" size={18} />}
            <h2 className="text-lg font-semibold">Logi procesu</h2>
          </div>
          <div
            ref={logBoxRef}
            className="h-96 overflow-auto rounded-xl bg-black/40 p-4 font-mono text-xs leading-relaxed text-slate-300"
          >
            {logs.map((line, i) => (
              <div key={i} className="whitespace-pre-wrap">{line}</div>
            ))}
            {busy && <div className="animate-pulse text-brand-accent">▌</div>}
          </div>

          {phase === "done" && job?.files && job.files.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-sm font-semibold text-slate-300">
                Pliki wynikowe ({job.files.length}):
              </p>
              <div className="flex flex-wrap gap-2">
                {job.files.map((f) => (
                  <a
                    key={f}
                    href={`${api.resultUrl(job.id).replace("/result", "/result/" + encodeURIComponent(f))}`}
                    className="rounded-lg border border-brand-border bg-brand-bg/50 px-3 py-1.5 text-xs hover:border-brand-accent"
                  >
                    {f}
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
