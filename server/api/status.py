"""Internal status endpoint. Not part of the public interface (reachable via Tailscale only)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import get_settings
from server.db.session import get_session
from server.monitoring.status import StatusReport, collect_status

router = APIRouter(prefix="/internal", tags=["internal"])


class SourceStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str = Field(max_length=100)
    online: bool
    last_sync: datetime | None
    expected_interval_seconds: int = Field(ge=1)
    # Technical error text of the last failed run (no payload content).
    last_error: str | None = Field(max_length=500)


class StatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    sources: list[SourceStatusResponse]
    queue_length: int = Field(ge=0)
    error_queue_length: int = Field(ge=0)
    last_backup: datetime | None


async def get_status_report(session: Annotated[AsyncSession, Depends(get_session)]) -> StatusReport:
    settings = get_settings()
    return await collect_status(
        session,
        user_id=settings.vanta_user_id,
        backup_marker_path=settings.vanta_backup_marker_path,
    )


@router.get("/status", response_model=StatusResponse)
async def status(report: Annotated[StatusReport, Depends(get_status_report)]) -> StatusResponse:
    """Sources online/offline, last sync, queue lengths and last backup."""
    return StatusResponse(
        generated_at=report.generated_at,
        sources=[
            SourceStatusResponse(
                source_key=s.source_key,
                online=s.online,
                last_sync=s.last_sync,
                expected_interval_seconds=s.expected_interval_seconds,
                last_error=s.last_error,
            )
            for s in report.sources
        ],
        queue_length=report.queue_length,
        error_queue_length=report.error_queue_length,
        last_backup=report.last_backup,
    )
