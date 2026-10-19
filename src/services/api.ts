const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001";
export const API_BASE_URL = rawApiBaseUrl.replace(/\/$/, "");

const AUTH_TOKEN_KEY = "legacyDocToken";

const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;

export type FunctionArg = {
  name: string;
  type: string;
};

export type FunctionItem = {
  name: string;
  kind?: string;
  signature?: string;
  return_type?: string;
  args?: FunctionArg[];
  summary?: string;
  description?: string;
  raises?: string[];
};

export type GenerateResponse = {
  status?: string;
  file?: string;
  summary?: string;
  documentation?: FunctionItem[];
  pdf_url?: string;
  markdown_url?: string;
  json_url?: string;
  findings?: FindingItem[];
  findings_locked?: boolean;
  depth?: string;
  documents?: DocumentSummary[];
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
};

export type PlanInfo = {
  tier: string;
  display_name: string;
  monthly_job_quota: number;
  monthly_cost_limit_usd: number;
  max_files_per_job: number;
  max_concurrent_jobs: number;
  features: string[];
  max_depth: string;
  available_depths: string[];
};

export type CurrentUser = {
  id: string;
  email: string;
  display_name: string | null;
  plan: PlanInfo;
  jobs_used_this_month: number;
  spent_this_month_usd: number;

  is_admin: boolean;
};

export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type Job = {
  id: string;
  job_type: string;
  status: JobStatus;
  progress_percent: number;
  progress_message: string | null;
  error_code: string | null;
  error_message: string | null;
  document_count: number;
  depth: string;
  project_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;

  source: string | null;
};

export type JobList = {
  items: Job[];
  total: number;
};

export type DocumentSummary = {
  id: string;
  job_id: string;
  path: string;
  language: string;
  summary: string | null;
  symbol_count: number;
  finding_count: number;
  depth: string;
};

export type SymbolDoc = {
  name: string;
  kind: string;
  signature: string;
  language: string;
  line_start: number;
  line_end: number;
  summary: string;
  description: string;
  parameters: { name: string; type: string | null; description: string }[];
  return_type: string | null;
  return_description: string | null;
  raises: string[];
  side_effects: string[];
  complexity_estimate: number | null;
  parent: string | null;
};

export type FindingItem = {
  id: string;
  category: string;
  severity: string;
  title: string;
  detail: string;
  suggestion: string | null;
  symbol_name: string | null;
  line_start: number | null;
  line_end: number | null;
  confidence: number;
};

export type DocumentDetail = {
  id: string;
  job_id: string;
  path: string;
  language: string;
  summary: string | null;
  symbols: SymbolDoc[];
  findings: FindingItem[];
  findings_locked: boolean;
  depth: string;
};

export function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string) {
  clearLocalSession();

  localStorage.setItem(AUTH_TOKEN_KEY, token);
  window.dispatchEvent(new Event("legacydoc-auth-updated"));
}

export function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);

  clearLocalSession();

  window.dispatchEvent(new Event("legacydoc-auth-updated"));
}

function getAuthHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("content-type");

  const data = contentType?.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    if (response.status === 401) {
      clearAuthToken();
    }

    const message =
      typeof data === "string"
        ? data
        : data?.message || data?.detail || data?.error || "Erro na API";

    throw new Error(message);
  }

  return data as T;
}

async function get<T>(path: string): Promise<T> {
  return handleResponse<T>(
    await fetch(`${API_BASE_URL}${path}`, { headers: getAuthHeaders() })
  );
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return handleResponse<T>(
    await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify(body),
    })
  );
}

async function remove(path: string): Promise<void> {
  await handleResponse<unknown>(
    await fetch(`${API_BASE_URL}${path}`, { method: "DELETE", headers: getAuthHeaders() })
  );
}

export async function login(email: string, password: string) {
  return post<AuthResponse>("/v1/auth/login", { email, password });
}

