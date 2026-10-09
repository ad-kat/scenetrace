import type {
  InvestigateRequest,
  InvestigateResponse,
  VideoInfo,
} from "./types";

const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = body?.error?.message ?? body?.detail ?? message;
    } catch {
      // ignore parse failure
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export async function fetchVideos(): Promise<VideoInfo[]> {
  const res = await fetch(`${API_BASE}/api/videos`);
  return handleResponse<VideoInfo[]>(res);
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
