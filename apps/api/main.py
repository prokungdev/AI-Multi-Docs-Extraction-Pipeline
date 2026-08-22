import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is available in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from apps.api.routers import health

app = FastAPI(
    title="AI Multi-Docs Extraction Pipeline REST API",
    description="RESTful API Backend for Document Extraction Pipeline, supporting Next.js Web & Mobile clients.",
    version="1.0.0",
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


@app.get("/", tags=["Root"])
def root_endpoint():
    """
    Root endpoint returning service identity and API documentation link.
    """
    return {
        "service": "AI Multi-Docs Extraction Pipeline REST API",
        "status": "online",
        "docs_url": "/docs",
        "health_check": "/api/v1/health"
    }
