import type {
  AnalyzeResponse,
  BenchmarkRun,
  DatasetDetails,
  DatasetItem,
  EvaluationResponse,
  ReportItem,
  SessionItem,
  SuggestedQuestionsResponse,
  TraceItem,
  UploadResponse,
} from "./types";

const API_BASE_URL = "/api/noha";

export function csrfToken(): string {
  if (typeof document === "undefined") return "";
  return (
    document.cookie
      .split("; ")
      .find((value) => value.startsWith("noha-csrf="))
      ?.split("=")[1] ?? ""
  );
}

export type ApiErrorKind = "network" | "http" | "malformed" | "aborted";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;

  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isUploadResponse(value: unknown): value is UploadResponse {
  if (!isRecord(value) || !isRecord(value.validation)) return false;
  const v = value.validation;
  return (
    typeof value.dataset_id === "string" &&
    typeof value.filename === "string" &&
    typeof value.size_bytes === "number" &&
    typeof v.rows === "number" &&
    typeof v.columns === "number" &&
    Array.isArray(v.column_names)
  );
}

function isAnalyzeResponse(value: unknown): value is AnalyzeResponse {
  if (!isRecord(value)) return false;
  return (
    typeof value.session_id === "string" &&
    typeof value.status === "string" &&
    typeof value.final_report === "string" &&
    [
      "analysis_plan",
      "tool_calls",
      "findings",
      "visualizations",
      "evidence",
      "validation_results",
      "errors",
    ].every((key) => Array.isArray(value[key]))
  );
}

/** Formats HTTP errors with clear analytical and security guidance. */
export function formatHttpError(status: number, fallback?: string): string {
  const isGeneric =
    !fallback ||
    fallback.includes("HTTP") ||
    fallback.startsWith("Request failed") ||
    fallback.toLowerCase().includes("fallback");

  switch (status) {
    case 401:
      return "Authentication required. Please sign in to access your datasets and analyses.";
    case 403:
      return "Access denied or session invalid. Please refresh the page or sign in again.";
    case 404:
      return !isGeneric && fallback
        ? fallback
        : "The requested dataset, analysis session, or chart was not found or does not belong to your account.";
    case 413:
      return "The dataset file or query exceeds the maximum allowed size (100 MB limit).";
    case 422:
      return !isGeneric && fallback
        ? fallback
        : "Validation failed: please check your query and dataset format.";
    case 429:
      return "Too many requests. Please wait a moment before trying again.";
    case 500:
      return !isGeneric && fallback
        ? fallback
        : "Analysis execution failed on the server. Please check your data format or try another question.";
    case 502:
      return "Analysis service is unreachable. Please verify that the backend server is running.";
    case 503:
      return !isGeneric && fallback
        ? fallback
        : "The analysis engine is currently busy with other analyses. Please retry shortly.";
    default:
      return fallback || `Request failed with status ${status}.`;
  }
}

/** FastAPI errors arrive as {"detail": string | [{loc, msg}]}. */
export function detailMessage(body: unknown, fallback: string, status?: number): string {
  if (isRecord(body)) {
    const detail = body.detail;
    if (typeof detail === "string" && detail.trim() !== "") {
      return detail;
    }
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((item: unknown) => {
          if (isRecord(item) && typeof item.msg === "string") {
            const loc = Array.isArray(item.loc)
              ? item.loc.filter((x) => x !== "body").join(".")
              : "";
            return loc ? `${loc}: ${item.msg}` : item.msg;
          }
          return JSON.stringify(item);
        })
        .filter(Boolean);
      if (msgs.length > 0) return msgs.join("; ");
    }
  }
  if (status) {
    return formatHttpError(status, fallback);
  }
  return fallback;
}

const unreachable = () => "Cannot reach the analysis service. Please verify that the server is running.";

export interface UploadProgress {
  loaded: number;
  total: number;
}

