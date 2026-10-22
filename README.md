# NGED Power Cuts

A Home Assistant custom integration that watches the live power cut feed from
[National Grid Electricity Distribution](https://www.nationalgrid.co.uk/electricity-distribution/)
(NGED, formerly Western Power Distribution) for one home. It tells you:

- whether NGED lists your postcode in a power cut that has started,
- when NGED expects your power back,
- how many power cuts have started near home,
- what planned work is coming up at or near home, as a calendar.

NGED is the distribution network operator for the East and West Midlands,
South West England and South Wales. If your home is elsewhere, NGED's feed
won't include it. The [Energy Networks Association](https://www.energynetworks.org/)
can tell you which operator covers your postcode.

No account or API key is needed.

## Requirements

- Home Assistant 2026.10 or newer.
- A home in NGED's area.

## Installation

### HACS

1. In HACS, open the menu, choose **Custom repositories**, and add
   `https://github.com/proffalken/ha-nged-power-cuts` as an **Integration**.
2. Install **NGED Power Cuts** and restart Home Assistant.

### Manual

Copy `custom_components/nged_power_cuts` into your Home Assistant
`config/custom_components` folder and restart.

## Configuration

Go to **Settings → Devices & services → Add integration → NGED Power Cuts**.

| Field | What it is for |
| --- | --- |
| Postcode | Your home's postcode. NGED lists the postcodes affected by each power cut, and the power cut sensor matches on this. |
| Latitude / longitude | Used to find power cuts near home. Defaults to the Home Assistant location. |
| Nearby radius | Power cuts within this distance of home count as nearby. Defaults to 5 km. |

You can add more than one postcode, for example a relative's home. Each
postcode is a separate entry. You can change the radius later under
**Configure**.

## Entities

Each postcode gets one device, **Power cuts &lt;postcode&gt;**, with these
entities.

| Entity | State | Attributes |
| --- | --- | --- |
| Power cut (binary sensor, problem) | On while NGED lists your postcode in a power cut that has started. Planned work counts from its planned start. | `power_cuts`: the cuts at your postcode. |
| Estimated restoration (timestamp sensor) | NGED's estimated restoration time for your postcode. With more than one cut, the latest estimate. Planned work with no estimate uses its planned end. Unknown when there is no cut. | |
| Nearby power cuts (sensor) | The number of power cuts that have started within the radius, including your own. | `radius_km`; `power_cuts`, nearest first, each with `distance_km`. |
| Planned power cuts (calendar) | Planned work at your postcode or within the radius that hasn't finished yet. | The usual calendar attributes for the current or next event. |

Each power cut in the attributes has `id` (NGED's reference), `area`,
`status`, `category`, `planned`, `reported`, `estimated_restoration`,
`planned_start`, `planned_end`, `psr_customers` (the number of customers on the
Priority Services Register affected), and `postcodes`.

Distance is measured from your location to the point NGED gives for the cut,
in a straight line.

The feed is polled every 5 minutes.

## Events

`nged_power_cuts_changed` is fired when a power cut at your postcode or within
the radius changes. Nothing is fired for the first poll after Home Assistant
starts, so a restart doesn't re-announce power cuts it already knew about.

| Field | Meaning |
| --- | --- |
| `config_entry_id` | The entry the event belongs to. |
| `change` | `new`, `updated` (status, category, times or postcodes changed), `started` (planned work has reached its start time) or `restored` (it left the feed). |
| `affects_you` | `true` if your postcode is listed. |
| `distance_km` | Distance from home, if NGED gave a location. |
| | Plus every power cut field listed under **Entities**. |

## Example automations

Tell your phone when a power cut at home is reported, restored, or its
restoration time changes:

```yaml
triggers:
  - trigger: event
    event_type: nged_power_cuts_changed
    event_data:
      affects_you: true
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Power cut {{ trigger.event.data.change }}"
      message: >-
        NGED {{ trigger.event.data.id }} ({{ trigger.event.data.category }}).
        {% if trigger.event.data.estimated_restoration %}
        Estimated restoration
        {{ as_datetime(trigger.event.data.estimated_restoration) | as_local }}.
        {% endif %}
```

A reminder the evening before planned work:

```yaml
triggers:
  - trigger: calendar
    event: start
    offset: "-12:00:00"
    entity_id: calendar.power_cuts_ab1_2cd_planned_power_cuts
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Planned power cut tomorrow
      message: "{{ trigger.calendar_event.summary }} from {{ trigger.calendar_event.start }}"
```

## Limitations

- If the power is off at home, your router may be off too. Home Assistant can
  only see the feed and send notifications while it has power and internet.
- The feed covers NGED's network only.
- NGED gives one location per power cut. A cut can affect postcodes some way
  from that point, so the nearby count is a guide.

## Development

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

`tests/fixtures/power_cuts_live.json` is a real snapshot of the feed from
22 October 2026. `scripts/make_icon.py` draws the brand icon
(`uv run --with pillow python scripts/make_icon.py`).

## Attribution

Supported by WPD Open Data. The power cut data comes from the
[Live Power Cuts](https://connecteddata.nationalgrid.co.uk/dataset/live-power-cuts)
dataset on NGED Connected Data, published under the WPD Open Data Licence.

This integration isn't made or endorsed by National Grid.

## Licence

MIT. See [LICENSE](LICENSE).
