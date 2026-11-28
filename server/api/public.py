"""Public endpoints (reachable through the tunnel). Every one requires a signed request."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from server.api.auth import AuthenticatedDevice, require_device

router = APIRouter(prefix="/v1", tags=["public"])


class PingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


@router.get("/ping", response_model=PingResponse)
async def ping(_device: Annotated[AuthenticatedDevice, Depends(require_device)]) -> PingResponse:
    """Lets the app check that registration and signing work."""
    return PingResponse(status="ok")
