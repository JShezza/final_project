"""
FastAPI layer
uvicorn main:app --reload to run

Endpoints:
POST    /recommend
GET     /tracks/search
GET     /health
"""

from fastapi import FastAPI, HTTPException

from recommender import Recommender
from schemas import RecommendationRequest, RecommendationResponse

app = FastAPI(title="NextTrack API")

# Start recommender at start up
recommender = Recommender()


@app.post("/recommend", response_model=RecommendationResponse)
def recommend(req: RecommendationRequest):
    results = recommender.recommend(
        seed_tracks=req.seed_tracks,
        limit=req.limit,
        exclude_seen=req.parameters.exclude_seen,
    )
    if not results:
        # No seeds ids in catalogue
        raise HTTPException(status_code=404, detail="No known seed tracks.")
    return RecommendationResponse(seed_tracks=req.seed_tracks, results=results)


@app.get("/tracks/search")
def search_tracks(q: str, limit: int = 10):
    """Search catalogue by track name for seed ids"""
    return {"query": q, "results": recommender.search(q, limit)}


@app.get("/health")
def health():
    return {"status": "ok", "catalogue_size": recommender.index.ntotal}
