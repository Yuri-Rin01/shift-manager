(() => {
  const STORAGE_KEY = "shift-manager.sidebar-nav";

  function readState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function writeState(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function setGroupCollapsed(group, collapsed) {
    const toggle = group.querySelector(".nav-group-toggle");
    const body = group.querySelector(".nav-group-body");
    group.classList.toggle("is-collapsed", collapsed);
    if (toggle) toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    if (body) body.hidden = collapsed;
  }

  function initGroup(group) {
    const key = group.dataset.navGroup;
    if (!key) return;

    const toggle = group.querySelector(".nav-group-toggle");
    if (!toggle) return;

    const saved = readState();
    if (Object.prototype.hasOwnProperty.call(saved, key)) {
      setGroupCollapsed(group, Boolean(saved[key]));
    }

    toggle.addEventListener("click", () => {
      const collapsed = !group.classList.contains("is-collapsed");
      setGroupCollapsed(group, collapsed);
      const next = readState();
      next[key] = collapsed;
      writeState(next);
    });
  }

  function initAll() {
    document.querySelectorAll(".nav-group").forEach(initGroup);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
