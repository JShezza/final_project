/**
 * api.js - call the client makes to NextTrack api
 */

const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function request(path, options) {
    const res = await fetch(`${BASE}${path}`, options);
    if (!res.ok) {
        let detail = `Request failed (${res.status})`;
        try {
            const body = await res.json();
            if (body.detail)
                detail = typeof body.detail == "string" ? body.detail : detail;
        } catch {
            // no json body
        }
        throw new Error(detail);
    }
    return res.json();
}

const json = (body) => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
});

export const searchTracks = (q, limit = 30) =>
    request(`/tracks/search?q=${encodeURIComponent(q)}&limit=${limit}`);

export const health = () => request(`/health`);

export const recommend = ({
    seedTracks,
    userId,
    novelty,
    targetMood,
    excludeSeen,
    limit,
    strategy,
}) =>
    request(
        `/recommend`,
        json({
            seed_tracks: seedTracks,
            userId: userId || null,
            strategy: strategy || null,
            limit,
            parameters: {
                novelty,
                target_mood: targetMood,
                exclude_seen: excludeSeen,
            },
        }),
    );

export const sendFeedback = (requestId, trackId, rating) =>
    request(
        `/feedback`,
        json({
            request_id: requestId,
            track_id: trackId,
            rating,
        }),
    );
