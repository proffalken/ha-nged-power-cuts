"""Tests for the NGED Power Cuts config and options flows."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.data_entry_flow import FlowResultType

from custom_components.nged_power_cuts.api import NGEDError
from custom_components.nged_power_cuts.const import (
    CONF_POSTCODE,
    CONF_RADIUS_KM,
    DOMAIN,
)
from custom_components.nged_power_cuts.models import parse_power_cuts
from tests.conftest import LAT, LON, POSTCODE, live_records


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    client = MagicMock()
    client.async_get_power_cuts = AsyncMock(
        return_value=parse_power_cuts(live_records())
    )
    with patch(
        "custom_components.nged_power_cuts.config_flow.NGEDApiClient",
        return_value=client,
    ):
        yield client


@pytest.fixture(autouse=True)
def no_setup() -> Generator[None]:
    with patch(
        "custom_components.nged_power_cuts.async_setup_entry", return_value=True
    ):
        yield


def _input(**overrides):
    data = {
        CONF_POSTCODE: "cf104rp",
        CONF_LATITUDE: LAT,
        CONF_LONGITUDE: LON,
        CONF_RADIUS_KM: 5,
    }
    data.update(overrides)
    return data


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_creates_entry_with_normalised_postcode(hass, mock_client) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], _input())

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == POSTCODE
    assert result["data"] == {
        CONF_POSTCODE: POSTCODE,
        CONF_LATITUDE: LAT,
        CONF_LONGITUDE: LON,
        CONF_RADIUS_KM: 5,
    }
    assert result["result"].unique_id == POSTCODE


async def test_defaults_to_home_location(hass, mock_client) -> None:
    hass.config.latitude = 51.81
    hass.config.longitude = -2.71
    result = await _start(hass)

    defaults = {
        str(key): key.default() for key in result["data_schema"].schema if key.default
    }
    assert defaults[CONF_LATITUDE] == 51.81
    assert defaults[CONF_LONGITUDE] == -2.71


async def test_rejects_a_bad_postcode(hass, mock_client) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input(postcode="Monmouth")
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_POSTCODE: "invalid_postcode"}


async def test_cannot_connect(hass, mock_client) -> None:
    mock_client.async_get_power_cuts.side_effect = NGEDError("down")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _input())

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_client.async_get_power_cuts.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _input())
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_same_postcode_twice_aborts(hass, mock_client, mock_config_entry) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _input())

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_change_radius(hass, mock_config_entry) -> None:
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_RADIUS_KM: 12}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_RADIUS_KM: 12}
