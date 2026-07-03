"use client";

import { useEffect, useRef, useState } from "react";
import { UploadCloud, Play, Search, Download, Loader2, CheckCircle2, XCircle, FileSpreadsheet, Square, Clock, FileText, History, Trash2, Calendar } from "lucide-react";
import { api, Job, JobFile, isLocalBackend } from "@/lib/api";
import { invalidateCache } from "@/lib/cache";
import ReferenceImage from "@/components/ReferenceImage";

type Phase = "idle" | "running" | "done" | "error";

function fmtDuration(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(ss)}` : `${m}:${pad(ss)}`;
}

export default function RozliczeniePage() {
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [logs, setLogs] = useState<string[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [files, setFiles] = useState<JobFile[]>([]);   // UNIKALNE wgrane pliki (bez duplikatów przeliczeń)
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState<number>(Date.now());
  const startAnchor = useRef<number | null>(null);  // chwila startu zadania w zegarze klienta
  const logBoxRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    logBoxRef.current?.scrollTo(0, logBoxRef.current.scrollHeight);
  }, [logs]);

  useEffect(() => () => esRef.current?.close(), []);

  // Tykanie licznika co sekundę, tylko gdy trwa przeliczenie.
  useEffect(() => {
    if (phase !== "running") return;
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [phase]);

  // Ustaw „kotwicę" startu z czasu serwera (elapsed_seconds), unikając stref czasowych.
  function anchorFrom(j: Job) {
    if (j.elapsed_seconds != null) startAnchor.current = Date.now() - j.elapsed_seconds * 1000;
  }

  // Po wejściu na stronę: ?job=ID z banera → pokaż to zadanie; w toku → wznów
  // podgląd logów na żywo. Gdy NIC nie trwa — log zostaje PUSTY (pokazujemy tylko
  // nazwę ostatniego pliku i przyciski pobierania, bez odtwarzania starego logu).
  useEffect(() => {
    loadJobs();
    const qid = new URLSearchParams(window.location.search).get("job");
    if (qid) {
      attach(qid);
      return;
    }
    const showLatestMeta = () =>
      api.listJobs().then((all) => { if (all.length) loadJobMeta(all[0].id); }).catch(() => {});
    api.activeJob().then((j) => {
      if (j && (j.live_status === "running" || j.status === "running" ||
                j.live_status === "queued" || j.status === "queued")) {
        attach(j.id);  // tylko trwające zadanie odtwarza log na żywo
      } else {
        showLatestMeta();
      }
    }).catch(showLatestMeta);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Wczytuje SAME metadane zadania (nazwa pliku, wyniki) — bez logów. */
  function loadJobMeta(jobId: string) {
    api.getJob(jobId).then((j) => {
      setJob(j);
      anchorFrom(j);
      setLogs([]);  // log pusty, gdy nic nie trwa
      setPhase(j.status === "done" ? "done" : "idle");
    }).catch(() => {});
  }

  /** Odświeża historię UNIKALNYCH wgranych plików (bez mnożenia przez przeliczenia). */
  function loadJobs() {
    api.listFiles().then((r) => setFiles(r.files)).catch(() => {});
  }

  /** Usuwa całą pozycję (wszystkie przeliczenia tego pliku/miesiąca) i odświeża listę. */
  async function deleteFile(f: JobFile) {
    const label = f.kind === "monthly" ? `rozliczenie miesiąca ${f.period}` : `plik „${f.input_name}"`;
    const extra = f.job_ids.length > 1 ? ` (${f.job_ids.length} przeliczeń)` : "";
    if (!confirm(`Usunąć ${label}${extra}? Tej operacji nie można cofnąć.`)) return;
    setDeleting(f.job_id);
    setError(null);
    try {
      for (const id of f.job_ids) await api.deleteJob(id).catch(() => {});
      if (job && f.job_ids.includes(job.id)) { setJob(null); setPhase("idle"); setLogs([]); }
      loadJobs();
      invalidateCache();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDeleting(null);
    }
  }

  /** Wybiera plik z historii — staje się „ostatnim plikiem" do przeliczenia.
   * Czyści świeżo wybrany plik, żeby przyciski działały na tym z historii. */
  function selectJob(jobId: string) {
    if (phase === "running") return;
    esRef.current?.close();
    setFile(null);
    setError(null);
    loadJobMeta(jobId);
  }

  /** Otwiera strumień logów zadania (nowego lub już trwającego) i śledzi go do końca. */
  function attach(jobId: string) {
    esRef.current?.close();
    setPhase("running");
    setLogs([]);
    setError(null);
    startAnchor.current = null;
    api.getJob(jobId).then((j) => { setJob(j); anchorFrom(j); }).catch(() => {});

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
      loadJobs();  // nowo wgrany/policzony plik pojawia się w historii
      invalidateCache();  // świeże wyniki zastępują zapamiętane (Pulpit, Historia, ...)

      // Liczenie „na tym komputerze" → automatycznie wyślij wynik do chmury,
      // żeby zadanie i wgrany plik były później widoczne online.
      if (status === "done" && isLocalBackend()) {
        setLogs((prev) => [...prev, "☁ Wysyłam wynik do chmury…"]);
        api.pushToCloud(jobId)
          .then(() => setLogs((prev) => [...prev, "☁ Wysłano do chmury — widoczne online."]))
          .catch((e) => setLogs((prev) => [...prev, "☁ Nie udało się wysłać do chmury: " + e.message]));
      }
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

  /** Ponowne przeliczenie na tym samym, wcześniej wgranym pliku (bez wgrywania).
   * Tryb jest wybierany jawnie, więc z ostatniego pliku można uruchomić zarówno
   * pełny proces, jak i same braki wzorca — niezależnie od trybu pierwotnego. */
  async function rerun(jobId: string, mode: "full" | "unmatched") {
    setPhase("running");
    setLogs([]);
    setError(null);
    setJob(null);
    try {
      const created = await api.rerunJob(jobId, mode);
      attach(created.id);
    } catch (e: any) {
      setError(e.message);
      setPhase("error");
    }
  }

  /** Uruchamia dany tryb na ŚWIEŻO wybranym pliku, a gdy go nie ma — na ostatnim
   * wgranym (rerun). Dzięki temu oba tryby są dostępne zawsze. */
  function start(mode: "full" | "unmatched") {
    if (file) return run(mode);
    if (job) return rerun(job.id, mode);
  }

  /** Zatrzymuje trwające rozliczenie (przycisk STOP). */
  async function stop() {
    if (!job) return;
    try {
      await api.cancelJob(job.id);
      setLogs((prev) => [...prev, "■ Zatrzymywanie…"]);
    } catch (e: any) {
      setError(e.message);
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
            ) : job ? (
              <span className="text-slate-300">
                Ostatni plik: <span className="font-semibold text-white">{job.input_name}</span>
                <span className="text-slate-400"> — kliknij, aby wgrać nowy</span>
              </span>
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
          <button className="btn-primary" disabled={(!file && !job) || busy} onClick={() => start("full")}>
            {busy ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} />}
            {file ? "Uruchom pełny proces" : "Pełny proces (ostatni plik)"}
          </button>
          <button className="btn-secondary" disabled={(!file && !job) || busy} onClick={() => start("unmatched")}>
            <Search size={18} />
            {file ? "Tylko braki wzorca" : "Braki wzorca (ostatni plik)"}
          </button>
          {busy && job && (
            <button className="btn-secondary !border-red-500/50 !text-red-300 hover:!border-red-400" onClick={stop}>
              <Square size={16} /> Zatrzymaj
            </button>
          )}

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

      <div className="card space-y-2">
        <h2 className="font-semibold">Wzór pliku miesięcznego</h2>
        <p className="text-[13px] text-slate-400">
          Wgraj obrazek-przykład, jaki plik wgrywać tutaj — kliknij miniaturkę, aby powiększyć na cały ekran.
        </p>
        <ReferenceImage slot="rozliczenie" title="Wzór: plik miesięczny" />
      </div>

      {files.length > 0 && (
        <div className="card">
          <div className="mb-1 flex items-center gap-2">
            <History size={18} className="text-brand-accent" />
            <h2 className="text-lg font-semibold">Wgrane pliki</h2>
            <span className="text-xs text-slate-400">({files.length})</span>
          </div>
          <p className="mb-3 text-xs text-slate-400">
            Unikalne pliki (bez powtórek przeliczeń). „Miesięczne" (data 1. dnia miesiąca w nazwie)
            trafiają na Pulpit, do Historii, lekarzy i porównania — pokazujemy najwyższe przeliczenie.
            „Jednorazowe" liczymy na żądanie i nie używamy nigdzie indziej.
          </p>
          <div className="space-y-2">
            {files.map((f) => {
              const selected = job?.id === f.job_id;
              const isMonthly = f.kind === "monthly";
              return (
                <div
                  key={f.job_id}
                  className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 ${
                    selected ? "border-brand-accent/50 bg-brand-accent/10" : "border-white/10 bg-white/[0.02]"
                  }`}
                >
                  {isMonthly
                    ? <Calendar size={18} className="shrink-0 text-brand-accent" />
                    : <FileText size={18} className="shrink-0 text-slate-400" />}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-semibold">{f.input_name}</span>
                      {isMonthly
                        ? <span className="pill pill-ok">Miesięczny · {f.period}</span>
                        : <span className="pill pill-muted">Jednorazowy</span>}
                      {selected && <span className="pill pill-ok"><CheckCircle2 size={12} /> Wybrany</span>}
                    </div>
                    <p className="text-xs text-slate-400">
                      {f.computed_at ? `Ostatnie pełne przeliczenie: ${new Date(f.computed_at).toLocaleString("pl-PL")}` : "—"}
                      {f.job_ids.length > 1 ? ` · ${f.job_ids.length} przeliczeń` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      className="btn-secondary px-3 py-1.5 text-xs"
                      disabled={busy || selected}
                      onClick={() => selectJob(f.job_id)}
                    >
                      Wybierz
                    </button>
                    <a
                      className="btn-secondary px-3 py-1.5 text-xs"
                      href={api.inputUrl(f.job_id)}
                      title="Pobierz plik źródłowy"
                    >
                      <Download size={14} />
                    </a>
                    <button
                      className="btn-secondary px-3 py-1.5 text-xs hover:border-red-500 hover:text-red-300 disabled:opacity-40"
                      disabled={busy || deleting === f.job_id}
                      onClick={() => deleteFile(f)}
                      title="Usuń ten plik (wszystkie jego przeliczenia)"
                    >
                      {deleting === f.job_id ? <Loader2 className="animate-spin" size={14} /> : <Trash2 size={14} />}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {error && <div className="card border-red-500/40 text-red-300">{error}</div>}

      {(logs.length > 0 || busy) && (
        <div className="card">
          <div className="mb-3 flex items-center gap-2">
            {phase === "running" && <Loader2 className="animate-spin text-brand-accent" size={18} />}
            {phase === "done" && <CheckCircle2 className="text-brand-accent" size={18} />}
            {phase === "error" && <XCircle className="text-red-400" size={18} />}
            <h2 className="text-lg font-semibold">Logi procesu</h2>
            {phase === "running" && startAnchor.current != null && (
              <span className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-brand-accent/15 px-2.5 py-1 text-sm font-semibold text-brand-accent2"
                title="Czas od początku tego przeliczenia (liczony też przez wznowienia)">
                <Clock size={15} /> {fmtDuration((nowMs - startAnchor.current) / 1000)}
              </span>
            )}
            {phase !== "running" && job?.elapsed_seconds != null && logs.length > 0 && (
              <span className="ml-auto inline-flex items-center gap-1.5 text-sm text-slate-400">
                <Clock size={15} /> Czas liczenia: {fmtDuration(job.elapsed_seconds)}
              </span>
            )}
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
