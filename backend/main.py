# main.py — FastAPI backend for Review Intel

from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from backend.nlp.pipeline import ReviewPipeline
except ImportError:
    from nlp.pipeline import ReviewPipeline

app = FastAPI(title="Review Intel API", version="1.0.0")

# Allow Chrome extension to call this
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # lock down to extension ID in production
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Lazily initialize heavy NLP pipeline on first usage
pipeline = None


def get_pipeline() -> ReviewPipeline:
    global pipeline
    if pipeline is None:
        pipeline = ReviewPipeline()
    return pipeline


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProductInfo(BaseModel):
    asin: str
    name: str
    domain: str
    url: str


class Review(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = ""
    body: str
    rating: Optional[float] = None
    author: Optional[str] = ""
    date: Optional[str] = ""
    verified: Optional[bool] = False
    helpful: Optional[int] = 0


class AnalyzeRequest(BaseModel):
    product: ProductInfo
    reviews: List[Review]
    aspects: Optional[List[str]] = []


class AnalyzeResponse(BaseModel):
    product: Dict[str, Any]
    total_reviews: int
    sentiment_distribution: Dict[str, int]
    aspect_sentiments: Dict[str, Dict[str, float]]
    top_positive_feature: Optional[str]
    top_negative_feature: Optional[str]
    common_complaints: List[str]
    keywords: List[str]
    summary: str
    verdict: str
    reviews: List[Dict[str, Any]]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    model_name = pipeline.model_name if pipeline is not None else "not_loaded"
    return {"status": "ok", "model": model_name}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    if not req.reviews:
        raise HTTPException(status_code=400, detail="No reviews provided")

    if len(req.reviews) > 300:
        raise HTTPException(status_code=400, detail="Max 300 reviews per request")

    try:
        runtime_pipeline = get_pipeline()
        result = runtime_pipeline.run(req.product.dict(), [r.dict() for r in req.reviews], req.aspects or [])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/features")
def analyze_features(req: AnalyzeRequest):
    """Returns only aspect-level breakdown — faster for feature-specific queries."""
    try:
        texts = [r.body for r in req.reviews if r.body.strip()]
        runtime_pipeline = get_pipeline()
        aspects = runtime_pipeline.extract_aspects_batch(texts)
        return {"aspects": aspects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
