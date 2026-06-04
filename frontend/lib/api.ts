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

export interface Version {
  id: string;
  kind: "wzorcowe" | "cennik";
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

  getSettings: () => req<{ settings: any; defaults: any }>("/api/settings"),
  saveSettings: (settings: any) =>
    req("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings }),
    }),
  resetSettings: () => req("/api/settings/reset", { method: "POST" }),
};
