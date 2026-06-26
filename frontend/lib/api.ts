// Klient API backendu FastAPI.
// Bazowy URL: można przełączać w aplikacji (Chmura ↔ Ten komputer) — wybór trzymany
// w localStorage; w razie braku używana jest zmienna środowiskowa (chmura).

// Adres chmury (wstrzykiwany przy buildzie na Vercel) i adres lokalnego backendu.
export const CLOUD_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8080";
export const LOCAL_BASE = "http://localhost:8080";
export const BASE_KEY = "teledag_api_base";

/** Aktualny adres backendu (wybór z localStorage albo domyślnie chmura). */
export function getApiBase(): string {
  if (typeof window !== "undefined") {
    const v = window.localStorage.getItem(BASE_KEY);
    if (v) return v.replace(/\/$/, "");
  }
  return CLOUD_BASE;
}

/** Zapisuje wybrany backend. Pusty/cloud → usuwa wpis (wraca do chmury). */
export function setApiBase(url: string) {
  if (typeof window === "undefined") return;
  if (!url || url.replace(/\/$/, "") === CLOUD_BASE) {
    window.localStorage.removeItem(BASE_KEY);
  } else {
    window.localStorage.setItem(BASE_KEY, url.replace(/\/$/, ""));
  }
}

/** Czy aktualnie liczymy lokalnie (na tym komputerze)? */
export function isLocalBackend(): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1)/.test(getApiBase());
}

// Wyliczane przy załadowaniu modułu (w przeglądarce). Zmiana backendu → przeładowanie strony.
export const API_BASE = getApiBase();

export const TOKEN_KEY = "teledag_token";

// Token: najpierw z localStorage (po zalogowaniu), w ostateczności ze zmiennej środowiskowej.
export function getToken(): string {
  if (typeof window !== "undefined") {
    const t = window.localStorage.getItem(TOKEN_KEY);
    if (t) return t;
  }
  return process.env.NEXT_PUBLIC_API_TOKEN || "";
}

export function setToken(token: string) {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getToken();
  return token ? { "X-API-Token": token, ...extra } : extra;
}

