// Tests for the NGED Power Cuts dashboard strategy. Run with: npm test
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  STRATEGY_TYPE,
  generateDashboard,
  keepStrategyRegistered,
  registerStrategy,
} from "../custom_components/nged_power_cuts/frontend/nged-power-cuts-strategy.js";

function entity(entity_id, translation_key, device_id, platform = "nged_power_cuts") {
  return { entity_id, translation_key, device_id, platform, labels: [] };
}

function home(slug, deviceId) {
  return [
    entity(`binary_sensor.${slug}_power_cut`, "power_cut", deviceId),
    entity(`sensor.${slug}_estimated_restoration`, "estimated_restoration", deviceId),
    entity(`sensor.${slug}_nearby_power_cuts`, "nearby_power_cuts", deviceId),
    entity(`calendar.${slug}_planned_power_cuts`, "planned_power_cuts", deviceId),
  ];
}

function makeHass({ second = false } = {}) {
  const list = [
    ...home("power_cuts_np25_3bg", "dev_home"),
    entity("binary_sensor.other_power_cut", "power_cut", "dev_other", "something_else"),
  ];
  const devices = {
    dev_home: { name: "Power cuts NP25 3BG", config_entries: ["entry1"] },
    dev_other: { name: "Something else", config_entries: ["other"] },
  };
  if (second) {
    list.push(...home("power_cuts_cf10_4rp", "dev_mum"));
    devices.dev_mum = { name: "Power cuts CF10 4RP", name_by_user: "Mum's", config_entries: ["entry2"] };
  }
  return { states: {}, entities: Object.fromEntries(list.map((e) => [e.entity_id, e])), devices };
}

const allCards = (view) => view.sections.flatMap((s) => s.cards);
const findCards = (view, type) => allCards(view).filter((c) => c.type === type);
const markdown = (view) => findCards(view, "markdown").map((c) => c.content).join("\n");

describe("generateDashboard", () => {
  it("builds one sections view with a stable path for notification links", async () => {
    const dash = await generateDashboard({}, makeHass());
    assert.equal(dash.views.length, 1);
    const [view] = dash.views;
    assert.equal(view.type, "sections");
    assert.equal(view.path, "power");
    assert.equal(dash.title, "Power cuts");
    assert.equal(view.title, "Power cuts");
  });

  it("uses a custom title", async () => {
    const dash = await generateDashboard({ title: "Power" }, makeHass());
    assert.equal(dash.title, "Power");
    assert.equal(dash.views[0].title, "Power");
  });

  it("starts with the home status, rendered from the power cut sensor", async () => {
    const [view] = (await generateDashboard({}, makeHass())).views;
    const [first] = view.sections;
    assert.equal(first.cards[0].heading, "Power cuts NP25 3BG");
    const status = first.cards.find((c) => c.type === "markdown").content;
    assert.match(status, /states\('binary_sensor\.power_cuts_np25_3bg_power_cut'\)/);
    assert.match(status, /state_attr\('binary_sensor\.power_cuts_np25_3bg_power_cut', 'power_cuts'\)/);
    assert.match(status, /sensor\.power_cuts_np25_3bg_estimated_restoration/);
    assert.match(status, /ha-alert/);
    assert.match(status, /Power is on/);
  });

  it("lists nearby cuts from the nearby sensor, with its radius", async () => {
    const [view] = (await generateDashboard({}, makeHass())).views;
    const nearby = view.sections.find((s) => s.cards[0].heading === "Nearby");
    assert.ok(nearby);
    const content = nearby.cards[1].content;
    assert.match(content, /state_attr\('sensor\.power_cuts_np25_3bg_nearby_power_cuts', 'power_cuts'\)/);
    assert.match(content, /'radius_km'/);
    assert.match(content, /distance_km/);
  });

  it("shows planned work as a calendar list", async () => {
    const [view] = (await generateDashboard({}, makeHass())).views;
    const [calendar] = findCards(view, "calendar");
    assert.deepEqual(calendar.entities, ["calendar.power_cuts_np25_3bg_planned_power_cuts"]);
    assert.equal(calendar.initial_view, "listWeek");
  });

  it("has no graphs", async () => {
    const [view] = (await generateDashboard({}, makeHass())).views;
    assert.equal(findCards(view, "history-graph").length, 0);
  });

  it("ignores entities from other integrations", async () => {
    const [view] = (await generateDashboard({}, makeHass())).views;
    assert.doesNotMatch(JSON.stringify(view), /binary_sensor\.other_power_cut/);
  });

  it("adds a block per home, sorted by name, using the user's device name", async () => {
    const [view] = (await generateDashboard({}, makeHass({ second: true }))).views;
    const homes = findCards(view, "heading")
      .map((c) => c.heading)
      .filter((h) => h.startsWith("Power cuts") || h === "Mum's");
    assert.deepEqual(homes, ["Mum's", "Power cuts NP25 3BG"]);
    assert.equal(findCards(view, "calendar").length, 2);
  });

  it("can be limited to one config entry", async () => {
    const [view] = (await generateDashboard({ entry_id: "entry2" }, makeHass({ second: true }))).views;
    const text = JSON.stringify(view);
    assert.match(text, /power_cuts_cf10_4rp/);
    assert.doesNotMatch(text, /power_cuts_np25_3bg/);
  });

  it("ends with links: NGED's map, the 105 line, and the user's own links", async () => {
    const config = { links: [{ name: "Power cut checklist", url: "https://example.com/power" }] };
    const [view] = (await generateDashboard(config, makeHass())).views;
    const last = view.sections.at(-1);
    assert.equal(last.cards[0].heading, "Links");
    const content = last.cards[1].content;
    assert.match(content, /powercuts\.nationalgrid\.co\.uk/);
    assert.match(content, /tel:105/);
    assert.match(content, /\[Power cut checklist\]\(https:\/\/example\.com\/power\)/);
  });

  it("explains what to do when the integration isn't set up", async () => {
    const [view] = (await generateDashboard({}, { entities: {}, devices: {} })).views;
    assert.match(markdown(view), /NGED Power Cuts integration/);
  });
});

