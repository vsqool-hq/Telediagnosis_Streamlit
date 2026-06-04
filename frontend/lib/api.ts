// Klient API backendu FastAPI.
// Bazowy URL i opcjonalny token z publicznych zmiennych środowiskowych.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8080";

const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || "";

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return API_TOKEN ? { "X-API-Token": API_TOKEN, ...extra } : extra;
}

// Token doklejany do URL-i używanych przez EventSource / pobieranie plików
export function withToken(url: string): string {
  if (!API_TOKEN) return url;
  return url + (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(API_TOKEN);
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
  clients_count?: number;
  by_modality?: { modality: string; count: number }[];
  top_clients?: { client: string; count: number }[];
}

// ---- Wywołania --------------------------------------------------------------

export const api = {
  overview: () => req<Overview>("/api/stats/overview"),
  jobStats: (id: string) => req<JobStats>(`/api/stats/job/${id}`),

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

  getSettings: () => req<{ settings: any; defaults: any }>("/api/settings"),
  saveSettings: (settings: any) =>
    req("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings }),
    }),
  resetSettings: () => req("/api/settings/reset", { method: "POST" }),
};
