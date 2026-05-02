"""
NLP Service
- Sentiment: cardiffnlp/twitter-roberta-base-sentiment-latest (fast, accurate)
- Aspects: keyword-based extraction + zero-shot classification fallback
- Keywords: KeyBERT / YAKE
Lazy-loads models on first call; stays warm for subsequent requests.
"""
import re
import logging
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy model loading ─────────────────────────────────────────────────────────

_sentiment_pipeline = None
_keyword_model = None


def get_sentiment_pipeline():
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        from transformers import pipeline
        logger.info("Loading sentiment model…")
        _sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model="cardiffnlp/twitter-roberta-base-sentiment-latest",
            top_k=None,
            truncation=True,
            max_length=512,
        )
        logger.info("Sentiment model loaded.")
    return _sentiment_pipeline


def get_keyword_model():
    global _keyword_model
    if _keyword_model is None:
        try:
            from keybert import KeyBERT
            _keyword_model = KeyBERT()
            logger.info("KeyBERT loaded.")
        except ImportError:
            logger.warning("KeyBERT not installed, falling back to YAKE")
            _keyword_model = "yake"
    return _keyword_model


# ── Aspect lexicon ─────────────────────────────────────────────────────────────

ASPECT_KEYWORDS = {
    "battery":     ["battery", "charge", "charging", "power", "drain", "backup", "mah"],
    "camera":      ["camera", "photo", "picture", "image", "selfie", "lens", "megapixel", "mp"],
    "display":     ["display", "screen", "brightness", "resolution", "amoled", "lcd", "nits"],
    "performance": ["performance", "speed", "fast", "lag", "slow", "processor", "chip", "ram", "smooth"],
    "build":       ["build", "quality", "design", "plastic", "metal", "glass", "premium", "feel", "grip"],
    "software":    ["software", "ui", "interface", "android", "update", "bloatware", "app", "os"],
    "audio":       ["speaker", "audio", "sound", "volume", "bass", "earphone", "jack", "noise"],
    "price":       ["price", "value", "worth", "expensive", "cheap", "budget", "cost", "money"],
    "heating":     ["heat", "heating", "hot", "warm", "temperature", "overheat"],
    "delivery":    ["delivery", "shipping", "package", "arrived", "box", "packaging"],
}