describe("registerStrategy", () => {
  it("defines the custom element and lists it in the new-dashboard dialog", () => {
    const defined = {};
    const win = {};
    const registry = {
      get: (tag) => defined[tag],
      define: (tag, cls) => {
        defined[tag] = cls;
      },
    };

    registerStrategy(win, registry, class {});
    registerStrategy(win, registry, class {}); // loading twice is harmless

    assert.equal(STRATEGY_TYPE, "nged-power-cuts");
    const cls = defined["ll-strategy-dashboard-nged-power-cuts"];
    assert.equal(typeof cls.generate, "function");
    assert.equal(win.customStrategies.length, 1);
    assert.equal(win.customStrategies[0].type, "nged-power-cuts");
    assert.equal(win.customStrategies[0].strategyType, "dashboard");
    assert.equal(win.customStrategies[0].name, "NGED Power Cuts");
  });
});

function fakeRegistry() {
  const defined = {};
  return {
    get: (tag) => defined[tag],
    define: (tag, cls) => {
      if (defined[tag]) throw new Error(`${tag} already defined`);
      defined[tag] = cls;
    },
  };
}

function fakeTimers() {
  const timers = { callback: null, cleared: false, now: 0 };
  timers.setInterval = (fn) => {
    timers.callback = fn;
    return 1;
  };
  timers.clearInterval = () => {
    timers.cleared = true;
  };
  timers.tick = (ms) => {
    timers.now += ms;
    if (!timers.cleared) timers.callback();
  };
  return timers;
}

const TAG = "ll-strategy-dashboard-nged-power-cuts";

describe("keepStrategyRegistered", () => {
  it("registers again when Home Assistant swaps in a new element registry", () => {
    const win = { customElements: fakeRegistry(), HTMLElement: class {} };
    const timers = fakeTimers();
    keepStrategyRegistered(win, { timers, now: () => timers.now });
    assert.ok(win.customElements.get(TAG));

    win.customElements = fakeRegistry();
    timers.tick(200);

    assert.equal(typeof win.customElements.get(TAG).generate, "function");
    assert.equal(win.customStrategies.length, 1);
  });

  it("does not let a failed definition stop later attempts", () => {
    const win = { customElements: fakeRegistry(), HTMLElement: class {} };
    const timers = fakeTimers();
    keepStrategyRegistered(win, { timers, now: () => timers.now });
    const broken = fakeRegistry();
    broken.define = () => {
      throw new Error("not ready");
    };
    win.customElements = broken;
    assert.doesNotThrow(() => timers.tick(200));
    win.customElements = fakeRegistry();
    timers.tick(200);
    assert.ok(win.customElements.get(TAG));
  });

  it("stops checking after the time limit", () => {
    const win = { customElements: fakeRegistry(), HTMLElement: class {} };
    const timers = fakeTimers();
    keepStrategyRegistered(win, { timers, now: () => timers.now, timeoutMs: 1000 });
    timers.tick(1200);
    assert.ok(timers.cleared);
  });
});
