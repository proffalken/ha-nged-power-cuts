"""Tests for the NGED Connected Data client."""

import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.nged_power_cuts.api import NGEDApiClient, NGEDError
from custom_components.nged_power_cuts.const import API_URL, RESOURCE_ID
from tests.conftest import api_response, live_records


def _params(offset: int, limit: int = 1000) -> dict[str, str]:
    return {"resource_id": RESOURCE_ID, "limit": str(limit), "offset": str(offset)}


@pytest.fixture
async def client(hass, aioclient_mock) -> NGEDApiClient:
    return NGEDApiClient(async_get_clientsession(hass))


async def test_get_power_cuts(client, aioclient_mock) -> None:
    aioclient_mock.get(API_URL, params=_params(0), json=api_response(live_records()))

    cuts = await client.async_get_power_cuts()

    assert len(cuts) == 13
    assert aioclient_mock.call_count == 1


async def test_pages_through_a_big_feed(client, aioclient_mock) -> None:
    records = live_records()
    client = NGEDApiClient(client._session, page_size=5)
    for offset in (0, 5, 10):
        aioclient_mock.get(
            API_URL,
            params=_params(offset, 5),
            json=api_response(records[offset : offset + 5], total=13),
        )

    cuts = await client.async_get_power_cuts()

    assert [c.id for c in cuts] == [r["fault_id"] for r in records]
    assert aioclient_mock.call_count == 3


async def test_an_incomplete_feed_is_an_error(client, aioclient_mock) -> None:
    # A partial list would make the missing cuts look restored.
    client = NGEDApiClient(client._session, page_size=5)
    aioclient_mock.get(
        API_URL, params=_params(0, 5), json=api_response(live_records()[:5], total=99)
    )
    aioclient_mock.get(API_URL, params=_params(5, 5), json=api_response([], total=99))

    with pytest.raises(NGEDError):
        await client.async_get_power_cuts()


async def test_too_many_pages_is_an_error(client, aioclient_mock) -> None:
    client = NGEDApiClient(client._session, page_size=1)
    aioclient_mock.get(API_URL, json=api_response(live_records()[:1], total=10_000))

    with pytest.raises(NGEDError):
        await client.async_get_power_cuts()


@pytest.mark.parametrize(
    "mock",
    [
        {"status": 500},
        {"text": "not json"},
        {"json": {"success": False, "error": {"message": "Not found"}}},
        {"json": {"success": True, "result": {}}},
        {"exc": aiohttp.ClientError("boom")},
        {"exc": TimeoutError()},
    ],
)
async def test_errors(client, aioclient_mock, mock) -> None:
    aioclient_mock.get(API_URL, params=_params(0), **mock)

    with pytest.raises(NGEDError):
        await client.async_get_power_cuts()