export async function register(email: string, password: string) {
  return post<AuthResponse>("/v1/auth/register", { email, password });
}

export async function getCurrentUser() {
  return get<CurrentUser>("/v1/auth/me");
}

export async function requestPasswordReset(email: string) {
  return post<{ message: string }>("/v1/auth/password-reset/request", { email });
}

export async function confirmPasswordReset(token: string, newPassword: string) {
  return post<AuthResponse>("/v1/auth/password-reset/confirm", {
    token,
    new_password: newPassword,
  });
}

export async function createRepositoryJob(params: {
  repoUrl: string;
  branch?: string | null;
  paths?: string[];
  depth?: string | null;
  projectId?: string | null;
}) {
  return post<Job>("/v1/jobs", {
    job_type: "document_repository",
    repo_url: params.repoUrl,
    branch: params.branch || null,
    paths: params.paths ?? [],
    depth: params.depth || null,
    project_id: params.projectId || null,
    output_language: "pt-BR",
  });
}

export async function getJob(jobId: string) {
  return get<Job>(`/v1/jobs/${jobId}`);
}

export async function deleteJobRecord(jobId: string) {
  return remove(`/v1/jobs/${jobId}/record`);
}

export async function listJobs(limit = 50) {
  return get<JobList>(`/v1/jobs?limit=${limit}`);
}

export function clearLocalSession() {
  for (const chave of [
    "legacyDocResult",
    "legacyDocHistory",
    "repoUrl",
    "repoBranch",
    "repoDepth",
    "pendingJobId",
  ]) {
    localStorage.removeItem(chave);
  }
}

export async function listDocuments(jobId: string) {
  return get<DocumentSummary[]>(`/v1/documents?job_id=${jobId}`);
}

export async function getDocument(documentId: string) {
  return get<DocumentDetail>(`/v1/documents/${documentId}`);
}

export function exportPath(documentId: string, format: string) {
  return `/v1/documents/${documentId}/export?format=${format}`;
}

const TERMINAL: JobStatus[] = ["succeeded", "failed", "cancelled"];

