// NGED Power Cuts dashboard strategy.
//
// Served by the integration and loaded on every Home Assistant page. It adds
// an "NGED Power Cuts" option to Settings > Dashboards > Add dashboard. The
// dashboard is rebuilt from the integration's entities each time it opens,
// so new homes and new entities appear without editing anything.
//
// Optional strategy config (edit the dashboard's raw configuration):
//   title: Power cuts            # dashboard and view title
//   entry_id: <config entry id>  # only show one postcode
//   links:                       # extra links in the links section
//     - name: Power cut checklist
//       url: https://example.com

export const STRATEGY_TYPE = "nged-power-cuts";
const PLATFORM = "nged_power_cuts";
const VIEW_PATH = "power";
const DEFAULT_TITLE = "Power cuts";

const NGED_MAP_URL = "https://powercuts.nationalgrid.co.uk/";
const TIME_FORMAT = "%a %-d %b, %H:%M";

function ngedEntities(hass, entryId) {
  const entities = Object.values(hass.entities || {}).filter((e) => e.platform === PLATFORM);
  if (!entryId) return entities;
  return entities.filter((e) => {
    const device = (hass.devices || {})[e.device_id];
    return device && (device.config_entries || []).includes(entryId);
  });
}

function byKey(entities, key) {
  return entities.find((e) => e.translation_key === key)?.entity_id;
}

function deviceName(hass, deviceId) {
  const device = (hass.devices || {})[deviceId] || {};
  return device.name_by_user || device.name || "Power cuts";
}

// "Power cuts Lily's work" -> "Lily's work", for headings that say "Near ...".
function placeName(hass, deviceId) {
  return deviceName(hass, deviceId).replace(/^Power cuts /, "");
}

// Jinja for a feed time, or a fallback when NGED gave none.
function time(expr, fallback) {
  return `{{ (as_timestamp(${expr}) | timestamp_custom('${TIME_FORMAT}')) if ${expr} else '${fallback}' }}`;
}

function statusContent(cutId, restorationId) {
  return `{% set state = states('${cutId}') %}
{% set cuts = state_attr('${cutId}', 'power_cuts') or [] %}
{% if state in ['unknown', 'unavailable'] %}
<ha-alert alert-type="info">Power cut data is unavailable right now. Check NGED's power cut map or call 105.</ha-alert>
{% elif state == 'off' %}
<ha-alert alert-type="success">Power is on. NGED doesn't list this postcode in any power cut.</ha-alert>
{% else %}
{% set etr = states('${restorationId}') %}
<ha-alert alert-type="error" title="Power cut">
NGED expects power back by {{ (as_timestamp(etr) | timestamp_custom('${TIME_FORMAT}')) if etr not in ['unknown', 'unavailable'] else 'an unknown time' }}.
</ha-alert>
{% for c in cuts %}
**{{ c.place_summary or c.id }}**: {{ 'planned work' if c.planned else 'fault' }} ({{ c.category or 'unknown type' }}){% if c.customers_off %}, {{ c.customers_off }} customers off{% endif %}<br>
{% if c.planned %}Planned ${time("c.planned_start", "start not given")} to ${time("c.planned_end", "end not given")}{% else %}Reported ${time("c.reported", "at an unknown time")}{% endif %}<br>
Estimated restoration: ${time("c.estimated_restoration", "not given")}<br>
NGED reference {{ c.id }}
{% if c.psr_customers %}<br>{{ c.psr_customers }} Priority Services Register customers affected{% endif %}

{% endfor %}
{% endif %}`;
}

function nearbyContent(nearbyId) {
  return `{% set cuts = state_attr('${nearbyId}', 'power_cuts') or [] %}
{% set radius = state_attr('${nearbyId}', 'radius_km') %}
{% if states('${nearbyId}') in ['unknown', 'unavailable'] %}
Nearby power cut data is unavailable right now.
{% elif cuts | count == 0 %}
No power cuts within {{ '%g' | format(radius | float(0)) }} km.
{% else %}
{% for c in cuts %}
- **{{ c.distance_km }} km**: {{ c.place_summary or c.id }}, {{ 'planned work' if c.planned else 'fault' }}{% if c.customers_off %}, {{ c.customers_off }} customers off{% endif %} ({{ (c.postcode_sectors or c.postcodes) | join(', ') }}). Restoration: ${time("c.estimated_restoration", "no estimate")}
{% endfor %}
{% endif %}`;
}

function radiusOf(hass, entityId) {
  return hass.states?.[entityId]?.attributes?.radius_km;
}

