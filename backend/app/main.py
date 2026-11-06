from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db import Base, engine
from app.routers.auth import router as auth_router
from app.routers.prediction import router as prediction_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    settings.validate()
    settings.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (settings.UPLOAD_DIR / "heatmaps").mkdir(parents=True, exist_ok=True)
    if settings.AUTO_CREATE_TABLES:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    lifespan=lifespan,
    # The interactive docs advertise every endpoint; useful locally, not
    # something a production clinical API should publish.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# Auth is a bearer header, not cookies, so credentials mode is not needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    # API responses carry patient data; nothing should be cached by default.
    response.headers.setdefault("Cache-Control", "no-store")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

# No static mount for UPLOAD_DIR: patient photos and heatmaps are served only
# through the authenticated, owner-checked /predictions/{id}/image|heatmap.

app.include_router(auth_router)
app.include_router(prediction_router)


@app.get("/")
def health():
    return {"status": "healthy", "version": settings.API_VERSION}


@app.get("/health")
def health_check():
    return {"status": "healthy", "version": settings.API_VERSION}
