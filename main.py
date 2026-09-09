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
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from requests import request

from ab_router import assign_variant
from admin_auth import check_credentials, issue_token, require_admin
from blender import (
    VARIANTS,
    Blender,
    catalogue_lookup,
    collaborative_pool,
    normalise_title,
)
from lyric_signal import LyricSentiment
from lyrics_adapter import LyricsAdapter
from mood import MOOD_TARGETS, MoodScorer
from outcome_logger import OutcomeLogger
from prepare_data import FEATURES
from recommender import Recommender
from schemas import (
    FeedbackRequest,
    LoginRequest,
    MetricEvent,
    Mood,
    MoodAnalyseRequest,
    MoodAnalysis,
    MoodRecommendRequest,
    OnboardRequest,
    PreferenceParameters,
    RecommendationRequest,
    RecommendationResponse,
    RecommendedTrack,
    SimilarRequest,
    TokenResponse,
)

load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
LOOKUP_CACHE = DATA_DIR / "title_lookup.pkl"
CANDIDATE_POOL = 50
LYRIC_POOL = 20
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
lyrics = LyricSentiment(LyricsAdapter())

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


def _lyric(seed_tracks, audio_pool, collab_pool, target_mood):
    """
    Lyric sentiment pool over the shortlist
    top pool cadniantes from cheaper signal, scored for closeness to the seed or  target mood
    Returns {} if no lyrics
    """

    def top(pool):
        return sorted(pool, key=pool.get, reverse=True)[:LYRIC_POOL]

    seed_compounds = []
    for tid in seed_tracks:
        at = _seed_artist_title(tid)
        if at:
            seed_compounds.append(lyrics.compound_for(tid, *at))

    reference = lyrics.reference_for(seed_compounds, target_mood)
    if reference is None:
        return {}

    shortlist = []
    for tid in dict.fromkeys(top(audio_pool) + top(collab_pool)):
        at = _seed_artist_title(tid)
        if at:
            shortlist.append((tid, *at))

    return lyrics.pool(shortlist, reference)


def _track_row(track_id: str):
    pos = recommender.id_to_pos(track_id)
    return None if pos is None else recommender.meta.iloc[pos]


def _hydrate(track_id: str, score: float, rationale: dict) -> RecommendedTrack:
    row = _track_row(track_id)
    return RecommendedTrack(
        id=track_id,
        name=str(row["row"]),  # type: ignore
        artists=str(row["artists"]),  # type: ignore
        year=int(row["year"]),  # type: ignore
        score=score,
        rationale=rationale,
    )


def _mood_from_text(text: str) -> MoodAnalysis:
    """VADER over free text -> a mood"""
    scores = lyrics.analyser.polarity_scores(text)
    compound = float(scores["compound"])
    if compound >= 0.3:
        mood = Mood.happy
    elif compound <= -0.3:
        mood = Mood.sad
    else:
        mood = Mood.any
    return MoodAnalysis(
        compound=compound,
        positive=scores["pos"],
        neutral=scores["neu"],
        negative=scores["neg"],
        mood=mood,
    )


def _run_pipeline(
    seed_tracks: list[str],
    user_id: str | None,
    params: PreferenceParameters,
    limit: int,
) -> RecommendationResponse:
    """The full hybrid pipeline. through /recommend and /mood/recommend"""
    variant_name = assign_variant(user_id)

    wants_mood = params.target_mood != Mood.any
    dim_targets = (
        mood_scorer.query_targets(params.target_mood.value) if wants_mood else None
    )

    audio_results = recommender.recommend(
        seed_tracks=seed_tracks,
        limit=CANDIDATE_POOL,
        exclude_seen=params.exclude_seen,
        dim_targets=dim_targets,
    )
    audio_pool = {r["id"]: r["rationale"]["audio_similarity"] for r in audio_results}

    collab_pool, popularity = _collaborative(seed_tracks)
    if params.exclude_seen:
        for tid in seed_tracks:
            collab_pool.pop(tid, None)

    if not audio_pool and not collab_pool:
        raise HTTPException(status_code=404, detail="No known seed tracks")

    lyric_pool: dict[str, float] = {}
    if VARIANTS[variant_name].get("lyric", 0) > 0:
        lyric_pool = _lyric(
            seed_tracks, audio_pool, collab_pool, params.target_mood.value
        )

    mood_fit = None
    if wants_mood:
        mood_fit = mood_scorer.fit_scores(
            set(audio_pool) | set(collab_pool), params.target_mood.value
        )

    blended = Blender(VARIANTS[variant_name], normalise=NORMALISE_SCORES).blend(
        {"audio": audio_pool, "collaborative": collab_pool, "lyric": lyric_pool},
        popularity=popularity or None,
        novelty=params.novelty,
        mood_fit=mood_fit,
        limit=limit,
    )
    results = [_hydrate(r["id"], r["score"], r["rationale"]) for r in blended]

    request_id = logger.log_request(
        user_id=user_id,
        variant=variant_name,
        seeds=seed_tracks,
        params=params.model_dump(mode="json"),
        result_ids=[r.id for r in results],
    )

    return RecommendationResponse(
        request_id=request_id,
        seed_tracks=seed_tracks,
        results=results,
        variant=variant_name,
    )


