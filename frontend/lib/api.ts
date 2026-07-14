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

/** Klucz dopasowania lekarza — port `doctor_key()` z backendu (cennik_lekarzy_convert.py),
 * niewrażliwy na kolejność imię/nazwisko, wielkość liter i łączniki vs spacje. Używany do
 * odnalezienia historii wypłat lekarza (klucze z /api/doctors/revenue-history są tak liczone). */
export function doctorKey(name: string | null | undefined): string {
  const s = (name || "")
    .replace(/[-‐-―−]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toUpperCase();
  if (!s) return "";
  return s.split(" ").sort().join(" ");
}

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
  uploaded_by?: string | null;
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
  period?: string | null;   // miesiąc rozliczenia „YYYY-MM" (z nazwy pliku − 1 mies.)
  created_by?: string | null;
}

// Unikalny wgrany plik (bez mnożenia przez kolejne przeliczenia). „monthly" =
// plik miesięczny (1. dzień miesiąca w nazwie), „oneoff" = jednorazowy.
export interface JobFile {
  kind: "monthly" | "oneoff";
  period: string | null;
  input_name: string;
  job_id: string;            // najlepsze (miesięczny) / najnowsze (jednorazowy) przeliczenie
  revenue: number | null;
  studies: number | null;
  computed_at: string | null;
  status?: string;
  job_ids: string[];         // wszystkie przeliczenia tej pozycji (do usunięcia całości)
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
  period?: string;
  job_id?: string;
  total_studies?: number;
  total_revenue?: number;
  clients_count?: number;
  zero_clients?: { client: string; studies: number; in_cennik: boolean; suggestions: string[] }[];
  zero_rate_studies?: number;
  zero_rates?: { jednostka: string; kategoria: string; n: number }[];
  by_modality?: { modality: string; count: number; revenue: number }[];
  top_clients?: { client: string; count: number; revenue: number }[];
}

// ---- Windykacja ---------------------------------------------------------------

export type ReceivableStatus =
  | "wystawiona" | "czesciowo_oplacona" | "oplacona" | "sporna" | "odpisana";

export interface Installment {
  id: string;
  receivable_id: string;
  label: string | null;
  amount: number;
  due_date: string | null;
  status: string;
  paid_amount: number;
  paid_at: string | null;
  note: string | null;
  created_at: string;
}

export interface ReceivableHistoryEntry {
  id: string;
  field: string;
  old_value: string | null;
  new_value: string | null;
  reason: string | null;
  changed_at: string;
}

export type ReceivableItemKind = "kara" | "korekta" | "inne";

export interface ReceivableItem {
  id: string;
  receivable_id: string;
  kind: ReceivableItemKind;
  label: string | null;
  amount: number;
  item_date: string | null;
  note: string | null;
  created_at: string;
}

export interface Payment {
  id: string;
  receivable_id: string;
  installment_id: string | null;
  amount: number;
  paid_at: string;
  note: string | null;
  created_at: string;
}

export interface Receivable {
  id: string;
  unit_key: string;
  unit_name: string;
  period: string | null;
  source_amount: number;
  amount_due: number;
  paid_amount: number;
  status: ReceivableStatus;
  due_date: string | null;
  note: string | null;
  source_run_id: string | null;
  source_changed: number;
  created_at: string;
  updated_at: string;
  remaining: number;
  is_overdue: boolean;
  days_overdue: number;
  installments: Installment[];
  installments_count: number;
  installments_balanced: boolean;
  items: ReceivableItem[];
  items_total: number;
  payments: Payment[];
  history?: ReceivableHistoryEntry[];
}

export interface WindykacjaSummary {
  overdue_amount: number;
  overdue_count: number;
  due_this_week_amount: number;
  due_this_week_count: number;
  paid_this_month_amount: number;
  paid_this_month_count: number;
  total_balance: number;
}

