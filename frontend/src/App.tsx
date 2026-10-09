import { useEffect, useRef, useState } from "react";
import { fetchVideos, postInvestigate } from "./api";
import type { Event, InvestigateResponse, VideoInfo } from "./types";
import "./App.css";

const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function VerificationBadge({ status }: { status: Event["verification"] }) {
  const labels: Record<Event["verification"], string> = {
    verified_model: "✓ Model verified",
    retrieval_only: "⚡ Retrieval",
    unverified_mock: "⚙ MOCK",
  };
  return (
    <span className={`badge badge-${status}`}>{labels[status]}</span>
  );
}

function EventCard({
  evt,
  index,
  selected,
  onJump,
  onFollowUp,
}: {
  evt: Event;
  index: number;
  selected: boolean;
  onJump: (evt: Event) => void;
  onFollowUp: (evt: Event) => void;
}) {
  return (
    <article className={`event-card${selected ? " event-card--selected" : ""}`}>
      <header className="event-card__header">
        <span className="event-card__index">#{index + 1}</span>
        <button
          className="event-card__timestamp"
          onClick={() => onJump(evt)}
          aria-label={`Jump to ${fmtTime(evt.start_sec)}`}
        >
          {fmtTime(evt.start_sec)} – {fmtTime(evt.end_sec)}
        </button>
        <VerificationBadge status={evt.verification} />
        {evt.labels.length > 0 && (
          <span className="event-card__labels">
            {evt.labels.map((l) => (
              <span key={l} className="label-chip">{l}</span>
            ))}
          </span>
        )}
      </header>
      <p className="event-card__explanation">{evt.explanation}</p>
      {evt.evidence.length > 0 && (
        <details className="event-card__evidence">
          <summary>Evidence ({evt.evidence.length})</summary>
          <ul>
            {evt.evidence.map((e, i) => (
              <li key={i}>
                <span className="evidence-kind">{e.kind}</span>: {e.detail}
              </li>
            ))}
          </ul>
        </details>
      )}
      <footer className="event-card__actions">
        <button onClick={() => onJump(evt)}>Jump to moment</button>
        <button onClick={() => onFollowUp(evt)}>Follow up</button>
      </footer>
    </article>
  );
}

function Timeline({
  duration,
  events,
  currentTime,
  onSeek,
}: {
  duration: number;
  events: Event[];
  currentTime: number;
  onSeek: (t: number) => void;
}) {
  if (duration <= 0) return null;
  const pct = (sec: number) => `${((sec / duration) * 100).toFixed(2)}%`;

  return (
    <div
      className="timeline"
      role="slider"
      aria-label="Video timeline"
      aria-valuenow={Math.round(currentTime)}
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      onClick={(e) => {
        const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
        const ratio = (e.clientX - rect.left) / rect.width;
        onSeek(Math.max(0, Math.min(duration, ratio * duration)));
      }}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") onSeek(Math.max(0, currentTime - 5));
        if (e.key === "ArrowRight") onSeek(Math.min(duration, currentTime + 5));
      }}
    >
      <div className="timeline__track" />
      <div
        className="timeline__playhead"
        style={{ left: pct(currentTime) }}
        aria-hidden="true"
      />
      {events.map((evt) => (
        <button
          key={evt.event_id}
          className="timeline__marker"
          style={{ left: pct(evt.start_sec), width: pct(evt.end_sec - evt.start_sec) }}
          title={`${fmtTime(evt.start_sec)} – ${fmtTime(evt.end_sec)}: ${evt.explanation}`}
          onClick={(e) => {
            e.stopPropagation();
            onSeek(evt.start_sec);
          }}
          aria-label={`Event at ${fmtTime(evt.start_sec)}`}
        />
      ))}
    </div>
  );
}

