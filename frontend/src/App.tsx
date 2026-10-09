import { useEffect, useRef, useState } from "react";
import {
  fetchHealth,
  fetchObjectClasses,
  fetchVideos,
  postArchiveSearch,
  postInvestigate,
  postReport,
  resolveMediaUrl,
} from "./api";
import type {
  ArchiveSearchResult,
  Event,
  IncidentReport,
  InvestigateResponse,
  TimelineEntry,
  VideoInfo,
} from "./types";
import "./App.css";

// ── helpers ──────────────────────────────────────────────────────────────────

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const EXAMPLE_QUERIES = [
  "forklift approaching a pedestrian",
  "worker standing in vehicle path",
  "vehicle and pedestrian at intersection",
  "person near moving industrial equipment",
];

// ── small components ─────────────────────────────────────────────────────────

function VerificationBadge({ status }: { status: Event["verification"] }) {
  const labels: Record<Event["verification"], string> = {
    verified_model: "Model-verified",
    retrieval_only: "Retrieval",
    unverified_mock: "MOCK",
  };
  return <span className={`badge badge-${status}`}>{labels[status]}</span>;
}

function SearchResultCard({
  result,
  selected,
  onSelect,
}: {
  result: ArchiveSearchResult;
  selected: boolean;
  onSelect: (r: ArchiveSearchResult) => void;
}) {
  return (
    <article
      className={`search-card${selected ? " search-card--selected" : ""}`}
      onClick={() => onSelect(result)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onSelect(result)}
      aria-pressed={selected}
    >
      <header className="search-card__header">
        <span className="search-card__time">
          {fmtTime(result.start_sec)}–{fmtTime(result.end_sec)}
        </span>
        {result.score !== null && (
          <span className="search-card__score">
            {(result.score * 100).toFixed(0)}% match
          </span>
        )}
        {result.source === "mock" && (
          <span className="badge badge-unverified_mock">MOCK</span>
        )}
      </header>
      <p className="search-card__title">{result.title}</p>
      {(result.location || result.camera_id) && (
        <div className="search-card__meta">
          {result.location && <span className="meta-chip">📍 {result.location}</span>}
          {result.camera_id && <span className="meta-chip">🎥 {result.camera_id}</span>}
        </div>
      )}
      {result.caption && (
        <p className="search-card__caption">{result.caption}</p>
      )}
    </article>
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
      {(evt.location || evt.camera_id) && (
        <div className="event-card__meta">
          {evt.location && <span className="meta-chip">📍 {evt.location}</span>}
          {evt.camera_id && <span className="meta-chip">🎥 {evt.camera_id}</span>}
        </div>
      )}
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
        <button type="button" onClick={() => onFollowUp(evt)}>Investigate surrounding footage</button>
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
      <div className="timeline__playhead" style={{ left: pct(currentTime) }} aria-hidden="true" />
      {events.map((evt) => (
        <button
          key={evt.event_id}
          type="button"
          className="timeline__marker"
          style={{ left: pct(evt.start_sec), width: pct(Math.max(0.5, evt.end_sec - evt.start_sec)) }}
          title={`${fmtTime(evt.start_sec)} – ${fmtTime(evt.end_sec)}: ${evt.explanation}`}
          onClick={(e) => { e.stopPropagation(); onSeek(evt.start_sec); }}
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
                  <button key={id} type="button" className="inv-timeline__chip" onClick={() => onJump(evt)}>
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

function ReportPanel({ report }: { report: IncidentReport }) {
  return (
    <section className="section section--report" aria-label="Safety investigation report">
      <h2 className="section-title">{report.title}</h2>
      <p className="report-summary">{report.summary}</p>
      {report.sections.map((sec, i) => (
        <details key={i} className="report-section" open={i < 3}>
          <summary className="report-section__heading">{sec.heading}</summary>
          <pre className="report-section__content">{sec.content}</pre>
        </details>
      ))}
      <p className="report-meta">Report ID: {report.report_id} · {report.generated_at}</p>
    </section>
  );
}

// ── main app ─────────────────────────────────────────────────────────────────

export default function App() {
  // Archive search
  const [searchQuery, setSearchQuery] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<ArchiveSearchResult[] | null>(null);
  const [searchWarnings, setSearchWarnings] = useState<string[]>([]);
  const [selectedResult, setSelectedResult] = useState<ArchiveSearchResult | null>(null);

  // Video player
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<VideoInfo | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [videoError, setVideoError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Investigation
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<InvestigateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);
  const [showTrace, setShowTrace] = useState(false);
  const [allEvents, setAllEvents] = useState<Event[]>([]);
  const [objectClasses, setObjectClasses] = useState<string[]>([]);
  const [objectFilter, setObjectFilter] = useState<string>("");

  // Report
  const [report, setReport] = useState<IncidentReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  // Provider mode
  const [providerMode, setProviderMode] = useState<string>("unknown");

  useEffect(() => {
    fetchHealth()
      .then((h) => setProviderMode(h.provider_mode))
      .catch(() => setProviderMode("unreachable"));
    fetchVideos()
      .then((vs) => { setVideos(vs); if (vs.length > 0) setSelectedVideo(vs[0]); })
      .catch((err) => setError(`Failed to load video list: ${err.message}`));
    fetchObjectClasses()
      .then(setObjectClasses)
      .catch(() => setObjectClasses([]));
  }, []);

  const videoSrc = selectedVideo?.video_url ? resolveMediaUrl(selectedVideo.video_url) : null;

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
      setReport(null);
      if (resp.events[0]) seekTo(resp.events[0].start_sec);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleArchiveSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    setSearchResults(null);
    setSearchWarnings([]);
    setError(null);
    setResult(null);
    setReport(null);
    try {
      const resp = await postArchiveSearch(searchQuery, 10);
      setSearchResults(resp.results);
      setSearchWarnings(resp.warnings);
      setProviderMode(resp.mode);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSearchLoading(false);
    }
  }

  function handleSelectResult(r: ArchiveSearchResult) {
    setSelectedResult(r);
    // Find or fall back to the first video in the list matching the result's video_id
    const match = videos.find((v) => v.id === r.video_id) ?? (videos.length > 0 ? videos[0] : null);
    if (match) {
      if (selectedVideo?.id !== match.id) {
        setSelectedVideo(match);
        setResult(null);
        setAllEvents([]);
        setVideoError(null);
      }
      // Seek after video load
      setTimeout(() => seekTo(r.start_sec), 100);
    }
    // Pre-populate investigation query from the search query
    setQuery(searchQuery || `Investigate potential near-miss at ${fmtTime(r.start_sec)}`);
    setReport(null);
  }

  async function handleGenerateReport() {
    if (!result?.session_id) return;
    setReportLoading(true);
    setReport(null);
    try {
      const r = await postReport(result.session_id, "SceneTrace Safety Investigation Report");
      setReport(r);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setReportLoading(false);
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
        <span className="app-subtitle">Near-miss detection &amp; safety investigation · Team 34</span>
        <span className={`mode-badge mode-badge--${providerMode}`} aria-label={`Provider mode ${providerMode}`}>
          {isMock ? "DEMO MODE — fixture data, not live inference" : `LIVE · ${providerMode}`}
        </span>
      </header>

      <main className="app-main">

        {/* ── Archive Search ─────────────────────────────────────────── */}
        <section className="section section--search" aria-label="Archive search">
          <h2 className="section-title">Find Potential Near-Misses</h2>
          <form onSubmit={handleArchiveSearch} className="search-form">
            <div className="search-row">
              <input
                type="text"
                className="search-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="e.g. forklift approaching a pedestrian in a warehouse aisle"
                maxLength={500}
                disabled={searchLoading}
                autoFocus
                aria-label="Search query"
              />
              <button
                type="submit"
                className="btn-primary"
                disabled={searchLoading || !searchQuery.trim()}
                aria-busy={searchLoading}
              >
                {searchLoading ? "Searching…" : "Search Archive"}
              </button>
            </div>
            <div className="example-queries" aria-label="Example queries">
              {EXAMPLE_QUERIES.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="example-chip"
                  onClick={() => setSearchQuery(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </form>

          {searchWarnings.map((w, i) => (
            <p key={i} className="results-warning">{w}</p>
          ))}

          {searchResults !== null && (
            <div className="search-results" aria-live="polite">
              {searchResults.length === 0 ? (
                <p className="no-results">No matching clips found. Try a different query.</p>
              ) : (
                <>
                  <p className="search-count">
                    {searchResults.length} result{searchResults.length !== 1 ? "s" : ""} — click a clip to load it
                  </p>
                  <div className="search-cards">
                    {searchResults.map((r, i) => (
                      <SearchResultCard
                        key={i}
                        result={r}
                        selected={selectedResult === r}
                        onSelect={handleSelectResult}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </section>

        {/* ── Video selector (secondary) ────────────────────────────── */}
        <details className="section section--selector">
          <summary className="field-label">Or select footage directly</summary>
          <div style={{ marginTop: 8 }}>
            <select
              value={selectedVideo?.id ?? ""}
              onChange={(e) => {
                const v = videos.find((x) => x.id === e.target.value) ?? null;
                setSelectedVideo(v);
                setResult(null);
                setSelectedResult(null);
                setAllEvents([]);
                setVideoError(null);
                setReport(null);
              }}
              aria-label="Select footage"
            >
              {videos.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.title}{v.duration_sec ? ` (${fmtTime(v.duration_sec)})` : ""}
                </option>
              ))}
            </select>
            {selectedVideo && <span className="source-badge" style={{ marginLeft: 8 }}>source: {selectedVideo.source}</span>}
          </div>
        </details>

        {/* ── Video player ─────────────────────────────────────────── */}
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
            <div className="no-video">Search for near-misses above, or select a video to begin.</div>
          )}
        </section>

        {/* ── Investigation ─────────────────────────────────────────── */}
        <section className="section section--query" aria-label="Investigation query">
          <form onSubmit={handleSubmit} className="query-form">
            <label htmlFor="query-input" className="field-label">
              Investigate this footage
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
              />
              <button
                type="submit"
                className="btn-primary"
                disabled={loading || !query.trim() || !selectedVideo}
                aria-busy={loading}
              >
                {loading ? "Investigating…" : "Investigate"}
              </button>
            </div>
            <div className="filter-row">
              <label htmlFor="object-filter" className="field-label">Object filter (YOLO)</label>
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

        {/* ── Investigation results ─────────────────────────────────── */}
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
                  <thead><tr><th>Tool</th><th>Status</th><th>ms</th></tr></thead>
                  <tbody>
                    {result.tool_trace.map((t, i) => (
                      <tr key={i}><td>{t.tool}</td><td>{t.status}</td><td>{t.duration_ms}</td></tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}

            <div className="report-action">
              <button
                type="button"
                className="btn-secondary"
                onClick={handleGenerateReport}
                disabled={reportLoading}
                aria-busy={reportLoading}
              >
                {reportLoading ? "Generating report…" : "Generate Safety Investigation Report"}
              </button>
            </div>
          </section>
        )}

        {/* ── Safety report ─────────────────────────────────────────── */}
        {report && <ReportPanel report={report} />}

      </main>
    </div>
  );
}