export interface CashflowBucket {
  index: number;
  start: string;
  end: string;
  label: string;
  inflow_actual: number;
  inflow_forecast: number;
  outflow_forecast: number;
  balance_actual: number | null;
  balance_forecast: number | null;
  net: number;
}

export interface CashflowOverview {
  generated_at: string;
  doctor_cost_payment_term_days: number;
  buckets: CashflowBucket[];
  kpis: {
    balance_to_date: number;
    overdue_amount: number;
    forecast_inflow_90d: number;
    forecast_outflow_90d: number;
    forecast_net_90d: number;
    revenue_forecast_total: number;
    doctor_cost_forecast_total: number;
  };
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

export interface AvailabilityItem { label: string; hours: number; rate: number; amount: number; no_rate?: boolean }
export interface Availability {
  period: string;
  doctors: Record<string, { name: string; items: AvailabilityItem[]; total: number }>;
  sum_total: number;
  sum_gotowosc: number;
  sum_triaz: number;
  hours_gotowosc?: number;
  hours_triaz?: number;
  unbilled_hours?: number;
  unbilled?: { name: string; label: string; hours: number }[];
  unmatched_hours?: number;
  unmatched: string[];
}

export interface DoctorBilling {
  empty: boolean;
  reason?: string;
  computed_at?: string | null;
  files_count?: number;
  availability?: Availability;
  availability_error?: string;
  rows?: { lekarz: string; kategoria: string; ilosc: number; stawka: number; wartosc: number }[];
  by_doctor?: { lekarz: string; ilosc: number; wartosc: number; gotowosc?: number }[];
  validation?: {
    total_studies: number;
    priced_studies: number;
    studies_without_category: number;
    n_doctors: number;
    total_value: number;
    value_studies?: number;
    value_availability?: number;
    doctors_unmatched: string[];
    pairs_without_price: { _lek_disp: string; _kategoria: string; n: number }[];
    zero_rate_studies?: number;
    zero_rate_pairs?: { lekarz: string; kategoria: string; n: number }[];
  };
}

export interface CompareMonth {
  period: string;        // "YYYY-MM"
  job_id: string;        // największe przeliczenie tego miesiąca
  revenue: number;
  computed: boolean;     // czy porównanie dla tego zadania jest już policzone
  computed_at?: string | null;
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
  rows_priority?: {
    priorytet: string; ilosc: number;
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
    gotowosc_triaz?: number; gotowosc_triaz_nieprzypisane?: number;
    wsparcie?: number; wsparcie_nieprzypisane?: number;
  };
}

export interface MapUnit {
  key: string;
  miasto: string;
  lat: number;
  lng: number;
  months: Record<string, number>;
  latest: number;
}
export interface MapData {
  months: string[];
  units: MapUnit[];
  missing_geo: string[];
  geocoded: number;
}

export interface TrendPoint {
  job_id: string;
  date: string;
  label: string;
  studies: number;
  revenue: number;
}

export interface DashboardData {
  overview: Overview;
  current: JobStats;
  trends: { points: TrendPoint[] };
}

// ---- Wywołania --------------------------------------------------------------

export interface SyncResult {
  synced: Record<string, string | null>;
  errors: Record<string, string>;
}

export interface Account { id: number; username: string; role: string; created_at: string }
export interface AuditEntry { id: number; ts: string; username: string | null; action: string; detail: string | null }
export interface Me { role: string | null; username: string | null; auth_enabled: boolean }

export const api = {
  // Walidacja tokenu/sesji — 200 oznacza autoryzację (lub wyłączony token w backendzie).
  validate: () => req("/api/settings"),

  // ---- Logowanie / role -----------------------------------------------------
  login: (username: string, password: string) =>
    req<{ token: string; username: string; role: string }>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  me: () => req<Me>("/api/auth/me"),
  logout: () => req("/api/auth/logout", { method: "POST" }).catch(() => {}),
  listUsers: () => req<{ users: Account[] }>("/api/users").then((r) => r.users),
  createUser: (username: string, password: string, role: string) =>
    req<Account>("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, role }),
    }),
  updateUser: (id: number, payload: { password?: string; role?: string }) =>
    req(`/api/users/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteUser: (id: number) => req(`/api/users/${id}`, { method: "DELETE" }),
  listAudit: (limit = 300) =>
    req<{ entries: AuditEntry[] }>(`/api/audit?limit=${limit}`).then((r) => r.entries),

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

  // Wyślij wgraną lokalnie wersję pliku (słownik/cennik/cennik lekarzy + plik
  // zobowiązań) do chmury i ustaw ją tam aktywną — żeby ten sam plik był od razu online.
  pushVersionToCloud: (kind: string, versionId: string) =>
    req("/api/sync/push-version", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cloud_base: CLOUD_BASE, token: getToken(), kind, version_id: versionId }),
    }),

  overview: () => req<Overview>("/api/stats/overview"),
  jobStats: (id: string) => req<JobStats>(`/api/stats/job/${id}`),
  statsCurrent: () => req<JobStats>("/api/stats/current"),
  trends: () => req<{ points: TrendPoint[] }>("/api/stats/trends"),
  dashboard: () => req<DashboardData>("/api/stats/dashboard"),
  mapData: () => req<MapData>("/api/stats/map"),
  unitsRevenueHistory: () =>
    req<{ units: Record<string, Record<string, number>> }>("/api/stats/revenue-history/units"),
  importExportUrl: (id: string, fmt: "csv" | "xlsx") =>
    withToken(`${API_BASE}/api/jobs/${id}/import-export?fmt=${fmt}`),

  listJobs: () => req<Job[]>("/api/jobs"),
  listFiles: () => req<{ files: JobFile[] }>("/api/jobs/files"),
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
  deleteJob: (id: string) => req<{ ok: boolean }>(`/api/jobs/${id}`, { method: "DELETE" }),
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
  // Obrazki-wzory dla miejsc wgrywania (slot: wzorcowe/cennik/cennik_lekarzy/rozliczenie).
  referenceImageUrl: (slot: string, v = 0) =>
    withToken(`${API_BASE}/api/reference-image/${slot}?v=${v}`),
  uploadReferenceImage: (slot: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<{ ok: boolean; ext: string }>(`/api/reference-image/${slot}`, { method: "POST", body: fd });
  },
  deleteReferenceImage: (slot: string) =>
    req(`/api/reference-image/${slot}`, { method: "DELETE" }),
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
  doctorsAvailabilityUrl: (jobId: string) => withToken(`${API_BASE}/api/doctors/billing/${jobId}/availability`),
  doctorsCompare: (jobId: string, opts: { peek?: boolean; recompute?: boolean } = {}) =>
    req<DoctorComparison>(`/api/doctors/compare/${jobId}?peek=${!!opts.peek}&recompute=${!!opts.recompute}`),
  doctorsCompareLatest: () => req<DoctorComparison>("/api/doctors/compare/latest"),
  doctorsCompareMonths: () => req<{ months: CompareMonth[] }>("/api/doctors/compare/months"),
  doctorsCompareDownloadUrl: (jobId: string) => withToken(`${API_BASE}/api/doctors/compare/${jobId}/download`),
  doctorsRevenueHistory: () =>
    req<{ doctors: Record<string, Record<string, number>>; names: Record<string, string> }>(
      "/api/doctors/revenue-history",
    ),
  doctorsList: () =>
    req<{ job_id: string | null; doctors: { name: string; key: string; excluded: boolean }[] }>("/api/doctors/list"),
  setDoctorsExcluded: (keys: string[]) =>
    req<{ ok: boolean; doctors_excluded: string[] }>("/api/doctors/excluded", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys }),
    }),
  unitsList: () =>
    req<{ job_id: string | null; units: { name: string; key: string; excluded: boolean }[] }>("/api/units"),
  teamupConfig: () =>
    req<{ has_key: boolean; key_from_env: boolean; key_source: string; env_names: string[];
      cal_gotowosc: string; cal_triaz: string }>("/api/teamup/config"),
  saveTeamupConfig: (payload: { api_key?: string; cal_gotowosc?: string; cal_triaz?: string }) =>
    req<{ ok: boolean; has_key: boolean }>("/api/teamup/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  teamupTest: () =>
    req<Record<string, {
      ok: boolean; events?: number; sample?: string[]; error?: string;
      pola_wszystkie?: Record<string, string[]>;
      pola_wlasne?: { title: string; wykryty_tryb: string | null }[];
    }>>("/api/teamup/test"),
  setUnitsExcluded: (keys: string[]) =>
    req<{ ok: boolean; units_excluded: string[] }>("/api/units/excluded", {
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

  windykacjaList: (params: { period?: string; status?: string; unit?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.period) q.set("period", params.period);
    if (params.status) q.set("status", params.status);
    if (params.unit) q.set("unit", params.unit);
    const qs = q.toString();
    return req<{ receivables: Receivable[] }>(`/api/windykacja/receivables${qs ? `?${qs}` : ""}`);
  },
  windykacjaSummary: (period?: string) =>
    req<WindykacjaSummary>(`/api/windykacja/summary${period ? `?period=${period}` : ""}`),
  windykacjaGet: (id: string) => req<Receivable>(`/api/windykacja/receivables/${id}`),
  windykacjaCreate: (payload: {
    unit_key: string; unit_name?: string; amount_due: number; period?: string;
    due_date?: string; status?: string; note?: string;
  }) =>
    req<Receivable>("/api/windykacja/receivables", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  windykacjaEdit: (id: string, payload: {
    amount_due?: number; due_date?: string; status?: string; note?: string; unit_name?: string; reason?: string;
  }) =>
    req<Receivable>(`/api/windykacja/receivables/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  windykacjaDelete: (id: string) =>
    req<{ ok: boolean }>(`/api/windykacja/receivables/${id}`, { method: "DELETE" }),
  windykacjaSetInstallments: (id: string, items: Array<{
    id?: string; label?: string; amount: number; due_date?: string; note?: string;
  }>) =>
    req<Receivable>(`/api/windykacja/receivables/${id}/installments`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items }),
    }),
  windykacjaPayInstallment: (receivableId: string, installmentId: string, amount: number, paidAt?: string, note?: string) =>
    req<Receivable>(`/api/windykacja/receivables/${receivableId}/installments/${installmentId}/pay`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount, paid_at: paidAt, note }),
    }),
  windykacjaPay: (id: string, amount: number, paidAt?: string, note?: string) =>
    req<Receivable>(`/api/windykacja/receivables/${id}/pay`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount, paid_at: paidAt, note }),
    }),
  windykacjaAddItem: (id: string, payload: {
    kind: ReceivableItemKind; amount: number; label?: string; item_date?: string; note?: string;
  }) =>
    req<Receivable>(`/api/windykacja/receivables/${id}/items`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  windykacjaDeleteItem: (id: string, itemId: string) =>
    req<Receivable>(`/api/windykacja/receivables/${id}/items/${itemId}`, { method: "DELETE" }),
  windykacjaSync: () =>
    req<{ created: number; updated: number; flagged: number }>("/api/windykacja/sync", { method: "POST" }),
  windykacjaPaymentTerms: () =>
    req<{ default_days: number; doctor_cost_days: number; terms: Record<string, number> }>(
      "/api/windykacja/payment-terms",
    ),
  windykacjaSavePaymentTerms: (payload: {
    default_days?: number; doctor_cost_days?: number; terms?: Record<string, number>;
  }) =>
    req<{ default_days: number; doctor_cost_days: number; terms: Record<string, number> }>(
      "/api/windykacja/payment-terms",
      { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
    ),

  cashflowOverview: () => req<CashflowOverview>("/api/cashflow/overview"),
};
