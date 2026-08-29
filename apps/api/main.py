import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is available in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from apps.api.routers import health, companies
from src.infrastructure.core.config import get_app_metadata

app_meta = get_app_metadata()

app = FastAPI(
    title=f"{app_meta['app_name']} REST API",
    description=app_meta["app_description"],
    version=app_meta["app_version"],
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for future Next.js web and mobile applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(companies.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
def root_endpoint():
    """
    Root endpoint returning service identity and API documentation link.
    """
    return {
        "service": f"{app_meta['app_name']} REST API",
        "version": app_meta["app_version"],
        "status": "online",
        "docs_url": "/docs",
        "health_check": "/api/v1/health"
    }