export default function App() {
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<VideoInfo | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<InvestigateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [showTrace, setShowTrace] = useState(false);
  const [videoError, setVideoError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    fetchVideos()
      .then((vs) => {
        setVideos(vs);
        if (vs.length > 0) setSelectedVideo(vs[0]);
      })
      .catch((err) => setError(`Failed to load video list: ${err.message}`));
  }, []);

  const videoSrc = selectedVideo?.video_url
    ? selectedVideo.video_url.startsWith("http")
      ? selectedVideo.video_url
      : `${API_BASE}${selectedVideo.video_url}`
    : null;

  function seekTo(sec: number) {
    const vid = videoRef.current;
    if (!vid) return;
    if (vid.readyState >= 1) {
      vid.currentTime = sec;
    } else {
      vid.addEventListener("loadedmetadata", () => { vid.currentTime = sec; }, { once: true });
    }
  }

  function handleJump(evt: Event) {
    setSelectedEvent(evt);
    seekTo(evt.start_sec);
  }

  async function handleFollowUp(evt: Event) {
    if (!selectedVideo || !result) return;
    const q = `What happened just before and after this moment? (${fmtTime(evt.start_sec)})`;
    setQuery(q);
    await runInvestigation(q, evt);
  }

  async function runInvestigation(q: string, followUpEvt?: Event) {
    if (!selectedVideo || !q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await postInvestigate({
        video_id: selectedVideo.id,
        query: q,
        selected_event_id: followUpEvt?.event_id ?? null,
        session_id: result?.session_id ?? null,
      });
      setResult(resp);
      setSelectedEvent(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    runInvestigation(query);
  }

  const isMock = result?.mode === "mock" || !result;

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">SceneTrace</h1>
        <span className="app-subtitle">Evidence-grounded video investigation</span>
        {isMock && (
          <span className="mock-badge" aria-label="Running in demo/mock mode">
            ⚙ DEMO MODE — fixture data, not live inference
          </span>
        )}
      </header>

      <main className="app-main">
        {/* Video selector */}
        <section className="section section--selector" aria-label="Video selection">
          <label htmlFor="video-select" className="field-label">Footage</label>
          <select
            id="video-select"
            value={selectedVideo?.id ?? ""}
            onChange={(e) => {
              const v = videos.find((x) => x.id === e.target.value) ?? null;
              setSelectedVideo(v);
              setResult(null);
              setSelectedEvent(null);
              setVideoError(null);
            }}
          >
            {videos.map((v) => (
              <option key={v.id} value={v.id}>
                {v.title}
                {v.duration_sec ? ` (${fmtTime(v.duration_sec)})` : ""}
              </option>
            ))}
          </select>
          {selectedVideo && (
            <span className="source-badge">source: {selectedVideo.source}</span>
          )}
        </section>

        {/* Video player */}
        <section className="section section--player" aria-label="Video player">
          {videoSrc ? (
            <>
              <video
                ref={videoRef}
                className="video-player"
                src={videoSrc}
                controls
                preload="metadata"
                onTimeUpdate={(e) => setCurrentTime((e.currentTarget as HTMLVideoElement).currentTime)}
                onLoadedMetadata={(e) => setVideoDuration((e.currentTarget as HTMLVideoElement).duration)}
                onError={() => setVideoError("Could not load video. Make sure the backend is running.")}
                aria-label={selectedVideo?.title ?? "Video"}
              />
              {videoError && <p className="error-text">{videoError}</p>}
              <Timeline
                duration={videoDuration}
                events={result?.events ?? []}
                currentTime={currentTime}
                onSeek={seekTo}
              />
            </>
          ) : (
            <div className="no-video">Select a video to begin.</div>
          )}
        </section>

        {/* Query form */}
        <section className="section section--query" aria-label="Investigation query">
          <form onSubmit={handleSubmit} className="query-form">
            <label htmlFor="query-input" className="field-label">
              What do you want to investigate?
            </label>
            <div className="query-row">
              <input
                id="query-input"
                type="text"
                className="query-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. Find when someone sets down a box"
                maxLength={500}
                disabled={loading}
                autoFocus
              />
              <button
                type="submit"
                className="btn-primary"
                disabled={loading || !query.trim() || !selectedVideo}
                aria-busy={loading}
              >
                {loading ? "Searching…" : "Investigate"}
              </button>
            </div>
          </form>
          {loading && (
            <div className="progress" role="status" aria-live="polite">
              <span className="spinner" aria-hidden="true" />
              Running investigation…
            </div>
          )}
        </section>

        {/* Errors */}
        {error && (
          <div className="error-banner" role="alert">
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Results */}
        {result && (
          <section className="section section--results" aria-label="Investigation results">
            <div className="results-header">
              <p className="results-answer">{result.answer}</p>
              {result.warnings.map((w, i) => (
                <p key={i} className="results-warning">⚠ {w}</p>
              ))}
            </div>

            {result.events.length === 0 && (
              <p className="no-results">No supported evidence found.</p>
            )}

            <div className="events-list">
              {result.events.map((evt, i) => (
                <EventCard
                  key={evt.event_id}
                  evt={evt}
                  index={i}
                  selected={selectedEvent?.event_id === evt.event_id}
                  onJump={handleJump}
                  onFollowUp={handleFollowUp}
                />
              ))}
            </div>

            {result.tool_trace.length > 0 && (
              <details
                className="trace-panel"
                open={showTrace}
                onToggle={(e) => setShowTrace((e.currentTarget as HTMLDetailsElement).open)}
              >
                <summary>Tool trace ({result.tool_trace.length} steps)</summary>
                <table className="trace-table">
                  <thead>
                    <tr>
                      <th>Tool</th>
                      <th>Status</th>
                      <th>ms</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.tool_trace.map((t, i) => (
                      <tr key={i}>
                        <td>{t.tool}</td>
                        <td>{t.status}</td>
                        <td>{t.duration_ms}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
