"""Optional push to Uptime Kuma, one push monitor per source.

The push URLs contain a secret token: they come from .env and are never logged.
The message only carries the technical source name and the state, no user data.
A failing push never breaks the server; it is logged without the URL.
"""

import logging

import httpx

from server.monitoring.status import SourceStatus

logger = logging.getLogger(__name__)

PUSH_TIMEOUT_SECONDS = 10.0


async def push_source(client: httpx.AsyncClient, url: str, source: SourceStatus) -> bool:
    """Push one source state. Returns True if Kuma accepted it."""
    params = {
        "status": "up" if source.online else "down",
        "msg": "OK" if source.online else "silent or failing",
    }
    try:
        response = await client.get(url, params=params, timeout=PUSH_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Kuma push for source %s failed: %s", source.source_key, type(exc).__name__)
        return False
    return True


async def push_all(
    client: httpx.AsyncClient, urls: dict[str, str], sources: list[SourceStatus]
) -> dict[str, bool]:
    """Push every source that has a configured URL. Sources without URL are skipped."""
    results: dict[str, bool] = {}
    for source in sources:
        url = urls.get(source.source_key)
        if url:
            results[source.source_key] = await push_source(client, url, source)
    return results
