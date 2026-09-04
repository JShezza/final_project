"""
FastAPI layer
uvicorn main:app --reload to run

Endpoints:
POST    /recommend
GET     /tracks/search
GET     /health
"""

import os
import pickle
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ab_router import assign_variant
from blender import (
    VARIANTS,
    Blender,
    catalogue_lookup,
    collaborative_pool,
    normalise_title,
)
from mood import MoodScorer
from outcome_logger import OutcomeLogger
from recommender import Recommender
from schemas import (
    FeedbackRequest,
    MetricEvent,
    Mood,
    RecommendationRequest,
    RecommendationResponse,
    RecommendedTrack,
)

load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
LOOKUP_CACHE = DATA_DIR / "title_lookup.pkl"
CANDIDATE_POOL = 50
NORMALISE_SCORES = True

app = FastAPI(title="NextTrack API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start recommender at start up ----------------------------------------------
recommender = Recommender()
logger = OutcomeLogger()
mood_scorer = MoodScorer(recommender)

# Lookup cache
if LOOKUP_CACHE.exists():
    with open(LOOKUP_CACHE, "rb") as f:
        title_lookup = pickle.load(f)
else:
    title_lookup = catalogue_lookup(recommender.meta)
    with open(LOOKUP_CACHE, "wb") as f:
        pickle.dump(title_lookup, f)

adapter = None
_key = os.environ.get("LASTFM_API_KEY")
if _key:
    from lastfm_adapter import LastFmAdapter

    adapter = LastFmAdapter(api_key=_key)
else:
    print("WARNING: No LAST_FM_API KEY. ONLY RUNNING IN AUDIO-ONLY MODE")


# Helper functions -----------------------------------------------------------
def _seed_artist_title(track_id: str) -> tuple[str, str] | None:
    """Look up seed id in catalogue: (first artist, track name)"""
    pos = recommender.id_to_pos.get(track_id)

    if pos is None:
        return None
    row = recommender.meta.iloc[pos]
    return str(row["artists"]).split(",")[0], str(row["name"])


def _collaborative(seed_tracks: list[str]) -> tuple[dict, dict]:
    """
    Query last.fm for every known seed and merge results into one candidate pool
    ({id: match}) ({id: playcount})
    """
    pool: dict[str, float] = {}
    popularity: dict[str, float] = {}

    if adapter is None:
        return pool, popularity

    for tid in seed_tracks:
        at = _seed_artist_title(tid)

        if at is None:
            continue

        artist, title = at
        similar = adapter.similar_tracks(artist, title, limit=CANDIDATE_POOL)
        matched = collaborative_pool(similar, title_lookup)

        for cid, score in matched.items():
            pool[cid] = max(pool.get(cid, 0.0), score)

        # Popularity for novelty bias
        for t in similar:
            cid = title_lookup.get(normalise_title(t["name"], t["artist"]))

            if cid is not None and t.get("playcount"):
                popularity[cid] = max(popularity.get(cid, 0), t["playcount"])

    return pool, popularity


# Routes ----------------------------------------------------------------------


@app.get("/health")
def health():
    return {
        "status": "ok",
        "catalogue_size": recommender.index.ntotal,
        "collaborative_signal": adapter is not None,
    }


@app.get("/tracks/search")
def search_tracks(q: str, limit: int = 10):
    """Search catalogue by track name for seed ids"""
    return {"query": q, "results": recommender.search(q, limit)}


@app.get("/experiments/{name}/variant")
def experiment_variant(name: str, user_id: str):
    """WHich A/B variant is assigned to a user id"""
    return {"experiment": name, "user_id": user_id, "variant": assign_variant(user_id)}


@app.post("/feedback")
def feedback(fb: FeedbackRequest):
    """Record rating against logged request. Thumbs up/down/skip"""
    if not logger.log_feedback(fb.request_id, fb.track_id, fb.rating):
        raise HTTPException(status_code=404, detail="Unknown request_id")
    return {"status": "recorded"}


@app.post("/experiments/{name}/metrics")
def experiment_metrics(name: str, event: MetricEvent):
    """Log a metric observation for offline user"""
    variant = assign_variant(event.user_id) if event.user_id else None
    logger.log_metric(name, event.user_id, variant, event.metric, event.value)
    return {"status": "recorded", "experiment": name, "variant": variant}


@app.post("/recommend", response_model=RecommendationResponse)
def recommend(req: RecommendationRequest):
    # A/B Router strategy
    variant_name = assign_variant(req.user_id)

    wants_mood = req.parameters.target_mood != Mood.any
    dim_targets = (
        mood_scorer.query_targets(req.parameters.target_mood.value)
        if wants_mood
        else None
    )

    audio_results = recommender.recommend(
        seed_tracks=req.seed_tracks,
        limit=CANDIDATE_POOL,
        exclude_seen=req.parameters.exclude_seen,
        dim_targets=dim_targets,
    )
    audio_pool = {r["id"]: r["rationale"]["audio_similarity"] for r in audio_results}

    collab_pool, popularity = _collaborative(req.seed_tracks)
    if req.parameters.exclude_seen:
        for tid in req.seed_tracks:
            collab_pool.pop(tid, None)

    if not audio_pool and not collab_pool:
        # No seeds ids in catalogue
        raise HTTPException(status_code=404, detail="No known seed tracks.")

    mood_fit = None
    if wants_mood:
        mood_fit = mood_scorer.fit_scores(
            set(audio_pool) | set(collab_pool), req.parameters.target_mood.value
        )

    blended = Blender(VARIANTS[variant_name], normalise=NORMALISE_SCORES).blend(
        {"audio": audio_pool, "collaborative": collab_pool},
        popularity=popularity or None,
        novelty=req.parameters.novelty,
        mood_fit=mood_fit,
        limit=req.limit,
    )

    results = []
    for r in blended:
        pos = recommender.id_to_pos[r["id"]]
        row = recommender.meta.iloc[pos]
        results.append(
            RecommendedTrack(
                id=r["id"],
                name=str(row["name"]),
                artists=str(row["artists"]),
                year=int(row["year"]),
                score=r["score"],
                rationale=r["rationale"],
            )
        )

    # log it with outcome_logger
    request_id = logger.log_request(
        user_id=req.user_id,
        variant=variant_name,
        seeds=req.seed_tracks,
        params=req.parameters.model_dump(mode="json"),
        result_ids=[r.id for r in results],
    )

    return RecommendationResponse(
        request_id=request_id,
        seed_tracks=req.seed_tracks,
        results=results,
        variant=variant_name,
    )
