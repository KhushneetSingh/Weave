import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Weave",
    description="Multi-agent LLM orchestration system — Phase 1 scaffold",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Liveness probe — returns 200 when the API process is running."""
    return {"status": "ok", "version": app.version}
