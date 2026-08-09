import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, fitbot, intelligence, knowledge, membership, people
from app.core.config import get_settings
from app.db import initialize_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mastergym")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    logger.info("%s API ready (model=%s)", settings.app_name, settings.gemini_model)
    yield


app = FastAPI(
    title=f"{settings.app_name} API",
    version="0.2.0",
    description=f"Backend for {settings.app_name} and its assistant {settings.bot_name}.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Never leak a stack trace to the browser; the log keeps the detail."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. Please try again."},
    )


app.include_router(auth.router, prefix="/api")
app.include_router(membership.router, prefix="/api")
app.include_router(people.router, prefix="/api")
app.include_router(fitbot.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(intelligence.router, prefix="/api")


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "app": settings.app_name, "bot": settings.bot_name}
