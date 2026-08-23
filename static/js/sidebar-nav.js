(() => {
  const STORAGE_KEY = "shift-manager.sidebar-nav";
  let openFlyoutGroup = null;

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

  function isRailMode() {
    return document.body.classList.contains("sidebar-rail");
  }

  function setGroupCollapsed(group, collapsed) {
    const toggle = group.querySelector(".nav-group-toggle");
    const body = group.querySelector(".nav-group-body");
    group.classList.toggle("is-collapsed", collapsed);
    if (toggle) toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    if (body) body.hidden = collapsed;
  }

  function closeFlyout() {
    document.querySelectorAll(".nav-group-flyout").forEach((el) => el.remove());
    document.querySelectorAll(".nav-group.is-flyout-open").forEach((el) => {
      el.classList.remove("is-flyout-open");
    });
    openFlyoutGroup = null;
  }

  function positionFlyout(group, flyout, toggle) {
    const rect = toggle.getBoundingClientRect();
    flyout.style.top = `${Math.max(8, rect.top)}px`;
    flyout.style.left = `${rect.right + 6}px`;
    const maxBottom = window.innerHeight - 8;
    const overflow = flyout.getBoundingClientRect().bottom - maxBottom;
    if (overflow > 0) {
      const nextTop = Math.max(8, rect.top - overflow);
      flyout.style.top = `${nextTop}px`;
    }
  }

  function openFlyout(group, toggle) {
    closeFlyout();
    const body = group.querySelector(".nav-group-body");
    if (!body) return;

    const flyout = document.createElement("div");
    flyout.className = "nav-group-flyout";
    flyout.innerHTML = body.innerHTML;
    document.body.appendChild(flyout);
    group.classList.add("is-flyout-open");
    openFlyoutGroup = group;
    positionFlyout(group, flyout, toggle);

    flyout.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", closeFlyout);
    });
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
      if (isRailMode()) {
        if (openFlyoutGroup === group) {
          closeFlyout();
        } else {
          openFlyout(group, toggle);
        }
        return;
      }

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

  document.addEventListener("click", (event) => {
    if (!openFlyoutGroup) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest(".nav-group-flyout") || target.closest(".nav-group-toggle")) return;
    closeFlyout();
  });

  window.addEventListener("resize", closeFlyout);
  window.addEventListener("sidebar-rail-change", closeFlyout);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
