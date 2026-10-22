"""Shared fixtures for the NGED Power Cuts test suite."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nged_power_cuts.const import (
    CONF_POSTCODE,
    CONF_RADIUS_KM,
    DOMAIN,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# "Home" for the tests is the postcode of a real planned outage in the captured
# feed (Cardiff, in progress from July 2026 to January 2027).
POSTCODE = "CF10 4RP"
LAT = 51.4546
LON = -3.1568

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for every test in this suite."""
    yield


def load_fixture(name: str) -> Any:
    """Load a JSON fixture by file name."""
    return json.loads((FIXTURES_DIR / name).read_text())


def live_records() -> list[dict[str, Any]]:
    """The records from the captured live feed (a fresh copy each time)."""
    return copy.deepcopy(load_fixture("power_cuts_live.json")["result"]["records"])


def api_response(records: list[dict[str, Any]], total: int | None = None) -> dict:
    """Wrap records the way the CKAN datastore_search API does."""
    return {
        "success": True,
        "result": {
            "records": records,
            "total": len(records) if total is None else total,
        },
    }


@pytest.fixture
def mock_config_entry(hass) -> MockConfigEntry:
    """A config entry for the test home."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"NGED power cuts {POSTCODE}",
        data={
            CONF_POSTCODE: POSTCODE,
            "latitude": LAT,
            "longitude": LON,
            CONF_RADIUS_KM: 5,
        },
        unique_id=POSTCODE,
    )
    entry.add_to_hass(hass)
    return entry
