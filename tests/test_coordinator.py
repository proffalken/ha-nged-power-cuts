"""Tests for the NGED Power Cuts data update coordinator."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.nged_power_cuts.api import NGEDError
from custom_components.nged_power_cuts.const import EVENT_POWER_CUT_CHANGED
from custom_components.nged_power_cuts.coordinator import PowerCutsCoordinator
from custom_components.nged_power_cuts.models import parse_power_cuts
from custom_components.nged_power_cuts.places import Place, PostcodesError
from tests.conftest import LAT, LON, POSTCODE, live_records

NOW = "2026-10-22T21:30:00+00:00"


def fault(fault_id="NEW", **changes) -> dict:
    """A real unplanned fault from the feed, moved to the test home."""
    base = next(r for r in live_records() if r["fault_id"] == "INCD-109435-l")
    base.update(fault_id=fault_id, postcode=f"{POSTCODE}, CF10 4RQ")
    base.update(location_latitude=LAT, location_longitude=LON)
    base.update(changes)
    return base


def _client(*polls: list[dict]) -> AsyncMock:
    client = AsyncMock()
    client.async_get_power_cuts.side_effect = [parse_power_cuts(p) for p in polls]
    return client


def _coordinator(hass, entry, client) -> PowerCutsCoordinator:
    return PowerCutsCoordinator(
        hass, entry, client, POSTCODE, LAT, LON, 5, places_client=_places_client()
    )


@pytest.fixture(autouse=True)
def frozen_now(freezer) -> None:
    freezer.move_to(NOW)


async def test_summarises_the_feed(hass, mock_config_entry) -> None:
    coordinator = _coordinator(hass, mock_config_entry, _client(live_records()))

    data = await coordinator._async_update_data()

    assert [c.id for c in data.yours] == ["INCD-7034-j"]
    assert data.total == 13


async def test_errors_become_update_failed(hass, mock_config_entry) -> None:
    client = AsyncMock()
    client.async_get_power_cuts.side_effect = NGEDError("down")
    coordinator = _coordinator(hass, mock_config_entry, client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_events_for_new_updated_and_restored(hass, mock_config_entry) -> None:
    events = async_capture_events(hass, EVENT_POWER_CUT_CHANGED)
    client = _client(
        live_records(),
        [*live_records(), fault()],
        [*live_records(), fault(etr="2026-10-23T03:00:00")],
        live_records(),
    )
    coordinator = _coordinator(hass, mock_config_entry, client)

    for _ in range(4):
        await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert [(e.data["change"], e.data["id"]) for e in events] == [
        ("new", "NEW"),
        ("updated", "NEW"),
        ("restored", "NEW"),
    ]
    first = events[0].data
    assert first["config_entry_id"] == mock_config_entry.entry_id
    assert first["affects_you"] is True
    assert first["distance_km"] == 0.0
    assert first["estimated_restoration"] == "2026-10-22T23:00:00+00:00"
    assert events[1].data["estimated_restoration"] == "2026-10-23T02:00:00+00:00"


async def test_no_events_on_first_poll(hass, mock_config_entry) -> None:
    events = async_capture_events(hass, EVENT_POWER_CUT_CHANGED)
    coordinator = _coordinator(
        hass, mock_config_entry, _client([*live_records(), fault()])
    )

    await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert events == []


async def test_no_events_for_cuts_elsewhere(hass, mock_config_entry) -> None:
    events = async_capture_events(hass, EVENT_POWER_CUT_CHANGED)
    elsewhere = next(r for r in live_records() if r["fault_id"] == "INCD-109435-l")
    client = _client([], [elsewhere])
    coordinator = _coordinator(hass, mock_config_entry, client)

    await coordinator._async_update_data()
    await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert events == []


async def test_event_when_planned_work_starts(hass, mock_config_entry, freezer) -> None:
    events = async_capture_events(hass, EVENT_POWER_CUT_CHANGED)
    planned = fault(
        fault_id="PLANNED",
        planned="true",
        category="LV PLANNED",
        etr=None,
        planned_outage_start_date="2026-10-23T09:00:00",
        planned_outage_end_date="2026-10-23T15:00:00",
    )
    coordinator = _coordinator(
        hass, mock_config_entry, _client([], [planned], [planned])
    )

    await coordinator._async_update_data()
    data = await coordinator._async_update_data()
    assert data.yours == []
    freezer.move_to("2026-10-23T08:05:00+00:00")
    data = await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert [c.id for c in data.yours] == ["PLANNED"]
    assert [e.data["change"] for e in events] == ["new", "started"]


def _places_client(places=None, error=None) -> AsyncMock:
    client = AsyncMock()
    if error:
        client.async_lookup.side_effect = error
    else:
        client.async_lookup.return_value = places or {}
    return client


async def test_events_name_the_location_and_places(hass, mock_config_entry) -> None:
    events = async_capture_events(hass, EVENT_POWER_CUT_CHANGED)
    places = _places_client(
        {
            POSTCODE: Place("Butetown", "Cardiff"),
            "CF10 4RQ": Place("Butetown", "Cardiff"),
        }
    )
    coordinator = PowerCutsCoordinator(
        hass,
        mock_config_entry,
        _client(live_records(), [*live_records(), fault()]),
        POSTCODE,
        LAT,
        LON,
        5,
        places_client=places,
    )

    await coordinator._async_update_data()
    await coordinator._async_update_data()
    await hass.async_block_till_done()

    (event,) = events
    assert event.data["location"] == mock_config_entry.title
    assert event.data["places"] == ["Butetown"]
    assert event.data["place_summary"] == "Butetown (Cardiff)"
    assert event.data["postcode_sectors"] == ["CF10 4"]
    assert event.data["customers_off"] == 107


async def test_places_are_looked_up_once(hass, mock_config_entry) -> None:
    places = _places_client({POSTCODE: Place("Butetown", "Cardiff")})
    coordinator = PowerCutsCoordinator(
        hass,
        mock_config_entry,
        _client([fault()], [fault()]),
        POSTCODE,
        LAT,
        LON,
        5,
        places_client=places,
    )

    await coordinator._async_update_data()
    await coordinator._async_update_data()

    assert places.async_lookup.await_count == 1
    (looked_up,) = places.async_lookup.await_args.args
    assert sorted(looked_up) == [POSTCODE, "CF10 4RQ"]


async def test_place_lookup_failures_still_notify(hass, mock_config_entry) -> None:
    events = async_capture_events(hass, EVENT_POWER_CUT_CHANGED)
    coordinator = PowerCutsCoordinator(
        hass,
        mock_config_entry,
        _client([], [fault()]),
        POSTCODE,
        LAT,
        LON,
        5,
        places_client=_places_client(error=PostcodesError("down")),
    )

    await coordinator._async_update_data()
    await coordinator._async_update_data()
    await hass.async_block_till_done()

    (event,) = events
    assert event.data["places"] == []
    assert event.data["place_summary"] is None
    assert event.data["postcode_sectors"] == ["CF10 4"]


async def test_describe_adds_places_for_attributes(hass, mock_config_entry) -> None:
    coordinator = PowerCutsCoordinator(
        hass,
        mock_config_entry,
        _client([fault()]),
        POSTCODE,
        LAT,
        LON,
        5,
        places_client=_places_client({POSTCODE: Place("Butetown", "Cardiff")}),
    )
    data = await coordinator._async_update_data()

    info = coordinator.describe(data.yours[0], 1.234)

    assert info["place_summary"] == "Butetown (Cardiff)"
    assert info["distance_km"] == 1.2
