import type {
  ArchiveSearchResponse,
  IncidentReport,
  InvestigateRequest,
  InvestigateResponse,
  VideoInfo,
} from "./types";

/** Empty string = same-origin (K8s /app). Dev default hits local API. */
const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  (import.meta.env.DEV ? "http://localhost:8000" : "");

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = body?.error?.message ?? body?.detail ?? message;
      if (Array.isArray(body?.detail)) {
        message = body.detail.map((d: { msg?: string }) => d.msg ?? "").join("; ") || message;
      }
    } catch {
      // ignore parse failure
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export function resolveMediaUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE}${path}`;
}

export async function fetchVideos(): Promise<VideoInfo[]> {
  const res = await fetch(`${API_BASE}/api/videos`);
  return handleResponse<VideoInfo[]>(res);
}

export async function fetchObjectClasses(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/api/metadata/object-classes`);
  if (!res.ok) return [];
  const data = await res.json();
  return Array.isArray(data?.values) ? data.values : [];
}

export async function postInvestigate(
  req: InvestigateRequest
): Promise<InvestigateResponse> {
  const res = await fetch(`${API_BASE}/api/investigate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return handleResponse<InvestigateResponse>(res);
}

export async function fetchHealth(): Promise<{
  status: string;
  provider_mode: string;
  vss_configured?: boolean;
}> {
  const res = await fetch(`${API_BASE}/health`);
  return handleResponse(res);
}

export async function postArchiveSearch(
  query: string,
  top_k = 10,
  object_classes?: string[] | null,
): Promise<ArchiveSearchResponse> {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k, object_classes: object_classes ?? null }),
  });
  return handleResponse<ArchiveSearchResponse>(res);
}

export async function postReport(
  session_id: string,
  title?: string,
): Promise<IncidentReport> {
  const res = await fetch(`${API_BASE}/api/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id, title }),
  });
  return handleResponse<IncidentReport>(res);
}
