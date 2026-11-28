"""Internal device registration. Not part of the public interface: the gateway allowlist
must never expose ``/internal`` (reachable via Tailscale or the local network only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from server.api import signing
from server.api.auth import register_device
from server.db.session import get_session

router = APIRouter(prefix="/internal/devices", tags=["internal"])


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=20, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    # Base64 of the 65 byte X9.62 uncompressed P-256 public key.
    public_key: str = Field(min_length=88, max_length=88)

    @field_validator("public_key")
    @classmethod
    def _valid_key(cls, value: str) -> str:
        signing.decode_public_key(value)
        return value


class RegisterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: int = Field(ge=1)


@router.post("/register", response_model=RegisterResponse)
async def register(
    body: RegisterRequest, session: Annotated[AsyncSession, Depends(get_session)]
) -> RegisterResponse:
    device_id = await register_device(
        session,
        code=body.code,
        name=body.name,
        public_key=signing.decode_public_key(body.public_key),
    )
    if device_id is None:
        await session.rollback()
        raise HTTPException(status_code=403, detail="invalid or expired code")
    await session.commit()
    return RegisterResponse(device_id=device_id)
