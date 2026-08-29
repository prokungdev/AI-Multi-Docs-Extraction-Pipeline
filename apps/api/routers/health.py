import os
import sys
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

# Ensure project root is available in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.infrastructure.core.healthcheck import run_healthcheck

router = APIRouter(
    prefix="/health",
    tags=["Health & Status"]
)


class HealthResponse(BaseModel):
    healthy: bool = Field(..., description="System health status indicator")
    status: str = Field(..., description="Summary status message")
    checks: dict = Field(default_factory=dict, description="Detailed subsystem health checks")
    remedies: list[str] = Field(default_factory=list, description="Actionable recovery steps if unhealthy")


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="System Health & Readiness Check",
    description="Inspects database connection, tables, and AI credentials readiness."
)
def get_health_status() -> dict:
    """
    Executes core health checks and returns current system status.
    """
    results = run_healthcheck()
    return results