/** POST /upload as multipart `file`. XHR is used because fetch cannot report upload progress. */
export function uploadDataset(
  file: File,
  onProgress: (progress: UploadProgress) => void,
  signal?: AbortSignal,
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/upload`);
    const token = csrfToken();
    if (token) {
      xhr.setRequestHeader("X-CSRF-Token", token);
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress({ loaded: event.loaded, total: event.total });
    };

    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (isUploadResponse(body)) resolve(body);
        else reject(new ApiError("malformed", "Upload succeeded but the response was not in the expected format."));
      } else {
        const message = detailMessage(body, `Upload failed (HTTP ${xhr.status}).`, xhr.status);
        reject(new ApiError("http", message, xhr.status));
      }
    };

    xhr.onerror = () => reject(new ApiError("network", unreachable()));
    xhr.ontimeout = () => reject(new ApiError("network", "The upload timed out."));
    xhr.onabort = () => reject(new ApiError("aborted", "Upload cancelled."));
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });

    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

/** POST /analyze. `datasetId` is forwarded exactly as /upload returned it. */
export async function analyze(
  userQuery: string,
  datasetId: string,
  signal?: AbortSignal,
): Promise<AnalyzeResponse> {
  let response: Response;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = csrfToken();
  if (token) {
    headers["X-CSRF-Token"] = token;
  }

  try {
    response = await fetch(`${API_BASE_URL}/analyze`, {
      method: "POST",
      headers,
      body: JSON.stringify({ user_query: userQuery, dataset_id: datasetId }),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("aborted", "Analysis cancelled.");
    }
    throw new ApiError("network", unreachable());
  }

  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const message = detailMessage(body, `Analysis failed (HTTP ${response.status}).`, response.status);
    throw new ApiError("http", message, response.status);
  }
  if (!isAnalyzeResponse(body)) {
    throw new ApiError("malformed", "The backend returned an analysis in an unexpected format.");
  }
  return body;
}

/** GET /analysis/{session_id}. Retrieves a previously executed analysis. */
export async function getAnalysis(
  sessionId: string,
  signal?: AbortSignal,
): Promise<AnalyzeResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/analysis/${encodeURIComponent(sessionId)}`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("aborted", "Request cancelled.");
    }
    throw new ApiError("network", unreachable());
  }

  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const message = detailMessage(
      body,
      `Failed to retrieve session (HTTP ${response.status}).`,
      response.status,
    );
    throw new ApiError("http", message, response.status);
  }
  if (!isAnalyzeResponse(body)) {
    throw new ApiError("malformed", "The backend returned an analysis in an unexpected format.");
  }
  return body;
}

/** Alias for getAnalysis. */
export const getSession = getAnalysis;

