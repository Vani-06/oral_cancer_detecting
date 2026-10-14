from contextlib import asynccontextmanager

from fastapi import FastAPI
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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
