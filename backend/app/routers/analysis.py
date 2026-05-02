import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import AnalysisRequest, AnalysisResponse
from app.services.nlp_service import analyze_reviews

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(request: AnalysisRequest):
    if not request.reviews:
        raise HTTPException(status_code=422, detail="No reviews provided")

    if len(request.reviews) > 500:
        raise HTTPException(status_code=422, detail="Too many reviews (max 500)")

    try:
        raw = [r.model_dump() for r in request.reviews]
        result = analyze_reviews(raw)

        return AnalysisResponse(
            product_title=request.product_title,
            total_reviews=len(request.reviews),
            **result,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=500, detail="Internal analysis error")