# Routes ----------------------------------------------------------------------


@app.get("/health")
def health():
    return {
        "status": "ok",
        "catalogue_size": recommender.index.ntotal,
        "collaborative_signal": adapter is not None,
        "lyric_signal": True,
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
    return _run_pipeline(req.seed_tracks, req.user_id, req.parameters, req.limit)


@app.post("/recommend/similar")
def recommend_similar(req: SimilarRequest):
    """Audio neartest track to one"""
    if req.track_id not in recommender.id_to_pos:
        raise HTTPException(status_code=404, detail="Unknown track id")

    results = recommender.recommend([req.track_id], limit=req.limit)

    return {
        "track_id": req.track_id,
        "results": [
            _hydrate(
                r["id"],
                r["rationale"]["audio_similarity"],
                {"audio": r["rationale"]["audio_similarity"]},
            )
            for r in results
        ],
    }


@app.post("/onboard")
def onboard(req: OnboardRequest):
    """
    Cold-start seeding
    turns artist names into candidate seed track

    """
    candidates = {}
    for artist in req.artists:
        for hit in recommender.search(artist, limit=req.limit):
            candidates.setdefault(hit["id"], hit)

    if not candidates:
        raise HTTPException(status_code=404, detail="No catalogue tracks")

    ids = list(candidates)
    if req.target_mood != Mood.any:
        fit = mood_scorer.fit_scores(ids, req.target_mood.value)
        ids.sort(key=lambda i: fit.get(i, 0.0), reverse=True)

    return {
        "artists": req.artists,
        "target_mood": req.target_mood,
        "seeds": [
            {k: candidates[i][k] for k in ("id", "name", "artists", "year")}
            for i in ids[: req.limit]
        ],
    }


@app.post("/mood/analyse", response_model=MoodAnalysis)
def mood_analyse(req: MoodAnalyseRequest):
    """VADER: emotional sentiment of the free text"""
    return _mood_from_text(req.text)


@app.post("/mood/recommend", response_model=RecommendationResponse)
def mood_recommend(req: MoodRecommendRequest):
    """Mood-driven recommendation - text set target_mood"""
    analysis = _mood_from_text(req.text)
    params = PreferenceParameters(novelty=req.novelty, target_mood=analysis.mood)
    return _run_pipeline(req.seed_tracks, req.user_id, params, req.limit)


@app.get("/tracks/{track_id}/info")
def track_info(track_id: str):
    row = _track_row(track_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unkown track id")

    return {
        k: (int(row[k]) if k == "year" else str(row[k]))
        for k in ("id", "name", "artist", "year")
    }


@app.get("/tracks/{track_id}/features")
def track_features(track_id: str):
    """
    Audio features for a tracks
    """

    pos = recommender.id_to_pos.get(track_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="Unknown track id")

    standardised = recommender.index.reconstruct(pos)
    raw = recommender.scaler.inverse_transform(standardised.reshape(1, -1))[0]

    return {
        "id": track_id,
        "features": {f: round(float(v), 4) for f, v in zip(FEATURES, raw)},
        "standardised": {f: round(float(v), 4) for f, v in zip(FEATURES, standardised)},
    }


# JWT/ADMIN


@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest):
    if not check_credentials(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token, ttl = issue_token(req.username)
    return TokenResponse(access_token=token, expires_in=ttl)


@app.get("/admin/stats")
def admin_stats(_: str = Depends(require_admin)):
    """Aggregate experiment counts"""
    return logger.stats()


@app.get("/admin/health")
def admin_health(_: str = Depends(require_admin)):
    """Detailed component status for the operator"""
    return {
        "catalogue_size": recommender.index.ntotal,
        "index_nprobe": recommender.index.nprobe,  # type: ignore
        "signal": {
            "audio": True,
            "collaborative": adapter is not None,
            "lyric": True,
        },
        "variants": list(VARIANTS),
        "moods": ["any", *MOOD_TARGETS],
        "normalise_scores": NORMALISE_SCORES,
        "candidate_pool": CANDIDATE_POOL,
        "lyric_pool": LYRIC_POOL,
    }
