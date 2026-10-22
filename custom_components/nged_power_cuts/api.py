"""Async client for NGED's live power cut data on Connected Data (CKAN)."""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from .const import API_URL, MAX_PAGES, PAGE_SIZE, RESOURCE_ID
from .models import PowerCut, parse_power_cuts

_TIMEOUT = aiohttp.ClientTimeout(total=60)


class NGEDError(Exception):
    """Raised when the feed can't be reached, errors, or returns bad data."""


class NGEDApiClient:
    """Reads NGED's Live Detailed Power Cuts table. No key is needed."""

    def __init__(
        self, session: aiohttp.ClientSession, page_size: int = PAGE_SIZE
    ) -> None:
        self._session = session
        self._page_size = page_size

    async def async_get_power_cuts(self) -> list[PowerCut]:
        """Every power cut in the feed, across all four licence areas."""
        records: list[Any] = []
        for page in range(MAX_PAGES):
            result = await self._get_page(page * self._page_size)
            batch = result["records"]
            records.extend(batch)
            if not batch or len(records) >= result.get("total", 0):
                break
        return parse_power_cuts(records)

    async def _get_page(self, offset: int) -> dict[str, Any]:
        params = {
            "resource_id": RESOURCE_ID,
            "limit": str(self._page_size),
            "offset": str(offset),
        }
        try:
            async with self._session.get(
                API_URL, params=params, timeout=_TIMEOUT
            ) as response:
                if response.status >= 400:
                    raise NGEDError(f"Unexpected status {response.status} from NGED")
                text = await response.text()
        except NGEDError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            raise NGEDError(f"Error connecting to NGED: {err}") from err

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as err:
            raise NGEDError(f"Bad JSON from NGED: {err}") from err
        if not isinstance(payload, dict) or not payload.get("success"):
            error = payload.get("error") if isinstance(payload, dict) else payload
            raise NGEDError(f"NGED returned an error: {error}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise NGEDError("NGED returned no result")
        if not isinstance(result.get("records"), list):
            raise NGEDError("NGED returned no records list")
        return result
