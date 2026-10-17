"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const input = document.querySelector("[data-jahez-link]");
  const button = document.querySelector("[data-jahez-copy]");
  if (!input || !button) return;
  input.value = new URL(input.value, window.location.origin).href;
  button.addEventListener("click", async () => {
    const status = document.querySelector("[data-jahez-copy-status]");
    try {
      await navigator.clipboard.writeText(input.value);
      status.textContent = button.dataset.copied;
    } catch (_) {
      input.focus(); input.select();
      status.textContent = button.dataset.fallback;
    }
  });
});