// Token doklejany do URL-i używanych przez EventSource / pobieranie plików
export function withToken(url: string): string {
  const token = getToken();
  if (!token) return url;
  return url + (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(token);
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(API_BASE + path, {
    ...init,
    headers: authHeaders(init.headers as Record<string, string>),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `Błąd ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ---- Typy -------------------------------------------------------------------

export type VersionKind = "wzorcowe" | "cennik" | "cennik_lekarzy";

export interface Version {
  id: string;
  kind: VersionKind;
  filename: string;
  original_name: string;
  label: string;
  size: number;
  is_active: number;
  uploaded_at: string;
}

export interface Job {
  id: string;
  mode: "full" | "unmatched";
  status: string;
  live_status?: string;
  input_name: string;
  wzorcowe_version: string | null;
  cennik_version: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  files?: string[];
  elapsed_seconds?: number;
}

export interface Overview {
  jobs_total: number;
  jobs_done: number;
  last_job: Job | null;
  active_wzorcowe: Version | null;
  active_cennik: Version | null;
  versions_wzorcowe: number;
  versions_cennik: number;
}

export interface JobStats {
  empty: boolean;
  total_studies?: number;
  total_revenue?: number;
  clients_count?: number;
  zero_clients?: { client: string; studies: number; in_cennik: boolean; suggestions: string[] }[];
  by_modality?: { modality: string; count: number; revenue: number }[];
  top_clients?: { client: string; count: number; revenue: number }[];
}

export interface CennikValidation {
  n_rows: number;
  n_badania: number;
  n_units: number;
  n_zeros: number;
  n_repaired: number;
  n_errors: number;
  n_duplicates: number;
  n_skipped_label?: number;
  stopped_at_wsparcie?: boolean;
  price_min: number;
  price_max: number;
  zeros_sample: [string, string][];
  repaired: { badanie: string; jednostka: string; z: string; na: string }[];
  errors: { badanie: string; jednostka: string; wartosc: string }[];
  duplicates: { badanie: string; jednostka: string }[];
  excluded_rows: string[];
  units: string[];
  badania: string[];
}

export interface CennikConversion {
  id: string;
  source_name: string;
  source_preview: { header: string[]; rows: string[][] };
  result_preview: { badanie: string; jednostka: string; cena: number }[];
  validation: CennikValidation;
}

// ---- Moduł lekarzy ----
export interface DoctorValidation {
  n_rows: number;
  n_doctors: number;
  n_categories: number;
  n_zeros: number;
  n_repaired: number;
  n_nonstandard: number;
  n_doctors_empty: number;
  price_min: number;
  price_max: number;
  repaired: { lekarz: string; kategoria: string; z: string; na: string }[];
  nonstandard: { lekarz: string; kategoria: string }[];
  doctors_empty: string[];
  skipped_sheets: string[];
  categories: string[];
}

export interface DoctorConversion {
  id: string;
  source_name: string;
  result_preview: { lekarz: string; kategoria: string; cena: number }[];
  validation: DoctorValidation;
}

export interface DoctorCoverage {
  doctor_cennik: { rows: number; doctors: number } | null;
  slownik_lekarz_filled: number;
  slownik_total: number;
  ready: boolean;
}

export interface DoctorBilling {
  empty: boolean;
  reason?: string;
  computed_at?: string | null;
  files_count?: number;
  rows?: { lekarz: string; kategoria: string; ilosc: number; stawka: number; wartosc: number }[];
  by_doctor?: { lekarz: string; ilosc: number; wartosc: number }[];
  validation?: {
    total_studies: number;
    priced_studies: number;
    studies_without_category: number;
    n_doctors: number;
    total_value: number;
    doctors_unmatched: string[];
    pairs_without_price: { _lek_disp: string; _kategoria: string; n: number }[];
  };
}

export interface DoctorComparison {
  empty: boolean;
  reason?: string;
  computed_at?: string | null;
  job_id?: string;
  rows?: {
    "Modalność": string; kategoria: string; ilosc: number;
    przychod_jednostki: number; koszt_lekarzy: number; marza: number;
  }[];
  rows_units?: {
    "Modalność": string; kategoria: string; ilosc: number;
    przychod_jednostki: number; koszt_lekarzy: number; marza: number;
  }[];
  by_doctor?: {
    lekarz: string; ilosc: number;
    przychod_jednostki: number; koszt_lekarzy: number; marza: number;
  }[];
  by_unit?: {
    jednostka: string; ilosc: number;
    przychod_jednostki: number; koszt_lekarzy: number; marza: number;
  }[];
  totals?: {
    przychod_jednostki: number; koszt_lekarzy: number; marza: number;
    studies: number; studies_without_category: number;
    studies_with_category?: number; przychod_jednostki_bez_kategorii?: number;
    przychod_jednostki_total?: number;
  };
}

export interface TrendPoint {
  job_id: string;
  date: string;
  label: string;
  studies: number;
  revenue: number;
}

// ---- Wywołania --------------------------------------------------------------

export interface SyncResult {
  synced: Record<string, string | null>;
  errors: Record<string, string>;
}

export const api = {
  // Walidacja tokenu/sesji — 200 oznacza autoryzację (lub wyłączony token w backendzie).
  validate: () => req("/api/settings"),

  // Pobiera aktywne pliki (słownik/cennik/cennik lekarzy) z chmury do bieżącego
  // (lokalnego) backendu. Wywoływane gdy liczymy „na tym komputerze".
  syncFromCloud: () =>
    req<SyncResult>("/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cloud_base: CLOUD_BASE, token: getToken() }),
    }),

  // Wyślij policzone lokalnie zadanie (wgrany plik + wyniki) do chmury — żeby było
  // widoczne online. Wywoływane przez lokalny backend (transfer serwer→serwer).
  pushToCloud: (jobId: string) =>
    req("/api/sync/push", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cloud_base: CLOUD_BASE, token: getToken(), job_id: jobId }),
    }),

  overview: () => req<Overview>("/api/stats/overview"),
  jobStats: (id: string) => req<JobStats>(`/api/stats/job/${id}`),
  trends: () => req<{ points: TrendPoint[] }>("/api/stats/trends"),
  importExportUrl: (id: string, fmt: "csv" | "xlsx") =>
    withToken(`${API_BASE}/api/jobs/${id}/import-export?fmt=${fmt}`),

  listJobs: () => req<Job[]>("/api/jobs"),
  activeJob: () => req<Job | null>("/api/jobs/active"),
  getJob: (id: string) => req<Job>(`/api/jobs/${id}`),

  createJob: (file: File, mode: "full" | "unmatched") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mode", mode);
    return req<Job>("/api/jobs", { method: "POST", body: fd });
  },

  rerunJob: (id: string, mode?: "full" | "unmatched") =>
    req<Job>(`/api/jobs/${id}/rerun${mode ? `?mode=${mode}` : ""}`, { method: "POST" }),
  cancelJob: (id: string) => req<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  logsUrl: (id: string) => withToken(`${API_BASE}/api/jobs/${id}/logs`),
  resultUrl: (id: string) => withToken(`${API_BASE}/api/jobs/${id}/result`),
  inputUrl: (id: string) => withToken(`${API_BASE}/api/jobs/${id}/input`),

  listVersions: (kind: string) => req<Version[]>(`/api/versions/${kind}`),
  uploadVersion: (kind: string, file: File, label: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("label", label);
    return req<Version>(`/api/versions/${kind}`, { method: "POST", body: fd });
  },
  activateVersion: (kind: string, id: string) =>
    req(`/api/versions/${kind}/${id}/activate`, { method: "POST" }),
  deleteVersion: (kind: string, id: string) =>
    req(`/api/versions/${kind}/${id}`, { method: "DELETE" }),
  versionDownloadUrl: (kind: string, id: string) =>
    withToken(`${API_BASE}/api/versions/${kind}/${id}/download`),

  convertCennik: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<CennikConversion>("/api/cennik/convert", { method: "POST", body: fd });
  },
  saveConvertedCennik: (id: string, label: string, filename: string) => {
    const fd = new FormData();
    fd.append("label", label);
    fd.append("filename", filename);
    return req<Version>(`/api/cennik/convert/${id}/save`, { method: "POST", body: fd });
  },
  convertedDownloadUrl: (id: string) => withToken(`${API_BASE}/api/cennik/convert/${id}/download`),

  // ---- Moduł lekarzy ----
  convertCennikLekarzy: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<DoctorConversion>("/api/cennik-lekarzy/convert", { method: "POST", body: fd });
  },
  saveConvertedCennikLekarzy: (id: string, label: string, filename: string) => {
    const fd = new FormData();
    fd.append("label", label);
    fd.append("filename", filename);
    return req<Version>(`/api/cennik-lekarzy/convert/${id}/save`, { method: "POST", body: fd });
  },
  convertedLekarzyDownloadUrl: (id: string) =>
    withToken(`${API_BASE}/api/cennik-lekarzy/convert/${id}/download`),

  doctorsCoverage: () => req<DoctorCoverage>("/api/doctors/coverage"),
  doctorsBilling: (jobId: string, opts: { peek?: boolean; recompute?: boolean } = {}) =>
    req<DoctorBilling>(`/api/doctors/billing/${jobId}?peek=${!!opts.peek}&recompute=${!!opts.recompute}`),
  // Liczenie biegnie w tle (osobny proces) — start + odpytywanie o status.
  doctorsBillingRun: (jobId: string, recompute = false) =>
    req<{ status: "running" | "done"; computed_at?: string | null }>(
      `/api/doctors/billing/${jobId}/run?recompute=${recompute}`, { method: "POST" }),
  doctorsBillingStatus: (jobId: string) =>
    req<{ status: "idle" | "running" | "done" | "error"; error?: string; computed_at?: string | null }>(
      `/api/doctors/billing/${jobId}/status`),
  doctorsBillingDownloadUrl: (jobId: string) => withToken(`${API_BASE}/api/doctors/billing/${jobId}/download`),
  doctorsBillingFilesUrl: (jobId: string) => withToken(`${API_BASE}/api/doctors/billing/${jobId}/files`),
  doctorsCompare: (jobId: string, opts: { peek?: boolean; recompute?: boolean } = {}) =>
    req<DoctorComparison>(`/api/doctors/compare/${jobId}?peek=${!!opts.peek}&recompute=${!!opts.recompute}`),
  doctorsCompareLatest: () => req<DoctorComparison>("/api/doctors/compare/latest"),
  doctorsCompareDownloadUrl: (jobId: string) => withToken(`${API_BASE}/api/doctors/compare/${jobId}/download`),
  doctorsList: () =>
    req<{ job_id: string | null; doctors: { name: string; key: string; excluded: boolean }[] }>("/api/doctors/list"),
  setDoctorsExcluded: (keys: string[]) =>
    req<{ ok: boolean; doctors_excluded: string[] }>("/api/doctors/excluded", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys }),
    }),

  getSettings: () => req<{ settings: any; defaults: any }>("/api/settings"),
  saveSettings: (settings: any) =>
    req("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings }),
    }),
  resetSettings: () => req("/api/settings/reset", { method: "POST" }),
  reseedAdjustments: () =>
    req<{ ok: boolean; unit_adjustments: Record<string, Record<string, { base: string; factor: number }>> }>(
      "/api/settings/adjustments/reseed",
      { method: "POST" },
    ),
};
