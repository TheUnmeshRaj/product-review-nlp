from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import analysis

app = FastAPI(
    title="ReviewLens NLP API",
    version="1.0.0",
    description="Sentiment analysis and aspect extraction for product reviews",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to extension origin in production
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(analysis.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
