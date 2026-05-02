from pydantic import BaseModel, Field
from typing import Optional


class RawReview(BaseModel):
    id: str
    text: str
    rating: float = Field(ge=0, le=5)
    date: str = ""
    username: str = "Anonymous"
    helpful: int = 0


class AnalysisRequest(BaseModel):
    reviews: list[RawReview]
    product_title: str = ""


# ── Response models ────────────────────────────────────────────────────────────

class ProcessedReview(BaseModel):
    id: str
    text: str
    rating: float
    date: str
    username: str
    helpful: int
    sentiment: str          # "positive" | "neutral" | "negative"
    sentiment_score: float  # confidence 0-1
    aspects: dict[str, str] # {"battery": "positive", "camera": "negative"}
    keywords: list[str]


class SentimentDistribution(BaseModel):
    positive: int
    neutral: int
    negative: int


class AspectSentiment(BaseModel):
    aspect: str
    positive: int
    neutral: int
    negative: int
    score: float  # net sentiment -1 to 1


class TrendPoint(BaseModel):
    period: str   # "Jan 2024"
    positive: int
    neutral: int
    negative: int
    avg_rating: float


class Insight(BaseModel):
    type: str     # "praise" | "complaint" | "neutral"
    text: str
    count: int


class AnalysisResponse(BaseModel):
    product_title: str
    total_reviews: int
    sentiment_distribution: SentimentDistribution
    aspect_sentiment: list[AspectSentiment]
    trends: list[TrendPoint]
    insights: list[Insight]
    top_keywords: list[str]
    reviews: list[ProcessedReview]
