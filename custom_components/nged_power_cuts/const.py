"""Constants for the NGED Power Cuts integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "nged_power_cuts"

CONF_POSTCODE: Final = "postcode"
CONF_RADIUS_KM: Final = "radius_km"
DEFAULT_RADIUS_KM: Final = 5.0

# NGED Connected Data (CKAN). "Live Detailed Power Cuts" in the "Live Power
# Cuts" dataset, published under the WPD Open Data Licence.
API_URL: Final = (
    "https://connecteddata.nationalgrid.co.uk/api/3/action/datastore_search"
)
RESOURCE_ID: Final = "a1365982-4e05-463c-8304-8323a2ba0ccd"
DATASET_URL: Final = "https://connecteddata.nationalgrid.co.uk/dataset/live-power-cuts"
POWER_CUT_MAP_URL: Final = "https://powercuts.nationalgrid.co.uk/"
PAGE_SIZE: Final = 1000
MAX_PAGES: Final = 20

UPDATE_INTERVAL: Final = timedelta(minutes=5)

ATTRIBUTION: Final = "Supported by WPD Open Data"

EVENT_POWER_CUT_CHANGED: Final = f"{DOMAIN}_changed"
