// Klient API backendu FastAPI.
// Bazowy URL i opcjonalny token z publicznych zmiennych środowiskowych.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8080";

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
  rows?: {
    "Modalność": string; kategoria: string; ilosc: number;
    przychod_jednostki: number; koszt_lekarzy: number; marza: number;
  }[];
  totals?: {
    przychod_jednostki: number; koszt_lekarzy: number; marza: number;
    studies: number; studies_without_category: number;
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

export const api = {
  // Walidacja tokenu/sesji — 200 oznacza autoryzację (lub wyłączony token w backendzie).
  validate: () => req("/api/settings"),

  overview: () => req<Overview>("/api/stats/overview"),
  jobStats: (id: string) => req<JobStats>(`/api/stats/job/${id}`),
  trends: () => req<{ points: TrendPoint[] }>("/api/stats/trends"),
  importExportUrl: (id: string, fmt: "csv" | "xlsx") =>
    withToken(`${API_BASE}/api/jobs/${id}/import-export?fmt=${fmt}`),

  listJobs: () => req<Job[]>("/api/jobs"),
  getJob: (id: string) => req<Job>(`/api/jobs/${id}`),

  createJob: (file: File, mode: "full" | "unmatched") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mode", mode);
    return req<Job>("/api/jobs", { method: "POST", body: fd });
  },

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
  doctorsBilling: (jobId: string) => req<DoctorBilling>(`/api/doctors/billing/${jobId}`),
  doctorsCompare: (jobId: string) => req<DoctorComparison>(`/api/doctors/compare/${jobId}`),

  getSettings: () => req<{ settings: any; defaults: any }>("/api/settings"),
  saveSettings: (settings: any) =>
    req("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings }),
    }),
  resetSettings: () => req("/api/settings/reset", { method: "POST" }),
};
