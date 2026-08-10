(() => {
  const COMPACT_MQ = window.matchMedia("(max-width: 1024px)");
  const PHONE_MQ = window.matchMedia("(max-width: 768px)");
  const LANDSCAPE_MQ = window.matchMedia("(orientation: landscape)");
  const SHORT_MQ = window.matchMedia("(max-height: 520px)");
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

  function syncDeviceMode() {
    const phone = PHONE_MQ.matches || (COMPACT_MQ.matches && SHORT_MQ.matches);
    const tablet = COMPACT_MQ.matches && !phone;
    const device = phone ? "phone" : tablet ? "tablet" : "desktop";
    const orientation = LANDSCAPE_MQ.matches ? "landscape" : "portrait";
    document.body.dataset.device = device;
    document.body.dataset.orientation = orientation;
    document.body.classList.toggle("is-phone", device === "phone");
    document.body.classList.toggle("is-tablet", device === "tablet");
    document.body.classList.toggle("is-desktop", device === "desktop");
    document.body.classList.toggle("is-landscape", orientation === "landscape");
    document.body.classList.toggle("is-portrait", orientation === "portrait");
    document.body.classList.toggle("is-short-viewport", SHORT_MQ.matches);
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
    const showMenu = isCompact() && !open;
    // Prefer topbar hamburger; keep edge tab hidden to avoid overlap on iPhone
    const tab = mobileOpenBtn();
    if (tab) tab.setAttribute("hidden", "");
    const menu = topbarMenuBtn();
    if (menu) {
      if (showMenu) menu.removeAttribute("hidden");
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

    syncDeviceMode();
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
      syncDeviceMode();
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

    [COMPACT_MQ, PHONE_MQ, LANDSCAPE_MQ, SHORT_MQ].forEach((mq) => {
      if (typeof mq.addEventListener === "function") mq.addEventListener("change", onMq);
      else if (typeof mq.addListener === "function") mq.addListener(onMq);
    });
    window.addEventListener("orientationchange", () => {
      window.setTimeout(onMq, 50);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
