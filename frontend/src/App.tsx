import { useEffect, useRef, useState } from "react";
import {
  fetchHealth,
  fetchObjectClasses,
  fetchVideos,
  postInvestigate,
  resolveMediaUrl,
} from "./api";
import type { Event, InvestigateResponse, TimelineEntry, VideoInfo } from "./types";
import "./App.css";

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function VerificationBadge({ status }: { status: Event["verification"] }) {
  const labels: Record<Event["verification"], string> = {
    verified_model: "Model verified",
    retrieval_only: "Retrieval",
    unverified_mock: "MOCK",
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
        <button type="button" onClick={() => onJump(evt)}>Jump to moment</button>
        <button type="button" onClick={() => onFollowUp(evt)}>Follow up</button>
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
          type="button"
          className="timeline__marker"
          style={{ left: pct(evt.start_sec), width: pct(Math.max(0.5, evt.end_sec - evt.start_sec)) }}
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

function InvestigationTimeline({
  entries,
  events,
  onJump,
}: {
  entries: TimelineEntry[];
  events: Event[];
  onJump: (evt: Event) => void;
}) {
  if (!entries.length) return null;
  const byId = new Map(events.map((e) => [e.event_id, e]));

  return (
    <section className="section section--inv-timeline" aria-label="Investigation timeline">
      <h2 className="section-title">Investigation timeline</h2>
      <ol className="inv-timeline">
        {entries.map((turn, idx) => (
          <li key={turn.turn_id} className="inv-timeline__item">
            <div className="inv-timeline__turn">Turn {idx + 1}</div>
            <div className="inv-timeline__query">{turn.query}</div>
            {turn.follow_up_of && (
              <div className="inv-timeline__meta">Follow-up of prior evidence</div>
            )}
            {turn.answer_preview && (
              <p className="inv-timeline__preview">{turn.answer_preview}</p>
            )}
            <div className="inv-timeline__events">
              {turn.event_ids.map((id) => {
                const evt = byId.get(id);
                if (!evt) return null;
                return (
                  <button
                    key={id}
                    type="button"
                    className="inv-timeline__chip"
                    onClick={() => onJump(evt)}
                  >
                    {fmtTime(evt.start_sec)}–{fmtTime(evt.end_sec)}
                  </button>
                );
              })}
            </div>
          </li>
        ))}
      </ol>
    </section>
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
  const [providerMode, setProviderMode] = useState<string>("unknown");
  const [objectClasses, setObjectClasses] = useState<string[]>([]);
  const [objectFilter, setObjectFilter] = useState<string>("");
  const [allEvents, setAllEvents] = useState<Event[]>([]);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    fetchHealth()
      .then((h) => setProviderMode(h.provider_mode))
      .catch(() => setProviderMode("unreachable"));

    fetchVideos()
      .then((vs) => {
        setVideos(vs);
        if (vs.length > 0) setSelectedVideo(vs[0]);
      })
      .catch((err) => setError(`Failed to load video list: ${err.message}`));

    fetchObjectClasses()
      .then(setObjectClasses)
      .catch(() => setObjectClasses([]));
  }, []);

  const videoSrc = selectedVideo?.video_url
    ? resolveMediaUrl(selectedVideo.video_url)
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
        object_classes: objectFilter ? [objectFilter] : null,
      });
      setResult(resp);
      setProviderMode(resp.mode);
      setAllEvents((prev) => {
        const map = new Map(prev.map((e) => [e.event_id, e]));
        for (const e of resp.events) map.set(e.event_id, e);
        return Array.from(map.values());
      });
      setSelectedEvent(null);
      if (resp.events[0]) {
        seekTo(resp.events[0].start_sec);
      }
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

  const isMock = providerMode === "mock";

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">SceneTrace</h1>
        <span className="app-subtitle">Evidence-grounded video investigation · Team 34</span>
        <span
          className={`mode-badge mode-badge--${providerMode}`}
          aria-label={`Provider mode ${providerMode}`}
        >
          {isMock
            ? "DEMO MODE — fixture data, not live inference"
            : `LIVE · ${providerMode}`}
        </span>
      </header>

      <main className="app-main">
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
              setAllEvents([]);
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
                onError={() => setVideoError("Could not load video stream.")}
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
                placeholder="e.g. forklift near a person in an aisle"
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
            <div className="filter-row">
              <label htmlFor="object-filter" className="field-label">
                Object filter (YOLO metadata)
              </label>
              <select
                id="object-filter"
                value={objectFilter}
                onChange={(e) => setObjectFilter(e.target.value)}
                disabled={loading}
              >
                <option value="">Any detected object</option>
                {objectClasses.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </form>
          {loading && (
            <div className="progress" role="status" aria-live="polite">
              <span className="spinner" aria-hidden="true" />
              Running investigation…
            </div>
          )}
        </section>

        {error && (
          <div className="error-banner" role="alert">
            <strong>Error:</strong> {error}
          </div>
        )}

        {result && (
          <section className="section section--results" aria-label="Investigation results">
            <div className="results-header">
              <p className="results-answer">{result.answer}</p>
              {result.warnings.map((w, i) => (
                <p key={i} className="results-warning">{w}</p>
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

            <InvestigationTimeline
              entries={result.timeline ?? []}
              events={allEvents}
              onJump={handleJump}
            />

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
