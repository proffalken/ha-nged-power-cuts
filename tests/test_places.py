"""Tests for turning NGED's postcode lists into place names."""

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.nged_power_cuts.places import (
    BULK_URL,
    POSTCODE_URL,
    Place,
    PostcodesClient,
    PostcodesError,
    describe_places,
    place_from_result,
    postcode_sectors,
)
from tests.conftest import load_fixture

COLEFORD = Place("Coleford", "Forest of Dean")
GOODRICH = Place("Goodrich", "Herefordshire")


def test_place_uses_the_parish_and_tidies_the_district() -> None:
    result = load_fixture("postcodes_bulk.json")["result"][3]["result"]

    assert place_from_result(result) == GOODRICH


def test_place_falls_back_to_the_ward_without_a_parish() -> None:
    result = {"parish": None, "admin_ward": "Town", "admin_district": "Monmouthshire"}

    assert place_from_result(result) == Place("Town", "Monmouthshire")


def test_unparished_areas_use_the_ward() -> None:
    result = {
        "parish": "Bristol, unparished area",
        "admin_ward": "Frome Vale",
        "admin_district": "Bristol, City of",
    }

    assert place_from_result(result) == Place("Frome Vale", "Bristol")


def test_no_result_is_no_place() -> None:
    assert place_from_result(None) is None
    assert place_from_result({"admin_district": "Cardiff"}) is None


def test_postcode_sectors() -> None:
    assert postcode_sectors(["GL16 8AA", "GL16 7JG", "GL16 8QA", "HR9 6JL"]) == [
        "GL16 7",
        "GL16 8",
        "HR9 6",
    ]


@pytest.mark.parametrize(
    ("places", "expected"),
    [
        ([], None),
        ([None, None], None),
        ([COLEFORD, COLEFORD], "Coleford (Forest of Dean)"),
        (
            [COLEFORD, GOODRICH, COLEFORD],
            "Coleford and Goodrich (Forest of Dean, Herefordshire)",
        ),
        (
            [Place("A", "D"), Place("B", "D"), Place("C", "D")],
            "A, B and C (D)",
        ),
        (
            [Place(n, "D") for n in "AABCDE"],
            "A, B, C and 2 more places (D)",
        ),
        ([Place("Cardiff", "Cardiff")], "Cardiff"),
    ],
)
def test_describe_places(places, expected) -> None:
    assert describe_places(places) == expected


async def test_bulk_lookup(hass, aioclient_mock) -> None:
    aioclient_mock.post(BULK_URL, json=load_fixture("postcodes_bulk.json"))
    client = PostcodesClient(async_get_clientsession(hass))

    places = await client.async_lookup(["GL16 8AA", "HR9 6JL", "ZZ1 1ZZ"])

    assert places["GL16 8AA"] == COLEFORD
    assert places["HR9 6JL"] == GOODRICH
    assert places["ZZ1 1ZZ"] is None


async def test_bulk_lookup_splits_into_batches_of_100(hass, aioclient_mock) -> None:
    aioclient_mock.post(BULK_URL, json={"status": 200, "result": []})
    client = PostcodesClient(async_get_clientsession(hass))

    await client.async_lookup([f"GL{i} 1AA" for i in range(250)])

    assert aioclient_mock.call_count == 3


async def test_nothing_to_look_up_makes_no_request(hass, aioclient_mock) -> None:
    client = PostcodesClient(async_get_clientsession(hass))

    assert await client.async_lookup([]) == {}
    assert aioclient_mock.call_count == 0


async def test_lookup_errors_raise(hass, aioclient_mock) -> None:
    aioclient_mock.post(BULK_URL, status=500)
    client = PostcodesClient(async_get_clientsession(hass))

    with pytest.raises(PostcodesError):
        await client.async_lookup(["GL16 8AA"])


async def test_locate_a_postcode(hass, aioclient_mock) -> None:
    aioclient_mock.get(
        POSTCODE_URL.format(postcode="HR96JL"),
        json=load_fixture("postcode_single.json"),
    )
    client = PostcodesClient(async_get_clientsession(hass))

    assert await client.async_locate("HR9 6JL") == pytest.approx(
        (51.8403, -2.6383), abs=1e-3
    )


async def test_locate_an_unknown_postcode(hass, aioclient_mock) -> None:
    aioclient_mock.get(POSTCODE_URL.format(postcode="ZZ11ZZ"), status=404)
    client = PostcodesClient(async_get_clientsession(hass))

    assert await client.async_locate("ZZ1 1ZZ") is None
