(() => {
  const COMPACT_MQ = window.matchMedia("(max-width: 1024px)");
  const SIDEBAR_ID = "app-sidebar";
  const LS_KEY = "sidebar_collapsed";

  // ---- helpers ----
  function sidebar() {
    return document.getElementById(SIDEBAR_ID) || document.querySelector(".sidebar");
  }
  function overlay() {
    return document.getElementById("sidebar-overlay");
  }
  function toggleBtn() {
    return document.getElementById("nav-toggle");
  }
  function isCompact() {
    return COMPACT_MQ.matches;
  }

  // ---- desktop collapse (icon-rail mode) ----
  function isDesktopCollapsed() {
    return document.body.classList.contains("sidebar-collapsed");
  }

  function setDesktopCollapsed(collapsed) {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    try {
      localStorage.setItem(LS_KEY, collapsed ? "1" : "0");
    } catch (_) {}
    const btn = toggleBtn();
    if (btn) {
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      btn.setAttribute("aria-label", collapsed ? "メニューを開く" : "メニューを閉じる");
    }
  }

  function toggleDesktop() {
    setDesktopCollapsed(!isDesktopCollapsed());
  }

  // ---- mobile drawer ----
  function setMobileOpen(open) {
    const next = Boolean(open);
    document.body.classList.toggle("sidebar-open", next);
    const btn = toggleBtn();
    if (btn) {
      btn.setAttribute("aria-expanded", next ? "true" : "false");
      btn.setAttribute("aria-label", next ? "メニューを閉じる" : "メニューを開く");
    }
    const pane = sidebar();
    if (pane) pane.setAttribute("aria-hidden", !next ? "true" : "false");
    const veil = overlay();
    if (veil) {
      if (next) veil.removeAttribute("hidden");
      else veil.setAttribute("hidden", "");
    }
  }

  function closeMobile() {
    setMobileOpen(false);
  }

  function toggleMobile() {
    setMobileOpen(!document.body.classList.contains("sidebar-open"));
  }

  // ---- dispatch ----
  function handleToggle() {
    if (isCompact()) {
      toggleMobile();
    } else {
      toggleDesktop();
    }
  }

  // ---- ensure toggle button (desktop topbar) ----
  function ensureToggleButton() {
    if (toggleBtn()) return;
    const topbar = document.querySelector(".main > .topbar");
    if (!topbar) return;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = "nav-toggle";
    btn.className = "nav-toggle";
    btn.setAttribute("aria-label", "メニューを閉じる");
    btn.setAttribute("aria-controls", SIDEBAR_ID);
    btn.setAttribute("aria-expanded", "true");
    btn.innerHTML =
      '<span class="nav-toggle-box" aria-hidden="true">' +
      '<span class="nav-toggle-bar"></span>' +
      '<span class="nav-toggle-bar"></span>' +
      '<span class="nav-toggle-bar"></span>' +
      "</span>";
    topbar.insertBefore(btn, topbar.firstChild);
  }

  function ensureSidebarId() {
    const pane = sidebar();
    if (pane && !pane.id) pane.id = SIDEBAR_ID;
  }

  // ---- restore desktop state from localStorage ----
  function restoreDesktopState() {
    if (isCompact()) return;
    try {
      const stored = localStorage.getItem(LS_KEY);
      if (stored === "1") setDesktopCollapsed(true);
    } catch (_) {}
  }

  // ---- bind ----
  function bind() {
    ensureSidebarId();
    ensureToggleButton();
    restoreDesktopState();

    const btn = toggleBtn();
    if (btn && !btn.dataset.bound) {
      btn.dataset.bound = "1";
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        handleToggle();
      });
    }

    const veil = overlay();
    if (veil && !veil.dataset.bound) {
      veil.dataset.bound = "1";
      veil.addEventListener("click", closeMobile);
    }

    const closeBtn = document.getElementById("sidebar-close");
    if (closeBtn && !closeBtn.dataset.bound) {
      closeBtn.dataset.bound = "1";
      closeBtn.addEventListener("click", closeMobile);
    }

    const pane = sidebar();
    if (pane && !pane.dataset.navBound) {
      pane.dataset.navBound = "1";
      pane.addEventListener("click", (e) => {
        // On mobile: close drawer on nav click
        if (e.target.closest("a.nav-item") && isCompact()) closeMobile();
        // On desktop collapsed: open on any click inside sidebar
        if (!isCompact() && isDesktopCollapsed()) setDesktopCollapsed(false);
      });
    }

    if (!document.body.dataset.shellEscBound) {
      document.body.dataset.shellEscBound = "1";
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          if (isCompact()) closeMobile();
          else setDesktopCollapsed(true);
        }
      });
    }

    const onMq = () => {
      if (!isCompact()) {
        // switching to desktop: close mobile drawer, restore desktop state
        closeMobile();
        restoreDesktopState();
        const paneEl = sidebar();
        if (paneEl) paneEl.removeAttribute("aria-hidden");
        const btn2 = toggleBtn();
        if (btn2) {
          btn2.setAttribute("aria-expanded", isDesktopCollapsed() ? "false" : "true");
          btn2.setAttribute("aria-label", isDesktopCollapsed() ? "メニューを開く" : "メニューを閉じる");
        }
      } else {
        // switching to mobile: reset desktop collapse
        document.body.classList.remove("sidebar-collapsed");
        const paneEl = sidebar();
        if (paneEl) paneEl.setAttribute("aria-hidden", "true");
        const btn2 = toggleBtn();
        if (btn2) {
          btn2.setAttribute("aria-expanded", "false");
          btn2.setAttribute("aria-label", "メニューを開く");
        }
      }
    };
    if (typeof COMPACT_MQ.addEventListener === "function") COMPACT_MQ.addEventListener("change", onMq);
    else if (typeof COMPACT_MQ.addListener === "function") COMPACT_MQ.addListener(onMq);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