/** GET /health. Resolves false on any failure. */
export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch("/api/health", { signal, cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------
// Workspace Module API Clients
// ---------------------------------------------------------

/** GET /datasets. Lists datasets owned by the current user. */
export async function listDatasets(signal?: AbortSignal): Promise<DatasetItem[]> {
  const response = await fetch(`${API_BASE_URL}/datasets`, { signal, cache: "no-store" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError("http", detailMessage(body, `Failed to list datasets (HTTP ${response.status}).`, response.status), response.status);
  }
  return Array.isArray(body) ? body : [];
}

/** GET /datasets/{dataset_id}. Retrieves detailed profile and statistics. */
export async function getDatasetDetails(datasetId: string, signal?: AbortSignal): Promise<DatasetDetails> {
  const response = await fetch(`${API_BASE_URL}/datasets/${encodeURIComponent(datasetId)}`, { signal, cache: "no-store" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError("http", detailMessage(body, `Failed to load dataset details (HTTP ${response.status}).`, response.status), response.status);
  }
  return body as DatasetDetails;
}

/** DELETE /datasets/{dataset_id}. Deletes dataset with ownership validation. */
export async function deleteDataset(datasetId: string, signal?: AbortSignal): Promise<void> {
  const headers: Record<string, string> = {};
  const token = csrfToken();
  if (token) headers["X-CSRF-Token"] = token;
  const response = await fetch(`${API_BASE_URL}/datasets/${encodeURIComponent(datasetId)}`, {
    method: "DELETE",
    headers,
    signal,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError("http", detailMessage(body, `Failed to delete dataset (HTTP ${response.status}).`, response.status), response.status);
  }
}

/** POST /datasets/{dataset_id}/replace. Replaces dataset file. */
export async function replaceDataset(
  datasetId: string,
  file: File,
  signal?: AbortSignal,
): Promise<UploadResponse> {
  const headers: Record<string, string> = {};
  const token = csrfToken();
  if (token) headers["X-CSRF-Token"] = token;

  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`${API_BASE_URL}/datasets/${encodeURIComponent(datasetId)}/replace`, {
    method: "POST",
    headers,
    body: form,
    signal,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError("http", detailMessage(body, `Failed to replace dataset (HTTP ${response.status}).`, response.status), response.status);
  }
  return body as UploadResponse;
}

/** GET /sessions. Lists analysis sessions. */
export async function listSessions(signal?: AbortSignal): Promise<SessionItem[]> {
  const response = await fetch(`${API_BASE_URL}/sessions`, { signal, cache: "no-store" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError("http", detailMessage(body, `Failed to list sessions (HTTP ${response.status}).`, response.status), response.status);
  }
  return Array.isArray(body) ? body : [];
}

/** GET /reports. Lists generated analysis reports. */
export async function listReports(signal?: AbortSignal): Promise<ReportItem[]> {
  const response = await fetch(`${API_BASE_URL}/reports`, { signal, cache: "no-store" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError("http", detailMessage(body, `Failed to list reports (HTTP ${response.status}).`, response.status), response.status);
  }
  return Array.isArray(body) ? body : [];
}

/** GET /traces. Lists execution traces. */
export async function listTraces(signal?: AbortSignal): Promise<TraceItem[]> {
  const response = await fetch(`${API_BASE_URL}/traces`, { signal, cache: "no-store" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError("http", detailMessage(body, `Failed to list execution traces (HTTP ${response.status}).`, response.status), response.status);
  }
  return Array.isArray(body) ? body : [];
}

/** GET /evaluations. Lists pipeline validations and benchmark runs. */
export async function getEvaluations(signal?: AbortSignal): Promise<EvaluationResponse> {
  const response = await fetch(`${API_BASE_URL}/evaluations`, { signal, cache: "no-store" });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError("http", detailMessage(body, `Failed to load evaluations (HTTP ${response.status}).`, response.status), response.status);
  }
  return body as EvaluationResponse;
}

/** POST /evaluations/run. Executes genuine deterministic benchmark evaluation. */
export async function runBenchmarkEvaluation(
  benchmarkId: string = "stress_sales_500k",
  signal?: AbortSignal,
): Promise<BenchmarkRun> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = csrfToken();
  if (token) headers["X-CSRF-Token"] = token;

  const response = await fetch(`${API_BASE_URL}/evaluations/run`, {
    method: "POST",
    headers,
    body: JSON.stringify({ benchmark_id: benchmarkId }),
    signal,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError("http", detailMessage(body, `Failed to run benchmark evaluation (HTTP ${response.status}).`, response.status), response.status);
  }
  return body as BenchmarkRun;
}

/** GET /datasets/{dataset_id}/suggested-questions. Dynamically generates schema-aware questions. */
export async function getSuggestedQuestions(
  datasetId: string,
  offset: number = 0,
  signal?: AbortSignal,
): Promise<SuggestedQuestionsResponse> {
  const query = offset > 0 ? `?offset=${offset}` : "";
  const response = await fetch(`${API_BASE_URL}/datasets/${datasetId}/suggested-questions${query}`, {
    signal,
    cache: "no-store",
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      "http",
      detailMessage(body, `Failed to fetch suggested questions (HTTP ${response.status}).`, response.status),
      response.status,
    );
  }
  return body as SuggestedQuestionsResponse;
}
