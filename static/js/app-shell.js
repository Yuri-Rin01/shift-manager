(() => {
  const COMPACT_MQ = window.matchMedia("(max-width: 1024px)");
  const SIDEBAR_ID = "app-sidebar";
  const LS_KEY = "sidebar_collapsed";

  function sidebar() {
    return document.getElementById(SIDEBAR_ID) || document.querySelector(".sidebar");
  }

  function overlay() {
    return document.getElementById("sidebar-overlay");
  }

  function collapseBtn() {
    return document.getElementById("sidebar-collapse");
  }

  function mobileOpenBtn() {
    return document.getElementById("sidebar-mobile-open");
  }

  function topbarMenuBtn() {
    return document.getElementById("topbar-menu-open");
  }

  function isCompact() {
    return COMPACT_MQ.matches;
  }

  function isDesktopCollapsed() {
    return document.body.classList.contains("sidebar-collapsed");
  }

  function syncCollapseButton() {
    const btn = collapseBtn();
    if (!btn || isCompact()) return;
    const collapsed = isDesktopCollapsed();
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    btn.setAttribute("aria-label", collapsed ? "サイドバーを開く" : "サイドバーを折りたたむ");
  }

  function syncMobileTab() {
    const open = document.body.classList.contains("sidebar-open");
    const show = isCompact() && !open;
    const tab = mobileOpenBtn();
    if (tab) {
      if (show) tab.removeAttribute("hidden");
      else tab.setAttribute("hidden", "");
    }
    const menu = topbarMenuBtn();
    if (menu) {
      if (show) menu.removeAttribute("hidden");
      else menu.setAttribute("hidden", "");
    }
  }

  function setDesktopCollapsed(collapsed) {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    try {
      localStorage.setItem(LS_KEY, collapsed ? "1" : "0");
    } catch (_) {}
    syncCollapseButton();
  }

  function toggleDesktop() {
    setDesktopCollapsed(!isDesktopCollapsed());
  }

  function setMobileOpen(open) {
    const next = Boolean(open);
    document.body.classList.toggle("sidebar-open", next);
    const pane = sidebar();
    if (pane) pane.setAttribute("aria-hidden", !next ? "true" : "false");
    const veil = overlay();
    if (veil) {
      if (next) veil.removeAttribute("hidden");
      else veil.setAttribute("hidden", "");
    }
    syncMobileTab();
  }

  function closeMobile() {
    setMobileOpen(false);
  }

  function openMobile() {
    setMobileOpen(true);
  }

  function restoreDesktopState() {
    if (isCompact()) return;
    try {
      if (localStorage.getItem(LS_KEY) === "1") setDesktopCollapsed(true);
      else syncCollapseButton();
    } catch (_) {
      syncCollapseButton();
    }
  }

  function bind() {
    const pane = sidebar();
    if (pane && !pane.id) pane.id = SIDEBAR_ID;

    restoreDesktopState();
    syncMobileTab();

    const collapse = collapseBtn();
    if (collapse && !collapse.dataset.bound) {
      collapse.dataset.bound = "1";
      collapse.addEventListener("click", (e) => {
        e.stopPropagation();
        if (isCompact()) return;
        toggleDesktop();
      });
    }

    const mobileTab = mobileOpenBtn();
    if (mobileTab && !mobileTab.dataset.bound) {
      mobileTab.dataset.bound = "1";
      mobileTab.addEventListener("click", (e) => {
        e.stopPropagation();
        openMobile();
      });
    }

    const topbarMenu = topbarMenuBtn();
    if (topbarMenu && !topbarMenu.dataset.bound) {
      topbarMenu.dataset.bound = "1";
      topbarMenu.addEventListener("click", (e) => {
        e.stopPropagation();
        openMobile();
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

    if (pane && !pane.dataset.navBound) {
      pane.dataset.navBound = "1";
      pane.addEventListener("click", (e) => {
        if (e.target.closest("a.nav-item") && isCompact()) closeMobile();
        if (!isCompact() && isDesktopCollapsed() && !e.target.closest("#sidebar-collapse")) {
          setDesktopCollapsed(false);
        }
      });
    }

    if (!document.body.dataset.shellEscBound) {
      document.body.dataset.shellEscBound = "1";
      document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        if (isCompact()) closeMobile();
        else setDesktopCollapsed(true);
      });
    }

    const onMq = () => {
      if (!isCompact()) {
        closeMobile();
        restoreDesktopState();
        if (pane) pane.removeAttribute("aria-hidden");
      } else {
        document.body.classList.remove("sidebar-collapsed");
        if (pane) pane.setAttribute("aria-hidden", "true");
      }
      syncMobileTab();
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
