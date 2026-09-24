/* Keep an open demonstration website in step with published CMS content. */
(() => {
  "use strict";
  const script = document.currentScript;
  const baseline = script?.dataset.version;
  const endpoint = script?.dataset.versionUrl;
  if (!/^[a-f0-9]{64}$/.test(baseline || "") || endpoint !== "/__demo/version") return;

  let checking = false;
  let edited = false;
  let lastInteraction = 0;

  const editable = "input, textarea, select, [contenteditable]:not([contenteditable='false'])";
  document.addEventListener("input", (event) => {
    if (event.target.closest(editable)) edited = true;
  }, true);
  document.addEventListener("change", (event) => {
    if (event.target.closest(editable)) edited = true;
  }, true);
  for (const event of ["pointerdown", "keydown"]) {
    document.addEventListener(event, () => { lastInteraction = Date.now(); }, true);
  }

  function interactionInProgress() {
    if (edited || Date.now() - lastInteraction < 3000) return true;
    if (document.activeElement?.matches(`${editable}, button, [role='button']`)) return true;
    if (document.querySelector("dialog[open], [role='dialog'][aria-modal='true']:not([hidden]), details[open]")) return true;
    for (const field of document.querySelectorAll("input, textarea, select")) {
      // Include browser autofill and restored form values, which may not emit input.
      if (field.type === "file" && field.files?.length) return true;
      if (["checkbox", "radio"].includes(field.type)) {
        if (field.checked !== field.defaultChecked) return true;
      } else if (field.tagName === "SELECT") {
        const options = [...field.options];
        if (field.multiple) {
          if (options.some((option) => option.selected !== option.defaultSelected)) return true;
        } else {
          const explicitDefault = options.findLastIndex((option) => option.defaultSelected);
          const defaultIndex = explicitDefault >= 0 ? explicitDefault : options.findIndex(
            (option) => !option.disabled && !option.closest("optgroup[disabled]")
          );
          if (field.selectedIndex !== defaultIndex) return true;
        }
      } else if (field.value !== field.defaultValue) return true;
    }
    return [...document.querySelectorAll("video, audio")].some((media) => !media.paused);
  }

  async function check() {
    if (document.hidden || checking) return;
    checking = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(endpoint, {
        cache: "no-store",
        credentials: "omit",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) return;
      const data = await response.json();
      if (/^[a-f0-9]{64}$/.test(data.version || "") && data.version !== baseline &&
          !document.hidden && !interactionInProgress()) {
        window.location.reload();
      }
    } catch {
      // A temporary outage should not interrupt the visitor; try next interval.
    } finally {
      window.clearTimeout(timeout);
      checking = false;
    }
  }

  window.setInterval(check, 15000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });
  check();
})();
