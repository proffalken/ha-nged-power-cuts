"""Tests for setting up the integration and its entities end to end."""

from datetime import datetime

import pytest
from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er

from custom_components.nged_power_cuts.const import API_URL, DOMAIN
from custom_components.nged_power_cuts.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.nged_power_cuts.places import BULK_URL
from tests.conftest import LAT, LON, POSTCODE, api_response, live_records, load_fixture

NOW = "2026-10-22T21:30:00+00:00"


def _fault(**changes) -> dict:
    base = next(r for r in live_records() if r["fault_id"] == "INCD-109435-l")
    base.update(
        fault_id="HOME",
        postcode=POSTCODE,
        location_latitude=LAT,
        location_longitude=LON,
    )
    base.update(changes)
    return base


@pytest.fixture(autouse=True)
def frozen_now(freezer) -> None:
    freezer.move_to(NOW)


async def _setup(hass, entry, aioclient_mock, records) -> None:
    aioclient_mock.get(API_URL, json=api_response(records))
    aioclient_mock.post(BULK_URL, json=load_fixture("postcodes_bulk.json"))
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(hass, key: str, platform: str) -> str:
    registry = er.async_get(hass)
    for entity in registry.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == platform
            and entity.unique_id.endswith(f"_{key}")
        ):
            return entity.entity_id
    raise AssertionError(f"No {platform} entity for {key}")


async def test_setup_and_unload(hass, mock_config_entry, aioclient_mock) -> None:
    await _setup(hass, mock_config_entry, aioclient_mock, live_records())
    assert mock_config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_feed_is_down(
    hass, mock_config_entry, aioclient_mock
) -> None:
    aioclient_mock.get(API_URL, status=503)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_no_power_cut(hass, mock_config_entry, aioclient_mock) -> None:
    others = [r for r in live_records() if r["fault_id"] != "INCD-7034-j"]
    await _setup(hass, mock_config_entry, aioclient_mock, others)

    state = hass.states.get(_entity_id(hass, "power_cut", "binary_sensor"))
    assert state.state == "off"
    assert state.attributes["power_cuts"] == []
    assert state.attributes["attribution"] == "Supported by WPD Open Data"

    etr = hass.states.get(_entity_id(hass, "estimated_restoration", "sensor"))
    assert etr.state == "unknown"

    nearby = hass.states.get(_entity_id(hass, "nearby_power_cuts", "sensor"))
    assert nearby.state == "0"


async def test_unplanned_power_cut_at_home(
    hass, mock_config_entry, aioclient_mock
) -> None:
    near = _fault(fault_id="NEAR", postcode="CF10 1AA", location_latitude=LAT + 0.02)
    await _setup(
        hass, mock_config_entry, aioclient_mock, [_fault(), near, *live_records()]
    )

    state = hass.states.get(_entity_id(hass, "power_cut", "binary_sensor"))
    assert state.state == "on"
    assert state.attributes["device_class"] == "problem"
    ids = [c["id"] for c in state.attributes["power_cuts"]]
    assert ids == ["HOME", "INCD-7034-j"]

    # The latest estimate among the cuts at home: the Cardiff planned work ends.
    etr = hass.states.get(_entity_id(hass, "estimated_restoration", "sensor"))
    assert etr.state == "2027-01-22T12:00:00+00:00"

    nearby = hass.states.get(_entity_id(hass, "nearby_power_cuts", "sensor"))
    assert nearby.state == "3"
    assert [c["id"] for c in nearby.attributes["power_cuts"]] == [
        "HOME",
        "INCD-7034-j",
        "NEAR",
    ]
    assert nearby.attributes["power_cuts"][2]["distance_km"] == 2.2
    assert nearby.attributes["radius_km"] == 5


async def test_restoration_uses_etr_for_faults(
    hass, mock_config_entry, aioclient_mock
) -> None:
    await _setup(hass, mock_config_entry, aioclient_mock, [_fault()])

    etr = hass.states.get(_entity_id(hass, "estimated_restoration", "sensor"))
    assert etr.state == "2026-10-22T23:00:00+00:00"


async def test_planned_work_calendar(hass, mock_config_entry, aioclient_mock) -> None:
    await hass.config.async_set_time_zone("Europe/London")
    planned = _fault(
        fault_id="PLANNED",
        planned="true",
        category="LV PLANNED",
        etr=None,
        planned_outage_start_date="2026-10-29T09:00:00",
        planned_outage_end_date="2026-10-29T15:00:00",
    )
    await _setup(hass, mock_config_entry, aioclient_mock, [planned])

    calendar = _entity_id(hass, "planned_power_cuts", "calendar")
    state = hass.states.get(calendar)
    assert state.state == "off"
    assert state.attributes["message"] == "Planned power cut (LV PLANNED)"
    # 09:00 GMT: the clocks go back on 25 October.
    assert state.attributes["start_time"] == "2026-10-29 09:00:00"

    result = await hass.services.async_call(
        CALENDAR_DOMAIN,
        "get_events",
        {
            "entity_id": calendar,
            "start_date_time": datetime(2026, 10, 22),
            "duration": {"days": 14},
        },
        blocking=True,
        return_response=True,
    )
    (event,) = result[calendar]["events"]
    assert event["summary"] == "Planned power cut (LV PLANNED)"
    assert "PLANNED" in event["description"]
    assert POSTCODE in event["description"]

    # Not yet a power cut.
    state = hass.states.get(_entity_id(hass, "power_cut", "binary_sensor"))
    assert state.state == "off"


async def test_radius_option_reloads(hass, mock_config_entry, aioclient_mock) -> None:
    near = _fault(fault_id="NEAR", postcode="CF10 1AA", location_latitude=LAT + 0.02)
    await _setup(hass, mock_config_entry, aioclient_mock, [near])
    sensor = _entity_id(hass, "nearby_power_cuts", "sensor")
    assert hass.states.get(sensor).state == "1"

    hass.config_entries.async_update_entry(mock_config_entry, options={"radius_km": 1})
    await hass.async_block_till_done()

    assert hass.states.get(sensor).state == "0"


async def test_diagnostics_redact_the_home(
    hass, mock_config_entry, aioclient_mock
) -> None:
    await _setup(hass, mock_config_entry, aioclient_mock, [_fault()])

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    text = str(diagnostics)
    assert POSTCODE not in text
    assert str(LAT) not in text
    assert diagnostics["summary"]["total"] == 1
    assert diagnostics["summary"]["yours"] == 1


async def test_power_cut_attributes_name_the_places(
    hass, mock_config_entry, aioclient_mock
) -> None:
    await _setup(hass, mock_config_entry, aioclient_mock, [_fault()])

    state = hass.states.get(_entity_id(hass, "power_cut", "binary_sensor"))

    (cut,) = state.attributes["power_cuts"]
    assert cut["place_summary"] == "Butetown (Cardiff)"
    assert cut["customers_off"] == 107


async def test_device_is_named_after_the_entry(
    hass, mock_config_entry, aioclient_mock
) -> None:
    from homeassistant.helpers import device_registry as dr

    await _setup(hass, mock_config_entry, aioclient_mock, live_records())

    (device,) = dr.async_entries_for_config_entry(
        dr.async_get(hass), mock_config_entry.entry_id
    )
    assert device.name == f"Power cuts {mock_config_entry.title}"
