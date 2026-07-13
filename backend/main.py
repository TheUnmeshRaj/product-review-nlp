# main.py — FastAPI backend for Review Intel

import os
from typing import Any, Dict, List, Optional

import uvicorn
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

try:
    from backend.nlp.pipeline import ReviewPipeline
except ImportError:
    from nlp.pipeline import ReviewPipeline

try:
    from backend.database import init_db, save_product_data, get_product_data
except ImportError:
    from database import init_db, save_product_data, get_product_data

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = FastAPI(title="Review Intel API", version="1.0.0")

# Allow Chrome extension to call this
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # lock down to extension ID in production
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

_pipeline: ReviewPipeline | None = None


def get_pipeline() -> ReviewPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ReviewPipeline()
    return _pipeline


@app.on_event("startup")
def startup_event():
    init_db()


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


class ChatRequest(BaseModel):
    asin: str
    message: str
    history: Optional[List[Dict[str, str]]] = []


class ChatResponse(BaseModel):
    response: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    if not req.reviews:
        raise HTTPException(status_code=400, detail="No reviews provided")

    if len(req.reviews) > 300:
        raise HTTPException(status_code=400, detail="Max 300 reviews per request")

    try:
        pipeline = get_pipeline()
        result = pipeline.run(req.product.dict(), [r.dict() for r in req.reviews], req.aspects or [])
        
        # Cache product data and reviews locally in SQLite database
        save_product_data(
            asin=req.product.asin,
            name=req.product.name,
            domain=req.product.domain,
            url=req.product.url,
            analytics=result,
            reviews=[r.dict() for r in req.reviews]
        )
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/features")
def analyze_features(req: AnalyzeRequest):
    """Returns only aspect-level breakdown — faster for feature-specific queries."""
    try:
        pipeline = get_pipeline()
        texts = [r.body for r in req.reviews if r.body.strip()]
        aspects = pipeline.extract_aspects_batch(texts)
        return {"aspects": aspects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY is not configured in backend/.env file."
        )

    # Retrieve cached product analysis data
    prod_data = get_product_data(req.asin)
    if not prod_data:
        raise HTTPException(
            status_code=404,
            detail="No analyzed review data found for this ASIN. Please run 'Analyze Reviews' first."
        )

    name = prod_data["name"]
    analytics = prod_data["analytics"]
    reviews = prod_data["reviews"]

    total = analytics.get("total_reviews", 0)
    dist = analytics.get("sentiment_distribution", {"positive": 0, "neutral": 0, "negative": 0})
    pos_pct = round(dist.get("positive", 0) / max(total, 1) * 100, 1)
    neg_pct = round(dist.get("negative", 0) / max(total, 1) * 100, 1)
    neu_pct = round(dist.get("neutral", 0) / max(total, 1) * 100, 1)

    aspects = analytics.get("aspect_sentiments", {})
    praised = [k for k, v in aspects.items() if v.get("positive", 0) > 60]
    complained = [k for k, v in aspects.items() if v.get("negative", 0) > 40]
    common_complaints = analytics.get("common_complaints", [])
    summary = analytics.get("summary", "")
    verdict = analytics.get("verdict", "")

    # Format review snippets to provide context to the LLM
    review_snippets = []
    for r in reviews[:15]:
        title = r.get("title", "")
        body = r.get("body", "")
        rating = r.get("rating", "")
        review_snippets.append(f"- [{rating} Stars] Title: {title}. Body: {body}")
    excerpts_str = "\n".join(review_snippets)

    # Formulate context prompt
    system_prompt = (
        f"You are Review Assistant, an AI expert helper for product analysis. You are answering user questions "
        f"about the product '{name}' (ASIN: {req.asin}) based on computed review analytics and feedback context.\n\n"
        f"--- ANALYSIS METADATA ---\n"
        f"Total Reviews: {total}\n"
        f"Sentiment Split: Positive: {pos_pct}%, Negative: {neg_pct}%, Neutral: {neu_pct}%\n"
        f"Praised Aspects (highly positive): {', '.join(praised) if praised else 'None'}\n"
        f"Complained Aspects (highly negative): {', '.join(complained) if complained else 'None'}\n"
        f"Common Complaints: {', '.join(common_complaints) if common_complaints else 'None'}\n"
        f"Extracted Summary: {summary}\n"
        f"Computed Verdict: {verdict}\n\n"
        f"--- SAMPLE CUSTOMER REVIEWS ---\n"
        f"{excerpts_str}\n\n"
        f"--- INSTRUCTIONS ---\n"
        f"- Base your answer on the provided metadata and customer reviews context.\n"
        f"- Do not speculate on details that are not in the context. If the context does not discuss the user's specific query, say so clearly.\n"
        f"- Keep your response helpful, professional, and relatively concise (maximum 3 paragraphs)."
    )

    messages = [{"role": "system", "content": system_prompt}]
    for h in req.history:
        # Map 'user' and 'assistant' keys to standard role/content format
        role = "user" if h.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": h.get("content", "")})
    messages.append({"role": "user", "content": req.message})

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama3-8b-8192",
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 800
                },
                timeout=30.0
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"Groq API Error {response.status_code}: {response.text}"
                )
            
            resp_data = response.json()
            reply = resp_data["choices"][0]["message"]["content"]
            return ChatResponse(response=reply)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=500, detail=f"Request to Groq API failed: {exc}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