export async function waitForJob(
  jobId: string,
  onProgress?: (job: Job) => void
): Promise<Job> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;

  for (;;) {
    const job = await getJob(jobId);

    onProgress?.(job);

    if (TERMINAL.includes(job.status)) {
      return job;
    }

    if (Date.now() > deadline) {
      throw new Error(
        "O processamento passou do tempo previsto. Consulte o job mais tarde."
      );
    }

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

function toFunctionItems(symbols: SymbolDoc[]): FunctionItem[] {
  return symbols.map((symbol) => ({
    name: symbol.parent ? `${symbol.parent}.${symbol.name}` : symbol.name,
    kind: symbol.kind,
    signature: symbol.signature,
    return_type: symbol.return_type ?? undefined,
    args: symbol.parameters.map((parameter) => ({
      name: parameter.name,
      type: parameter.type ?? "?",
    })),
    summary: symbol.summary,
    description: symbol.description,
    raises: symbol.raises,
  }));
}

export function documentToResult(
  detail: DocumentDetail,
  documents: DocumentSummary[]
): GenerateResponse {
  return {
    status: "success",
    file: detail.path,
    summary: detail.summary ?? undefined,
    documentation: toFunctionItems(detail.symbols),
    findings: detail.findings,
    findings_locked: detail.findings_locked,
    depth: detail.depth,
    documents,
    pdf_url: exportPath(detail.id, "pdf"),
    markdown_url: exportPath(detail.id, "markdown"),
    json_url: exportPath(detail.id, "json"),
  };
}

export async function followJob(
  jobId: string,
  onProgress?: (job: Job) => void
): Promise<GenerateResponse> {
  const finished = await waitForJob(jobId, onProgress);

  if (finished.status !== "succeeded") {
    throw new Error(
      finished.error_message ||
        "O processamento falhou. Tente novamente em alguns minutos."
    );
  }

  const documents = await listDocuments(finished.id);

  if (documents.length === 0) {
    throw new Error(
      "Nenhum arquivo suportado foi encontrado no material enviado."
    );
  }

  return documentToResult(await getDocument(documents[0].id), documents);
}

export async function runRepositoryJob(
  params: {
    repoUrl: string;
    branch?: string | null;
    paths?: string[];
    depth?: string | null;
  },
  onProgress?: (job: Job) => void
): Promise<GenerateResponse> {
  const created = await createRepositoryJob(params);

  return followJob(created.id, onProgress);
}

export type Language = {
  name: string;
  display_name: string;
  extensions: string[];
};

export async function getLanguages() {
  return get<Language[]>("/v1/meta/languages");
}

function parseJsonOrNull<T>(text: string): T | null {
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

export function createUploadJob(
  file: File,
  depth: string | null,
  onProgress?: (percent: number) => void
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("output_language", "pt-BR");

    if (depth) form.append("depth", depth);

    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE_URL}/v1/jobs/upload`);

    const token = getAuthToken();
    if (token) request.setRequestHeader("Authorization", `Bearer ${token}`);

    request.upload.onprogress = (evento) => {
      if (evento.lengthComputable) {
        onProgress?.(Math.round((evento.loaded / evento.total) * 100));
      }
    };

    request.onerror = () =>
      reject(new Error("Não foi possível enviar o arquivo. Verifique sua conexão."));

    request.onload = () => {
      const corpo = parseJsonOrNull<{ message?: string }>(request.responseText);

      if (request.status >= 200 && request.status < 300) {
        resolve(corpo as unknown as Job);
        return;
      }

      if (request.status === 401) clearAuthToken();

      reject(
        new Error(
          request.status === 413
            ? "O arquivo passa do limite de 50 MB."
            : corpo?.message || "Não foi possível enviar o arquivo."
        )
      );
    };

    request.send(form);
  });
}

export type AdminAccount = {
  id: string;
  email: string;
  display_name: string | null;
  plan_tier: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;

  jobs_this_month: number;
  spent_this_month_usd: number;
  cost_limit_usd: number;
  documents_total: number;
  last_job_at: string | null;
  locked_until: string | null;
};

export type AdminAccountList = {
  items: AdminAccount[];
  total: number;
};

export type AdminAction = {
  id: string;
  actor_email: string;
  target_email: string;
  action: string;
  value_before: string | null;
  value_after: string | null;
  reason: string;
  created_at: string;
};

export async function listAccounts(search = "", limit = 50) {
  const busca = search.trim() ? `&search=${encodeURIComponent(search.trim())}` : "";

  return get<AdminAccountList>(`/v1/admin/accounts?limit=${limit}${busca}`);
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  return handleResponse<T>(
    await fetch(`${API_BASE_URL}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify(body),
    })
  );
}

export async function changeAccountPlan(userId: string, plan: string, reason: string) {
  return patch<AdminAccount>(`/v1/admin/accounts/${userId}/plan`, { plan, reason });
}

export async function changeAccountStatus(
  userId: string,
  isActive: boolean,
  reason: string
) {
  return patch<AdminAccount>(`/v1/admin/accounts/${userId}/status`, {
    is_active: isActive,
    reason,
  });
}

export async function listAudit(limit = 100) {
  return get<AdminAction[]>(`/v1/admin/audit?limit=${limit}`);
}

export function resolveBackendUrl(path?: string | null) {
  if (!path) return null;

  return path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
}

export async function downloadArtifact(path?: string | null, fallbackName = "documento") {
  const url = resolveBackendUrl(path);

  if (!url) {
    throw new Error("Arquivo nao disponivel.");
  }

  const response = await fetch(url, { headers: getAuthHeaders() });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("Sessao expirada. Entre novamente para baixar o arquivo.");
    }
    throw new Error("Nao foi possivel baixar o arquivo.");
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = objectUrl;
  link.download = fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(objectUrl);
}
