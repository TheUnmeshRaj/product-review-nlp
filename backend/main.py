# main.py — FastAPI backend for Review Intel

import os
import re
import datetime
from typing import Any, Dict, List, Optional

import uvicorn
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from bs4 import BeautifulSoup

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
    time_filter: Optional[str] = "all"


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


class AnalyzeHtmlRequest(BaseModel):
    html: str
    url: Optional[str] = None
    aspects: Optional[List[str]] = []
    time_filter: Optional[str] = "all"


class ChatRequest(BaseModel):
    asin: str
    message: str
    history: Optional[List[Dict[str, str]]] = []


class ChatResponse(BaseModel):
    response: str


# ── Parser & Date Helpers ──────────────────────────────────────────────────────

MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}


def parse_amazon_date(date_str: str) -> Optional[datetime.date]:
    if not date_str:
        return None
    s = date_str.lower().strip()
    s = re.sub(r"^reviewed in .* on ", "", s)
    year_match = re.search(r"\b(20\d{2})\b", s)
    if not year_match:
        return None
    year = int(year_match.group(1))
    
    month = None
    for m_name, m_val in MONTH_MAP.items():
        if m_name in s:
            month = m_val
            break
    if not month:
        return None
        
    s_no_year = s.replace(str(year), "")
    day_match = re.search(r"\b(\d{1,2})\b", s_no_year)
    day = int(day_match.group(1)) if day_match else 1
    
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def parse_amazon_html(html_content: str, url: Optional[str] = None) -> Dict[str, Any]:
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Extract Product Name
    name_el = soup.find(id="productTitle") or soup.select_one("h1.a-size-large") or soup.find("h1")
    product_name = name_el.get_text().strip() if name_el else "Unknown Product"
    
    # Extract ASIN
    asin = None
    if url:
        asin_match = re.search(r"\/(?:dp|product-reviews)\/([A-Z0-9]{10})", url)
        if asin_match:
            asin = asin_match.group(1)
            
    if not asin:
        asin_el = soup.find(id="ASIN") or soup.find(attrs={"name": "ASIN"})
        if asin_el:
            asin = asin_el.get("value") or asin_el.get("content")
            
    if not asin:
        dp_link = soup.select_one("link[rel='canonical']")
        if dp_link and dp_link.get("href"):
            asin_match = re.search(r"\/(?:dp|product-reviews)\/([A-Z0-9]{10})", dp_link.get("href"))
            if asin_match:
                asin = asin_match.group(1)
                
    asin = asin or "UNKNOWN"
    
    # Extract Reviews
    review_elements = soup.select('[data-hook="review"], .a-section.review, [id^="customer_review-"]')
    
    reviews = []
    for el in review_elements:
        try:
            # Rating
            rating_el = el.select_one('[data-hook="review-star-rating"] .a-icon-alt, [data-hook="cmps-review-star-rating"] .a-icon-alt, .a-icon-star .a-icon-alt, .review-rating .a-icon-alt')
            rating_text = rating_el.get_text() if rating_el else ""
            rating_match = re.search(r"([\d.]+)", rating_text)
            rating = float(rating_match.group(1)) if rating_match else None
            
            # Title
            title_el = el.select_one('[data-hook="review-title"], .review-title')
            title = ""
            if title_el:
                for icon in title_el.select(".a-icon-alt"):
                    icon.decompose()
                title = title_el.get_text().strip()
                
            # Body
            body_el = el.select_one('[data-hook="review-body"] span, [data-hook="review-body"], .review-text')
            body = body_el.get_text().strip() if body_el else ""
            if not body:
                continue
                
            # Author
            author_el = el.select_one('.a-profile-name, [data-hook="review-author"], .author')
            author = author_el.get_text().strip() if author_el else "Anonymous"
            
            # Date
            date_el = el.select_one('[data-hook="review-date"], .review-date')
            date_raw = date_el.get_text().strip() if date_el else ""
            date_match = re.search(r"on (.+)$", date_raw)
            date = date_match.group(1) if date_match else date_raw
            
            # Verified
            verified = bool(el.select_one('[data-hook="avp-badge"], .verified-purchase') or el.select_one('[data-hook="avp-badge"]'))
            
            # Helpful
            helpful_el = el.select_one('[data-hook="helpful-vote-statement"]')
            helpful_text = helpful_el.get_text() if helpful_el else ""
            helpful_match = re.search(r"(\d+)", helpful_text)
            helpful = int(helpful_match.group(1)) if helpful_match else 0
            
            review_id = el.get("id") or f"r_{os.urandom(4).hex()}"
            
            reviews.append({
                "id": review_id,
                "title": title,
                "body": body,
                "rating": rating,
                "author": author,
                "date": date,
                "verified": verified,
                "helpful": helpful
            })
        except Exception:
            continue
            
    return {
        "product": {
            "asin": asin,
            "name": product_name,
            "domain": "amazon.in" if "amazon.in" in (url or "") else "amazon.com",
            "url": url or f"https://www.amazon.com/dp/{asin}"
        },
        "reviews": reviews
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    if not req.reviews:
        raise HTTPException(status_code=400, detail="No reviews provided")

    reviews_list = [r.dict() for r in req.reviews]
    
    # Filter reviews by date if time_filter is specified
    if req.time_filter and req.time_filter != "all":
        try:
            days_limit = int(req.time_filter)
            cutoff_date = datetime.date.today() - datetime.timedelta(days=days_limit)
            
            filtered = []
            for r in reviews_list:
                r_date = parse_amazon_date(r.get("date", ""))
                if r_date is None or r_date >= cutoff_date:
                    filtered.append(r)
            reviews_list = filtered
        except Exception as e:
            print(f"Error filtering by time: {e}")
            
    if not reviews_list:
        raise HTTPException(
            status_code=400,
            detail=f"No reviews found in the selected time range (Last {req.time_filter} Days)."
        )

    if len(reviews_list) > 300:
        raise HTTPException(status_code=400, detail="Max 300 reviews per request")

    try:
        pipeline = get_pipeline()
        result = pipeline.run(req.product.dict(), reviews_list, req.aspects or [])
        
        # Cache product data and reviews locally in SQLite database
        save_product_data(
            asin=req.product.asin,
            name=req.product.name,
            domain=req.product.domain,
            url=req.product.url,
            analytics=result,
            reviews=reviews_list
        )
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/html", response_model=AnalyzeResponse)
def analyze_html(req: AnalyzeHtmlRequest):
    if not req.html.strip():
        raise HTTPException(status_code=400, detail="HTML content is empty")

    try:
        parsed = parse_amazon_html(req.html, req.url)
        product = parsed["product"]
        reviews = parsed["reviews"]

        if not reviews:
            raise HTTPException(status_code=400, detail="No reviews found in the HTML content")

        # Filter reviews by date if time_filter is specified
        if req.time_filter and req.time_filter != "all":
            try:
                days_limit = int(req.time_filter)
                cutoff_date = datetime.date.today() - datetime.timedelta(days=days_limit)
                
                filtered = []
                for r in reviews:
                    r_date = parse_amazon_date(r.get("date", ""))
                    if r_date is None or r_date >= cutoff_date:
                        filtered.append(r)
                reviews = filtered
            except Exception as e:
                print(f"Error filtering by time: {e}")
                
        if not reviews:
            raise HTTPException(
                status_code=400,
                detail=f"No reviews found in the selected time range (Last {req.time_filter} Days)."
            )

        # Limit to max 300 reviews
        reviews = reviews[:300]

        pipeline = get_pipeline()
        result = pipeline.run(product, reviews, req.aspects or [])
        
        # Cache product data and reviews locally in SQLite database
        save_product_data(
            asin=product["asin"],
            name=product["name"],
            domain=product["domain"],
            url=product["url"],
            analytics=result,
            reviews=reviews
        )
        
        return result
    except HTTPException:
        raise
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
        f"- Keep your response helpful, professional, and relatively concise (maximum 3 paragraphs).\n"
        f"- Format your response using markdown. Use **bolding** to emphasize features (e.g., **battery life**), performance highlights, and clear verdicts (e.g., **Verdict:** **Yes, buy** or **Verdict:** **No, do not buy**)."
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
                    "model": "llama-3.1-8b-instant",
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
