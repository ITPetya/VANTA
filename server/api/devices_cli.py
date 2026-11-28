"""Server commands for device management.

python -m server.api.devices_cli create-code
python -m server.api.devices_cli list
python -m server.api.devices_cli revoke <device_id>
"""

import argparse
import asyncio

from sqlalchemy import select

from server.api.auth import create_registration_code, revoke_device
from server.config import get_settings
from server.db.models import Device
from server.db.session import get_session_factory


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    async with get_session_factory()() as session:
        if args.command == "create-code":
            code = await create_registration_code(
                session,
                user_id=settings.vanta_user_id,
                ttl_seconds=settings.vanta_registration_code_ttl_seconds,
            )
            await session.commit()
            minutes = settings.vanta_registration_code_ttl_seconds // 60
            print(f"Registrierungscode (einmalig, {minutes} Minuten gültig): {code}")
        elif args.command == "list":
            rows = await session.scalars(
                select(Device).where(Device.user_id == settings.vanta_user_id).order_by(Device.id)
            )
            for d in rows:
                state = "gesperrt" if d.revoked else "aktiv"
                print(f"{d.id}\t{d.name}\t{state}\t{d.last_seen_at}")
        else:
            ok = await revoke_device(
                session, user_id=settings.vanta_user_id, device_id=args.device_id
            )
            await session.commit()
            print("gesperrt" if ok else "Gerät nicht gefunden")
            return 0 if ok else 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m server.api.devices_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create-code")
    sub.add_parser("list")
    revoke = sub.add_parser("revoke")
    revoke.add_argument("device_id", type=int)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
