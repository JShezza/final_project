from pydantic import BaseModel, Field


class PreferenceParameters(BaseModel):
    """User controllable params with each request"""

    exclude_seen: bool = True  # Ignore tracks that have been used in the request


class RecommendationRequest(BaseModel):
    seed_tracks: list[str] = Field(..., min_length=1, max_length=50)
    parameters: PreferenceParameters = PreferenceParameters()
    limit: int = Field(10, ge=1, le=20)


class Rationale(BaseModel):
    """Why a track was recommended by a signal"""

    audio_similarity: float


class RecommendedTrack(BaseModel):
    id: str
    name: str
    artists: str
    year: int
    rationale: Rationale


class RecommendationResponse(BaseModel):
    seed_tracks: list[str]
    results: list[RecommendedTrack]
    variant: str = "faiss"  # The strategy used to handle the request