def detect_aspects(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for aspect, keywords in ASPECT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(aspect)
    return found


# ── Sentiment classification ───────────────────────────────────────────────────

LABEL_MAP = {
    "positive": "positive",
    "label_2":  "positive",
    "neutral":  "neutral",
    "label_1":  "neutral",
    "negative": "negative",
    "label_0":  "negative",
}


def classify_sentiment(text: str, pipeline) -> tuple[str, float]:
    """Returns (label, confidence)"""
    try:
        results = pipeline(text[:512])[0]  # list of {label, score}
        best = max(results, key=lambda x: x["score"])
        label = LABEL_MAP.get(best["label"].lower(), "neutral")
        return label, round(best["score"], 4)
    except Exception as e:
        logger.error(f"Sentiment error: {e}")
        return "neutral", 0.5


def rating_to_sentiment(rating: float) -> str:
    if rating >= 4:
        return "positive"
    elif rating >= 3:
        return "neutral"
    return "negative"


def blend_sentiment(model_label: str, model_conf: float, rating: float):
    """Blend model output with star rating for higher accuracy."""
    rating_label = rating_to_sentiment(rating)
    # If model is confident (>0.8) or rating is ambiguous (3), trust model
    if model_conf >= 0.78 or rating == 3:
        return model_label, model_conf
    # Otherwise blend: if both agree, keep; if not, lean toward rating
    if model_label == rating_label:
        return model_label, min(model_conf + 0.1, 1.0)
    return rating_label, 0.65


# ── Keyword extraction ─────────────────────────────────────────────────────────

def extract_keywords(texts: list[str], top_n: int = 20) -> list[str]:
    combined = " ".join(texts)
    model = get_keyword_model()

    if model == "yake":
        import yake
        extractor = yake.KeywordExtractor(lan="en", n=2, top=top_n)
        kws = extractor.extract_keywords(combined)
        return [kw for kw, _ in kws]

    try:
        kws = model.extract_keywords(
            combined,
            keyphrase_ngram_range=(1, 2),
            stop_words="english",
            top_n=top_n,
        )
        return [kw for kw, _ in kws]
    except Exception:
        # Simple fallback: frequency
        words = re.findall(r'\b[a-z]{4,}\b', combined.lower())
        stopwords = {"this", "that", "with", "have", "from", "they", "been", "very", "good", "great", "nice"}
        filtered = [w for w in words if w not in stopwords]
        return [w for w, _ in Counter(filtered).most_common(top_n)]


# ── Trend calculation ──────────────────────────────────────────────────────────

def parse_period(date_str: str) -> Optional[str]:
    """Try to parse review date into 'Mon YYYY' format."""
    patterns = [
        "%B %d, %Y",       # January 15, 2024
        "%d %B %Y",        # 15 January 2024
        "%Y-%m-%d",
        "%d/%m/%Y",
        "Reviewed in %s on %B %d, %Y",
    ]
    # Extract just the date portion if it contains 'Reviewed in'
    match = re.search(r'(\w+ \d+, \d{4})', date_str)
    if match:
        date_str = match.group(1)

    for fmt in patterns:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%b %Y")
        except ValueError:
            continue
    return None


def compute_trends(reviews_with_sentiment: list[dict]) -> list[dict]:
    period_data: dict[str, dict] = defaultdict(
        lambda: {"positive": 0, "neutral": 0, "negative": 0, "ratings": []}
    )

    for r in reviews_with_sentiment:
        period = parse_period(r.get("date", "")) or "Unknown"
        period_data[period][r["sentiment"]] += 1
        if r["rating"] > 0:
            period_data[period]["ratings"].append(r["rating"])

    trends = []
    for period, data in sorted(period_data.items(), key=lambda x: x[0]):
        avg_rating = (
            round(sum(data["ratings"]) / len(data["ratings"]), 2)
            if data["ratings"]
            else 0.0
        )
        trends.append({
            "period": period,
            "positive": data["positive"],
            "neutral": data["neutral"],
            "negative": data["negative"],
            "avg_rating": avg_rating,
        })

    return trends[-12:]  # last 12 periods


# ── Insight generation ─────────────────────────────────────────────────────────

def generate_insights(
    aspect_sentiment: dict[str, dict],
    top_keywords: list[str],
) -> list[dict]:
    insights = []

    for aspect, counts in aspect_sentiment.items():
        total = counts["positive"] + counts["neutral"] + counts["negative"]
        if total < 2:
            continue
        pos_ratio = counts["positive"] / total
        neg_ratio = counts["negative"] / total

        if pos_ratio >= 0.7:
            insights.append({
                "type": "praise",
                "text": f"Buyers consistently praise the {aspect} — {int(pos_ratio*100)}% positive mentions",
                "count": counts["positive"],
            })
        elif neg_ratio >= 0.5:
            insights.append({
                "type": "complaint",
                "text": f"Common complaint: {aspect} — {int(neg_ratio*100)}% negative mentions",
                "count": counts["negative"],
            })

    insights.sort(key=lambda x: x["count"], reverse=True)
    return insights[:6]


# ── Main analysis entry point ──────────────────────────────────────────────────

def analyze_reviews(raw_reviews: list[dict]) -> dict:
    if not raw_reviews:
        raise ValueError("No reviews provided")

    pipeline = get_sentiment_pipeline()

    processed = []
    aspect_counts: dict[str, dict] = defaultdict(
        lambda: {"positive": 0, "neutral": 0, "negative": 0}
    )
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}

    for r in raw_reviews:
        text = r["text"]
        rating = r.get("rating", 0)

        raw_label, conf = classify_sentiment(text, pipeline)
        label, conf = blend_sentiment(raw_label, conf, rating)

        sentiment_dist[label] += 1

        aspects = detect_aspects(text)
        aspect_sentiments = {}
        for aspect in aspects:
            aspect_counts[aspect][label] += 1
            aspect_sentiments[aspect] = label

        keywords = extract_keywords([text], top_n=5)

        processed.append({
            **r,
            "sentiment": label,
            "sentiment_score": conf,
            "aspects": aspect_sentiments,
            "keywords": keywords,
        })

    # Build aspect_sentiment list
    aspect_sentiment_list = []
    for aspect, counts in aspect_counts.items():
        total = sum(counts.values())
        net_score = (counts["positive"] - counts["negative"]) / total if total else 0
        aspect_sentiment_list.append({
            "aspect": aspect,
            **counts,
            "score": round(net_score, 3),
        })
    aspect_sentiment_list.sort(key=lambda x: sum([x["positive"], x["neutral"], x["negative"]]), reverse=True)

    # Keywords across all reviews
    all_texts = [r["text"] for r in raw_reviews]
    top_keywords = extract_keywords(all_texts, top_n=15)

    trends = compute_trends(processed)
    insights = generate_insights(aspect_counts, top_keywords)

    return {
        "sentiment_distribution": sentiment_dist,
        "aspect_sentiment": aspect_sentiment_list,
        "trends": trends,
        "insights": insights,
        "top_keywords": top_keywords,
        "reviews": processed,
    }
