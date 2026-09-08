from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Mood(str, Enum):
    """Target Moods for context engine and lyric sentiment"""

    any = "any"
    happy = "happy"
    sad = "sad"
    energetic = "energetic"
    calm = "calm"


class PreferenceParameters(BaseModel):
    """User controllable params with each request"""

    novelty: float = Field(0.5, ge=0, le=1)  # greater or equal, less or equal

    target_mood: Mood = Mood.any
    exclude_seen: bool = True  # Ignore tracks that have been used in the request


class RecommendationRequest(BaseModel):
    # Opaque key for only A/B variant assignment and anonymous logging
    user_id: str | None = None

    seed_tracks: list[str] = Field(..., min_length=1, max_length=50)
    parameters: PreferenceParameters = PreferenceParameters()
    limit: int = Field(1, ge=1, le=20)


class RecommendedTrack(BaseModel):
    id: str
    name: str
    artists: str
    year: int
    score: float
    rationale: dict[str, float]  # e.g {"audio": 0.31, "collaborate": 0.45}


class RecommendationResponse(BaseModel):
    request_id: str  # linked to outcome logger
    seed_tracks: list[str]
    results: list[RecommendedTrack]
    variant: str  # The strategy used to handle the request


class FeedbackRequest(BaseModel):
    """Rating for a recommended track tied to a logged request"""

    request_id: str
    track_id: str
    rating: Literal["up", "down", "skip"]


class MetricEvent(BaseModel):
    """Named metric observation for offline analysis"""

    user_id: str | None = None
    metric: str
    value: float


class SimilarRequest(BaseModel):
    """Tracks similar to one track"""

    track_id: str
    limit: int = Field(10, ge=1, le=50)


class OnboardRequest(BaseModel):
    """
    Cold start seed. New users don't have history so name artists
    and a mood for seed tracks to start with.
    """

    artists: list[str] = Field(..., min_length=1, max_length=10)
    target_mood: Mood = Mood.any
    limit: int = Field(10, ge=1, le=30)


class MoodAnalyseRequest(BaseModel):
    """Free  text describing the vibe"""

    text: str = Field(..., min_length=1, max_length=2000)


class MoodAnalysis(BaseModel):
    compound: float  # Vader polarity -1 to +1
    positive: float
    neutral: float
    negative: float
    mood: Mood  # happy sad any


class MoodRecommendRequest(BaseModel):
    """Mood driven recommendation"""

    text: str = Field(..., min_length=1, max_length=2000)
    seed_tracks: list[str] = Field(..., min_length=1, max_length=50)
    user_id: str | None = None
    novelty: float = Field(0.5, ge=0, le=1)
    limit: int = Field(1, ge=1, le=20)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # Seconds
