/* Behavioral checks for the buildless preview; browser layout is checked separately. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
  path.join(__dirname, "../site/script.js"),
  "utf8",
);

class Element {
  constructor(values = {}) {
    this.handlers = {};
    this.style = {};
    this.dataset = {};
    this.attributes = {};
    this.hidden = true;
    this.textContent = "";
    const classes = new Set();
    this.classList = {
      add: (value) => classes.add(value),
      remove: (value) => classes.delete(value),
      contains: (value) => classes.has(value),
    };
    Object.assign(this, values);
  }
  addEventListener(name, callback) {
    (this.handlers[name] ||= []).push(callback);
  }
  async emit(name, event = {}) {
    for (const handler of this.handlers[name] || []) await handler(event);
  }
  setAttribute(name, value) {
    this.attributes[name] = value;
  }
  setPointerCapture(id) {
    this.capturedPointer = id;
  }
}

function load({
  stored = null,
  light = false,
  storageBlocked = false,
  clipboard = { writeText: async () => {} },
} = {}) {
  const ids = Object.fromEntries(
    [
      "page-theme",
      "demo-stage",
      "demo-widget",
      "reset-position",
      "radius",
      "radius-value",
      "demo-help",
      "demo-controls",
      "copy-command",
      "copy-status",
      "run-command",
    ].map((id) => [id, new Element()]),
  );
  Object.assign(ids["demo-stage"], { clientWidth: 500, clientHeight: 338 });
  Object.assign(ids["demo-widget"], { offsetWidth: 226, offsetHeight: 38 });
  ids["run-command"].textContent = "python source/app.py";
  const documentElement = new Element();
  const themeMeta = {};
  const looks = ["dark", "light"].map(
    (lookChoice) => new Element({ dataset: { lookChoice } }),
  );
  const preference = new Element({ matches: light });
  const writes = [];
  const window = new Element({
    matchMedia: () => preference,
    localStorage: {
      getItem() {
        if (storageBlocked) throw new Error("Storage blocked");
        return stored;
      },
      setItem(key, value) {
        if (storageBlocked) throw new Error("Storage blocked");
        writes.push({ key, value });
      },
    },
  });
  const document = {
    documentElement,
    getElementById: (id) => ids[id],
    querySelector: () => themeMeta,
    querySelectorAll: () => looks,
  };
  vm.runInNewContext(script, { document, window, navigator: { clipboard } });
  return { ids, documentElement, themeMeta, looks, preference, window, writes };
}

test("system theme follows changes until an explicit preference is persisted", async () => {
  const app = load({ light: true });
  assert.equal(app.documentElement.dataset.theme, "light");
  await app.preference.emit("change", { matches: false });
  assert.equal(app.documentElement.dataset.theme, "dark");
  await app.ids["page-theme"].emit("click");
  assert.equal(app.documentElement.dataset.theme, "light");
  assert.match(app.ids["page-theme"].attributes["aria-label"], /dark/);
  assert.deepEqual(app.writes, [
    { key: "netpulse-site-theme", value: "light" },
  ]);
  await app.preference.emit("change", { matches: false });
  assert.equal(app.documentElement.dataset.theme, "light");
});

test("saved themes win; corrupt or inaccessible storage falls back safely", async () => {
  assert.equal(
    load({ stored: "dark", light: true }).documentElement.dataset.theme,
    "dark",
  );
  assert.equal(
    load({ stored: "light" }).documentElement.dataset.theme,
    "light",
  );
  assert.equal(
    load({ stored: "invalid", light: true }).documentElement.dataset.theme,
    "light",
  );
  const blocked = load({ storageBlocked: true });
  await blocked.ids["page-theme"].emit("click");
  assert.equal(blocked.documentElement.dataset.theme, "light");
  assert.equal(blocked.ids["demo-controls"].hidden, false);
});

test("widget look is independent of page theme and exposes selected state", async () => {
  const app = load();
  await app.looks[1].emit("click");
  assert.equal(app.ids["demo-widget"].dataset.look, "light");
  assert.equal(app.documentElement.dataset.theme, "dark");
  assert.equal(app.looks[1].attributes["aria-pressed"], "true");
  assert.equal(app.looks[0].attributes["aria-pressed"], "false");
});

test("corner preview includes square and rounded ends, capped to mini height", async () => {
  const { ids } = load();
  for (const [input, expected] of [
    [0, 0],
    [12, 12],
    [24, 19],
  ]) {
    ids.radius.value = String(input);
    await ids.radius.emit("input");
    assert.equal(ids["radius-value"].value, input + " px");
    assert.equal(ids["demo-widget"].style.borderRadius, expected + "px");
  }
});

test("drag stays inside the preview and ends on cancel or lost capture", async () => {
  for (const stopEvent of [
    "pointerup",
    "pointercancel",
    "lostpointercapture",
  ]) {
    const { ids } = load();
    const widget = ids["demo-widget"];
    await widget.emit("pointerdown", {
      button: 0,
      isPrimary: true,
      pointerId: 1,
      clientX: 0,
      clientY: 0,
    });
    await widget.emit("pointermove", {
      pointerId: 1,
      clientX: 9999,
      clientY: 9999,
    });
    assert.equal(widget.style.left, "266px");
    assert.equal(widget.style.top, "250px");
    await widget.emit("pointermove", {
      pointerId: 1,
      clientX: -9999,
      clientY: -9999,
    });
    assert.equal(widget.style.left, "8px");
    assert.equal(widget.style.top, "8px");
    await widget.emit(stopEvent, { pointerId: 1 });
    await widget.emit("pointermove", {
      pointerId: 1,
      clientX: 500,
      clientY: 500,
    });
    assert.equal(widget.style.left, "8px");
    assert.equal(widget.classList.contains("is-dragging"), false);
  }
});

test("secondary and unrelated pointers cannot move the widget", async () => {
  const widget = load().ids["demo-widget"];
  const initial = widget.style.left;
  for (const event of [
    { button: 2, isPrimary: true },
    { button: 0, isPrimary: false },
  ]) {
    await widget.emit("pointerdown", {
      ...event,
      pointerId: 2,
      clientX: 0,
      clientY: 0,
    });
    await widget.emit("pointermove", {
      pointerId: 2,
      clientX: 100,
      clientY: 0,
    });
    assert.equal(widget.style.left, initial);
  }
  await widget.emit("pointerdown", {
    button: 0,
    isPrimary: true,
    pointerId: 1,
    clientX: 0,
    clientY: 0,
  });
  await widget.emit("pointermove", { pointerId: 2, clientX: 100, clientY: 0 });
  assert.equal(widget.style.left, initial);
});

test("keyboard movement, resizing, and reset keep the preview reachable", async () => {
  const { ids, window } = load();
  const widget = ids["demo-widget"];
  let prevented = false;
  await widget.emit("keydown", {
    key: "ArrowRight",
    shiftKey: true,
    preventDefault() {
      prevented = true;
    },
  });
  assert.equal(prevented, true);
  assert.equal(widget.style.left, "161px");
  await widget.emit("keydown", {
    key: "Tab",
    preventDefault() {
      assert.fail("Tab trapped");
    },
  });
  ids["demo-stage"].clientWidth = 280;
  await window.emit("resize");
  assert.equal(widget.style.left, "46px");
  await ids["reset-position"].emit("click");
  assert.equal(widget.style.left, "27px");
});

test("copy command reports success and a usable fallback on rejection or absence", async () => {
  let copied;
  const success = load({
    clipboard: {
      async writeText(value) {
        copied = value;
      },
    },
  });
  await success.ids["copy-command"].emit("click");
  assert.equal(copied, "python source/app.py");
  assert.match(success.ids["copy-status"].textContent, /Command copied/);
  for (const clipboard of [
    null,
    {
      async writeText() {
        throw new Error("Permission denied");
      },
    },
  ]) {
    const app = load({ clipboard });
    await app.ids["copy-command"].emit("click");
    assert.match(app.ids["copy-status"].textContent, /Select and copy/);
    assert.equal(app.ids["run-command"].textContent, "python source/app.py");
  }
});
