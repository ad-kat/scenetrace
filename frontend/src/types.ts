export interface VideoInfo {
  id: string;
  title: string;
  duration_sec: number | null;
  video_url: string;
  source: string;
  location?: string | null;
  camera_id?: string | null;
  original_video?: string | null;
}

export interface EvidenceItem {
  kind: "retrieval" | "detection" | "reasoning" | string;
  detail: string;
  start_sec?: number | null;
  end_sec?: number | null;
}

export interface Event {
  event_id: string;
  video_id: string;
  start_sec: number;
  end_sec: number;
  explanation: string;
  evidence: EvidenceItem[];
  labels: string[];
  score: number | null;
  verification: "verified_model" | "retrieval_only" | "unverified_mock";
  playback_source?: string | null;
  original_video?: string | null;
}

export interface ToolTraceEntry {
  tool: string;
  status: string;
  duration_ms: number;
  detail?: string | null;
}

export interface TimelineEntry {
  turn_id: string;
  query: string;
  event_ids: string[];
  answer_preview: string;
  follow_up_of?: string | null;
}

export interface InvestigateResponse {
  session_id: string;
  mode: "mock" | "live" | "hybrid";
  answer: string;
  events: Event[];
  tool_trace: ToolTraceEntry[];
  warnings: string[];
  timeline: TimelineEntry[];
}

export interface InvestigateRequest {
  video_id: string;
  query: string;
  selected_event_id?: string | null;
  session_id?: string | null;
  object_classes?: string[] | null;
  metadata_filters?: Record<string, string> | null;
}
