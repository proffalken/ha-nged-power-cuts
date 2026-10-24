"""Turn NGED's lists of postcodes into place names people recognise.

NGED lists the postcodes affected by each power cut, but no place names.
postcodes.io (free, no key, open data from the ONS) says which parish and
council each postcode is in. Only the postcodes of power cuts are sent to
it, plus your own postcode once, during setup, to find where it is.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import aiohttp

POSTCODES_IO = "https://api.postcodes.io"
BULK_URL = f"{POSTCODES_IO}/postcodes"
POSTCODE_URL = f"{POSTCODES_IO}/postcodes/{{postcode}}"
BATCH_SIZE = 100  # postcodes.io's limit for one bulk lookup
MAX_NAMES = 3

_TIMEOUT = aiohttp.ClientTimeout(total=20)
# ONS names some councils "Herefordshire, County of" or "Bristol, City of".
_DISTRICT_SUFFIX = re.compile(r",\s*(County|City) of$")


class PostcodesError(Exception):
    """Raised when postcodes.io can't be reached or returns bad data."""


@dataclass(frozen=True, slots=True)
class Place:
    """Where a postcode is: its parish (or ward) and its council."""

    name: str
    district: str | None


def place_from_result(result: dict[str, Any] | None) -> Place | None:
    """A Place from one postcodes.io result, or None if it has no name."""
    if not result:
        return None
    parish = result.get("parish") or ""
    name = result.get("admin_ward") if not parish or "unparished" in parish else parish
    if not name:
        return None
    district = result.get("admin_district")
    if district:
        district = _DISTRICT_SUFFIX.sub("", district)
    return Place(name, district or None)


def postcode_sectors(postcodes: Iterable[str]) -> list[str]:
    """The postcode sectors ("GL16 8") a list of full postcodes falls in."""
    return sorted({pc[:-2] for pc in postcodes if len(pc) > 2})


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def describe_places(places: Iterable[Place | None]) -> str | None:
    """A short description such as "Coleford and Goodrich (Forest of Dean)".

    Places with the most affected postcodes come first.
    """
    counts = Counter(p for p in places if p is not None)
    if not counts:
        return None
    ordered = [p for p, _ in sorted(counts.items(), key=lambda i: (-i[1], i[0].name))]
    names = list(dict.fromkeys(p.name for p in ordered))
    shown = names[:MAX_NAMES]
    text = _join(shown)
    if len(names) > MAX_NAMES:
        more = len(names) - MAX_NAMES
        text = f"{', '.join(shown)} and {more} more place{'' if more == 1 else 's'}"
    districts = [d for d in dict.fromkeys(p.district for p in ordered) if d]
    if districts and districts != shown:
        text = f"{text} ({', '.join(districts)})"
    return text


class PostcodesClient:
    """Looks postcodes up on postcodes.io."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_lookup(self, postcodes: Iterable[str]) -> dict[str, Place | None]:
        """Where each postcode is. Unknown postcodes map to None."""
        wanted = list(dict.fromkeys(postcodes))
        places: dict[str, Place | None] = {}
        for start in range(0, len(wanted), BATCH_SIZE):
            batch = wanted[start : start + BATCH_SIZE]
            body = await self._request("post", BULK_URL, json={"postcodes": batch})
            found = {
                item["query"]: place_from_result(item.get("result"))
                for item in body.get("result") or []
                if isinstance(item, dict) and item.get("query")
            }
            # A missing answer isn't "unknown postcode"; ask again next time.
            if missing := set(batch) - found.keys():
                raise PostcodesError(
                    f"postcodes.io left out {len(missing)} of {len(batch)} postcodes"
                )
            places.update(found)
        return places

    async def async_locate(self, postcode: str) -> tuple[float, float] | None:
        """The latitude and longitude of a postcode, or None if it's unknown."""
        url = POSTCODE_URL.format(postcode=postcode.replace(" ", ""))
        body = await self._request("get", url, missing_ok=True)
        result = body.get("result") or {}
        lat, lon = result.get("latitude"), result.get("longitude")
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)

    async def _request(
        self, method: str, url: str, missing_ok: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        try:
            async with self._session.request(
                method, url, timeout=_TIMEOUT, **kwargs
            ) as response:
                if missing_ok and response.status == 404:
                    return {}
                response.raise_for_status()
                body = await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise PostcodesError(f"postcodes.io lookup failed: {err}") from err
        if not isinstance(body, dict):
            raise PostcodesError("postcodes.io returned an unexpected response")
        return body
