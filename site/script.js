(() => {
  "use strict";

  const page = document.documentElement;
  const pageTheme = document.getElementById("page-theme");
  const preference = window.matchMedia("(prefers-color-scheme: light)");
  let chosenTheme = null;
  try {
    const saved = window.localStorage.getItem("netpulse-site-theme");
    if (saved === "dark" || saved === "light") chosenTheme = saved;
  } catch {
    /* The page also works when browser storage is unavailable. */
  }

  function applyPageTheme(theme) {
    page.dataset.theme = theme;
    pageTheme.setAttribute(
      "aria-label",
      `Switch to ${theme === "dark" ? "light" : "dark"} theme`,
    );
    document.querySelector('meta[name="theme-color"]').content =
      theme === "dark" ? "#101613" : "#f6f8f1";
  }
  applyPageTheme(chosenTheme || (preference.matches ? "light" : "dark"));
  pageTheme.hidden = false;
  pageTheme.addEventListener("click", () => {
    chosenTheme = page.dataset.theme === "dark" ? "light" : "dark";
    applyPageTheme(chosenTheme);
    try {
      window.localStorage.setItem("netpulse-site-theme", chosenTheme);
    } catch {
      /* Optional preference. */
    }
  });
  preference.addEventListener("change", (event) => {
    if (!chosenTheme) applyPageTheme(event.matches ? "light" : "dark");
  });

  const stage = document.getElementById("demo-stage");
  const widget = document.getElementById("demo-widget");
  const reset = document.getElementById("reset-position");
  const radius = document.getElementById("radius");
  const radiusValue = document.getElementById("radius-value");
  const lookButtons = document.querySelectorAll("[data-look-choice]");
  let position = null;
  let drag = null;

  function place(x, y) {
    // Keep the complete mini widget inside the desktop and above its taskbar.
    const maxX = Math.max(8, stage.clientWidth - widget.offsetWidth - 8);
    const maxY = Math.max(8, stage.clientHeight - widget.offsetHeight - 50);
    position = {
      x: Math.min(maxX, Math.max(8, x)),
      y: Math.min(maxY, Math.max(8, y)),
    };
    widget.style.left = `${position.x}px`;
    widget.style.top = `${position.y}px`;
    widget.style.transform = "none";
  }
  function center() {
    place(
      (stage.clientWidth - widget.offsetWidth) / 2,
      stage.clientHeight * 0.42 - widget.offsetHeight / 2,
    );
  }
  center();
  // Enable touch dragging only after pointer handlers are installed.
  widget.style.touchAction = "none";
  reset.hidden = false;
  document.getElementById("demo-help").textContent =
    "Drag to try Mini mode · sample readings";
  reset.addEventListener("click", center);
  widget.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || !event.isPrimary) return;
    drag = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      startX: position.x,
      startY: position.y,
    };
    widget.setPointerCapture(event.pointerId);
    widget.classList.add("is-dragging");
  });
  widget.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    place(
      drag.startX + event.clientX - drag.x,
      drag.startY + event.clientY - drag.y,
    );
  });
  function stopDrag(event) {
    if (!drag || event.pointerId !== drag.id) return;
    drag = null;
    widget.classList.remove("is-dragging");
  }
  widget.addEventListener("pointerup", stopDrag);
  widget.addEventListener("pointercancel", stopDrag);
  widget.addEventListener("lostpointercapture", stopDrag);
  widget.addEventListener("keydown", (event) => {
    const directions = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    };
    const direction = directions[event.key];
    if (!direction) return;
    event.preventDefault();
    const step = event.shiftKey ? 24 : 8;
    place(position.x + direction[0] * step, position.y + direction[1] * step);
  });
  window.addEventListener("resize", () => {
    drag = null;
    widget.classList.remove("is-dragging");
    if (position) place(position.x, position.y);
  });

  document.getElementById("demo-controls").hidden = false;
  lookButtons.forEach((button) =>
    button.addEventListener("click", () => {
      widget.dataset.look = button.dataset.lookChoice;
      lookButtons.forEach((choice) =>
        choice.setAttribute("aria-pressed", String(choice === button)),
      );
    }),
  );
  radius.addEventListener("input", () => {
    radiusValue.value = `${radius.value} px`;
    widget.style.borderRadius = `${Math.min(Number(radius.value), widget.offsetHeight / 2)}px`;
  });

  const copy = document.getElementById("copy-command");
  const copyStatus = document.getElementById("copy-status");
  copy.hidden = false;
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(
        document.getElementById("run-command").textContent,
      );
      copyStatus.textContent = "Command copied. Paste it into your terminal.";
    } catch {
      copyStatus.textContent =
        "Copy is unavailable in this browser. Select and copy the command above.";
    }
  });
})();
