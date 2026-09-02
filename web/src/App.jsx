import { useState, useEffect, useRef } from "react";
import { health, recommend, searchTracks, sendFeedback } from "./api.js";

const MOODS = ["any", "happy", "sad", "energetic", "calm"];
const SIGNAL_COLOUR = { audio: "var(--audio)", collaborative: "var(--collab)" };

function App() {
    const [seeds, setSeeds] = useState([]);
    const [query, setQuery] = useState("");
    const [matches, setMatches] = useState([]);
    const [searching, setSearching] = useState(false);

    const [userId, setUserId] = useState("");
    const [novelty, setNovelty] = useState(0.5);
    const [targetMood, setTargetMood] = useState("any");
    const [excludeSeen, setExcludeSeen] = useState(true);
    const [limit, setLimit] = useState(10);

    const [response, setResponse] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [ratings, setRatings] = useState({});
    const [blind, setBlind] = useState(false);
    const [status, setStatus] = useState(null);
    const [openTrack, setOpenTrack] = useState(null);

    useEffect(() => {
        health()
            .then(setStatus)
            .catch(() => setError("Can't reach API. Check uvicorn running"));
    }, []);

    // Debounce search
    useEffect(() => {
        if (query.trim().length < 2) {
            setMatches([]);
            return;
        }
        setSearching(true);
        const timer = setTimeout(() => {
            searchTracks(query)
                .then((r) => setMatches(r.results))
                .catch(() => setMatches([]))
                .finally(() => setSearching(false));
        }, 250);
        return () => clearTimeout(timer);
    }, [query]);

    function addSeed(track) {
        if (!seeds.some((s) => s.id === track.id)) setSeeds([...seeds, track]);
        setQuery("");
        setMatches([]);
    }

    // getRecommendations function needed
    async function getRecommendations() {
        setLoading(true);
        setError(null);
        setRatings({});
        setOpenTrack(null);
        try {
            const data = await recommend({
                seedTracks: seeds.map((s) => s.id),
                userId,
                novelty,
                targetMood,
                excludeSeen,
                limit,
            });
            setResponse(data);
        } catch (e) {
            setError(e.message);
            setResponse(null);
        } finally {
            setLoading(false);
        }
    }

    // rate function
    async function rate(trackId, rating) {
        setRatings((r) => ({ ...r, [trackId]: rating }));
        try {
            await sendFeedback(response.request_id, trackId, rating);
        } catch {
            setError(
                "Rating didn't save. Not included orcount towards experiment.",
            );
        }
    }
    // HTML Rendering
    return (
        <div className="page">
            <header className="header">
                <h1>NextTrack</h1>
                <p className="tagline">
                    {" "}
                    Recommendations from tracks you send!
                </p>
                {status && (
                    <p className="status">
                        {status.catalogue_size.toLocaleString()} tracks
                        {status.collaborative_signal
                            ? " · audio and collaborative signals"
                            : "· audio signal only"}
                    </p>
                )}
            </header>

            <main className="layout">
                <section className="panel controls" aria-label="Request">
                    <h2>Seed Tracks</h2>
                    <p className="hint">
                        The songs your recommendation will be built from
                    </p>
                    <div className="seed-input">
                        <input
                            type="text"
                            value={query}
                            placeholder="Search Catalogue"
                            onChange={(e) => setQuery(e.target.value)}
                            aria-label="Search for a track to add as a seed"
                        />
                        {searching && (
                            <span className="spinner" aria-hidden="true" />
                        )}
                    </div>

                    {matches.length > 0 && (
                        <ul className="matches">
                            {matches.map((m) => (
                                <li key={m.id}>
                                    <button onClick={() => addSeed(m)}>
                                        <span className="match-name">
                                            {m.name}
                                        </span>
                                        <span className="match-artist">
                                            {m.artists} · {m.year}
                                        </span>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}

                    {seeds.length > 0 && (
                        <ul className="chips">
                            {seeds.map((s) => (
                                <li className="chip" key={s.id}>
                                    {s.name}
                                    <button
                                        onClick={() =>
                                            setSeeds(
                                                seeds.filter(
                                                    (x) => x.id !== s.id,
                                                ),
                                            )
                                        }
                                        aria-label={`Remove ${s.name}`}
                                    ></button>
                                </li>
                            ))}
                        </ul>
                    )}

                    <h2>Preferences</h2>
                    <label className="field">
                        <span className="field-label">
                            Novelty
                            <output>{novelty.toFixed(2)}</output>
                        </span>
                        <input
                            type="range"
                            min="0"
                            max="1"
                            step="0.05"
                            value={novelty}
                            onChange={(e) => setNovelty(Number(e.target.value))}
                        />
                        <span className="hint">
                            Higher values push away from tracks with large
                            listener counts.
                        </span>
                    </label>

                    <label className="field">
                        <span className="field-label">Mood</span>
                        <select
                            value={targetMood}
                            onChange={(e) => setTargetMood(e.target.value)}
                        >
                            {MOODS.map((m) => (
                                <option key={m} value={m}>
                                    {" "}
                                    {m}
                                </option>
                            ))}
                        </select>
                    </label>

                    <label className="field">
                        <span className="field-label">
                            Tracks to return
                            <output>{limit}</output>
                        </span>
                        <input
                            type="range"
                            min="1"
                            max="20"
                            value={limit}
                            onChange={(e) => setLimit(Number(e.target.value))}
                        />
                    </label>

                    <label className="checkbox">
                        <input
                            type="checkbox"
                            checked={excludeSeen}
                            onChange={(e) => setExcludeSeen(e.target.checked)}
                        />
                        Leave out seed tracks
                    </label>
                    <label className="field">
                        <span className="field-label">Session Key</span>
                        <input
                            type="text"
                            value={userId}
                            placeholder="optional"
                            onChange={(e) => setUserId(e.target.value)}
                        />
                        <span className="hint">
                            Keeps you on one strategy across requests.
                        </span>
                    </label>

                    <button
                        className="primary"
                        onClick={getRecommendations}
                        disabled={seeds.length === 0 || loading}
                    >
                        {loading ? "Finding a track" : "Get recommendations"}
                    </button>
                    {seeds.length === 0 && (
                        <p className="hint">Add at least one track to start</p>
                    )}
                </section>

                <section className="panel results" aria-label="Recommendations">
                    <div className="results-head">
                        <h2>Recommendations</h2>
                        <label className="checkbox blind">
                            <input
                                type="checkbox"
                                checked={blind}
                                onChange={(e) => setBlind(e.target.checked)}
                            />
                            Hide how it was chosen
                        </label>
                    </div>

                    {error && <p className="error">{error}</p>}

                    {!response && !error && (
                        <p className="empty">
                            Pick a seed and the recommendations will display
                            with the reasoning.
                        </p>
                    )}

                    {response && (
                        <>
                            {!blind && (
                                <p className="variant">
                                    Strategy:{" "}
                                    <strong>{response.variant}</strong>
                                </p>
                            )}
                            <ol className="tracks">
                                {response.results.map((t) => (
                                    <TrackRow
                                        key={t.id}
                                        track={t}
                                        topScore={response.results[0].score}
                                        blind={blind}
                                        rating={ratings[t.id]}
                                        onRate={rate}
                                        open={openTrack === t.id}
                                        onOpen={() =>
                                            setOpenTrack(
                                                openTrack === t.id
                                                    ? null
                                                    : t.id,
                                            )
                                        }
                                    />
                                ))}
                            </ol>
                        </>
                    )}
                </section>
            </main>
        </div>
    );
}

function TrackRow({ track, topScore, blind, rating, onRate, open, onOpen }) {
    const total = Object.values(track.rationale).reduce((a, b) => a + b, 0);
    const strength =
        topScore > 0 ? Math.max((track.score / topScore) * 100, 4) : 0;

    return (
        <li className="track">
            <div className="track-row">
                <button
                    className="play"
                    onClick={onOpen}
                    aria-expanded={open}
                    aria-label={
                        open
                            ? `Close play for ${track.name}`
                            : `Play ${track.name}`
                    }
                >
                    {open ? "\u00d7" : "\u25b6"}
                </button>

                <div className="track-body">
                    <p className="track-name">{track.name}</p>
                    <p className="track-meta">
                        {track.artists} · {track.year}
                    </p>

                    {!blind && total > 0 && (
                        <div className="rationale">
                            <div
                                className="bar"
                                style={{ width: `${strength}` }}
                                role="img"
                                aria-label={`Score ${track.score.toFixed(2)}, signal contributions`}
                            >
                                {Object.entries(track.rationale)
                                    .filter(([, v]) => v > 0)
                                    .map(([signal, value]) => (
                                        <span
                                            className="bar-part"
                                            key={signal}
                                            style={{
                                                width: `${(value / total) * 100}%`,
                                                background:
                                                    SIGNAL_COLOUR[signal],
                                            }}
                                        ></span>
                                    ))}
                            </div>
                            <p className="rationale-text">
                                {Object.entries(track.rationale)
                                    .filter(([, v]) => v > 0)
                                    .map(
                                        ([signal, value]) =>
                                            `${signal} ${value.toFixed(2)}`,
                                    )
                                    .join("  ")}
                            </p>
                        </div>
                    )}
                </div>
                <div className="ratings">
                    {[
                        ["up", "\ud83d\udc4d"],
                        ["down", "\ud83d\udc4e"],
                        ["skip", "\u21b7"],
                    ].map(([value, glyph]) => (
                        <button
                            key={value}
                            className={
                                rating === value ? "rate chosen" : "rate"
                            }
                            onClick={() => onRate(track.id, value)}
                            aria-label={value}
                        >
                            {glyph}
                        </button>
                    ))}
                </div>
            </div>

            {/* Spotify embed for 30s sample without account*/}
            {open && (
                <iframe
                    classsName="embed"
                    title={`Spotify player for ${track.name}`}
                    src={`https://open.spotify.com/embed/track/${track.id}?utm_source=nexttrack`}
                    width="100%"
                    height="80"
                    frameborder="0"
                    allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
                    loading="lazy"
                />
            )}
        </li>
    );
}

export default App;
