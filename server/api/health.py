"""Internal health endpoint. Not part of the public interface."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/internal", tags=["internal"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the process is up. Database checks follow with the status endpoint."""
    return HealthResponse(status="ok")