function homeSections(hass, deviceId, entities, several) {
  const cut = byKey(entities, "power_cut");
  const restoration = byKey(entities, "estimated_restoration");
  const nearby = byKey(entities, "nearby_power_cuts");
  const calendar = byKey(entities, "planned_power_cuts");
  const sections = [];

  if (cut) {
    sections.push({
      type: "grid",
      cards: [
        { type: "heading", heading: deviceName(hass, deviceId) },
        { type: "markdown", content: statusContent(cut, restoration) },
      ],
    });
  }
  if (nearby && radiusOf(hass, nearby) !== 0) {
    sections.push({
      type: "grid",
      cards: [
        { type: "heading", heading: several ? `Near ${placeName(hass, deviceId)}` : "Nearby" },
        { type: "markdown", content: nearbyContent(nearby) },
      ],
    });
  }
  if (calendar) {
    sections.push({
      type: "grid",
      cards: [
        { type: "heading", heading: "Planned work" },
        { type: "calendar", entities: [calendar], initial_view: "listWeek" },
      ],
    });
  }
  return sections;
}

function linksContent(config) {
  const lines = [
    `- [NGED power cut map](${NGED_MAP_URL})`,
    "- Report or ask about a power cut: [105](tel:105) (free from any phone)",
  ];
  for (const link of config.links || []) {
    lines.push(`- [${link.name}](${link.url})`);
  }
  return lines.join("\n");
}

export async function generateDashboard(config, hass) {
  const title = config.title || DEFAULT_TITLE;
  const entities = ngedEntities(hass, config.entry_id);

  if (entities.length === 0) {
    const sections = [
      {
        type: "grid",
        cards: [
          {
            type: "markdown",
            content:
              "No power cut data yet. Set up the NGED Power Cuts integration under " +
              "**Settings > Devices & services**, then reload this dashboard.",
          },
        ],
      },
    ];
    return { title, views: [{ type: "sections", title, path: VIEW_PATH, sections }] };
  }

  const devices = new Map();
  for (const e of entities) {
    if (!e.device_id) continue;
    if (!devices.has(e.device_id)) devices.set(e.device_id, []);
    devices.get(e.device_id).push(e);
  }
  const homes = [...devices.entries()].sort(([a], [b]) =>
    deviceName(hass, a).localeCompare(deviceName(hass, b)),
  );

  const several = homes.length > 1;
  const sections = homes.flatMap(([deviceId, list]) =>
    homeSections(hass, deviceId, list, several),
  );
  sections.push({
    type: "grid",
    cards: [
      { type: "heading", heading: "Links" },
      { type: "markdown", content: linksContent(config) },
    ],
  });

  return {
    title,
    views: [{ type: "sections", title, path: VIEW_PATH, max_columns: 3, sections }],
  };
}

export function registerStrategy(win, registry, BaseClass) {
  const tag = `ll-strategy-dashboard-${STRATEGY_TYPE}`;
  if (!registry.get(tag)) {
    registry.define(
      tag,
      class extends BaseClass {
        static async generate(config, hass) {
          return generateDashboard(config, hass);
        }
      },
    );
  }
  win.customStrategies = win.customStrategies || [];
  if (!win.customStrategies.some((s) => s.type === STRATEGY_TYPE)) {
    win.customStrategies.push({
      type: STRATEGY_TYPE,
      strategyType: "dashboard",
      name: "NGED Power Cuts",
      description: "Power cuts at and near home, and planned work, from National Grid Electricity Distribution.",
      documentationURL: "https://github.com/proffalken/ha-nged-power-cuts",
    });
  }
}

// Home Assistant's frontend installs a scoped custom element registry
// polyfill when it starts, which replaces window.customElements. This script
// is loaded at the same time, so it can define the strategy in the original
// registry just before the swap, where Home Assistant can no longer see it.
// Keep checking for a while after loading and define it again if it has gone.
export function keepStrategyRegistered(
  win,
  { intervalMs = 200, timeoutMs = 60000, timers = globalThis, now = Date.now } = {},
) {
  const attempt = () => {
    try {
      registerStrategy(win, win.customElements, win.HTMLElement);
    } catch (err) {
      // The registry may not be ready yet; the next check tries again.
    }
  };
  attempt();
  const started = now();
  const handle = timers.setInterval(() => {
    if (now() - started > timeoutMs) {
      timers.clearInterval(handle);
      return;
    }
    if (!win.customElements.get(`ll-strategy-dashboard-${STRATEGY_TYPE}`)) attempt();
  }, intervalMs);
}

if (typeof window !== "undefined" && window.customElements) {
  keepStrategyRegistered(window);
}
