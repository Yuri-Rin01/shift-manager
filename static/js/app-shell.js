(() => {
  const COMPACT_MQ = window.matchMedia("(max-width: 1024px)");
  const PHONE_MQ = window.matchMedia("(max-width: 768px)");
  const LANDSCAPE_MQ = window.matchMedia("(orientation: landscape)");
  const SHORT_MQ = window.matchMedia("(max-height: 520px)");
  const SIDEBAR_ID = "app-sidebar";
  const LS_KEY = "sidebar_collapsed";
  const PEEK_LEAVE_MS = 220;
  const EDGE_OPEN_PX = 18;

  let peekCloseTimer = null;
  let pinnedCollapsed = false;

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

  function hotzone() {
    return document.getElementById("sidebar-hotzone");
  }

  function isCompact() {
    return COMPACT_MQ.matches;
  }

  function isDesktopCollapsed() {
    return document.body.classList.contains("sidebar-collapsed");
  }

  function isPeeking() {
    return document.body.classList.contains("sidebar-peek");
  }

  function syncDeviceMode() {
    const phone = PHONE_MQ.matches || (COMPACT_MQ.matches && SHORT_MQ.matches);
    const tablet = COMPACT_MQ.matches && !phone;
    const device = phone ? "phone" : tablet ? "tablet" : "desktop";
    const orientation = LANDSCAPE_MQ.matches ? "landscape" : "portrait";
    const isIos =
      /iP(hone|ad|od)/.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    document.body.dataset.device = device;
    document.body.dataset.orientation = orientation;
    document.body.classList.toggle("is-phone", device === "phone");
    document.body.classList.toggle("is-tablet", device === "tablet");
    document.body.classList.toggle("is-desktop", device === "desktop");
    document.body.classList.toggle("is-landscape", orientation === "landscape");
    document.body.classList.toggle("is-portrait", orientation === "portrait");
    document.body.classList.toggle("is-short-viewport", SHORT_MQ.matches);
    document.body.classList.toggle("is-ios", isIos);
    document.body.classList.toggle("is-compact", isCompact());
  }

  function syncCollapseButton() {
    const btn = collapseBtn();
    if (!btn || isCompact()) return;
    const collapsed = isDesktopCollapsed();
    btn.setAttribute("aria-expanded", collapsed && !isPeeking() ? "false" : "true");
    btn.setAttribute(
      "aria-label",
      collapsed && !isPeeking() ? "サイドバーを開く" : "サイドバーを折りたたむ"
    );
  }

  function syncMobileTab() {
    const open = document.body.classList.contains("sidebar-open");
    const showMenu = isCompact() && !open;
    const tab = mobileOpenBtn();
    if (tab) tab.setAttribute("hidden", "");
    const menu = topbarMenuBtn();
    if (menu) {
      if (showMenu) menu.removeAttribute("hidden");
      else menu.setAttribute("hidden", "");
    }
  }

  function clearPeekTimer() {
    if (peekCloseTimer) {
      window.clearTimeout(peekCloseTimer);
      peekCloseTimer = null;
    }
  }

  function setPeek(open) {
    if (isCompact() || !isDesktopCollapsed()) {
      document.body.classList.remove("sidebar-peek");
      clearPeekTimer();
      return;
    }
    document.body.classList.toggle("sidebar-peek", Boolean(open));
    syncCollapseButton();
  }

  function schedulePeekClose() {
    clearPeekTimer();
    peekCloseTimer = window.setTimeout(() => {
      setPeek(false);
      peekCloseTimer = null;
    }, PEEK_LEAVE_MS);
  }

  function setDesktopCollapsed(collapsed) {
    pinnedCollapsed = Boolean(collapsed);
    document.body.classList.toggle("sidebar-collapsed", pinnedCollapsed);
    if (!pinnedCollapsed) document.body.classList.remove("sidebar-peek");
    try {
      localStorage.setItem(LS_KEY, pinnedCollapsed ? "1" : "0");
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
      else {
        setDesktopCollapsed(false);
        syncCollapseButton();
      }
    } catch (_) {
      syncCollapseButton();
    }
  }

  function ensureHotzone() {
    let zone = hotzone();
    if (zone) return zone;
    zone = document.createElement("div");
    zone.id = "sidebar-hotzone";
    zone.className = "sidebar-hotzone";
    zone.setAttribute("aria-hidden", "true");
    document.body.appendChild(zone);
    return zone;
  }

  function bindPeekInteractions(pane) {
    if (!pane || pane.dataset.peekBound) return;
    pane.dataset.peekBound = "1";

    const zone = ensureHotzone();

    const openPeek = () => {
      if (isCompact() || !isDesktopCollapsed()) return;
      clearPeekTimer();
      setPeek(true);
    };

    const leavePeek = () => {
      if (isCompact() || !isDesktopCollapsed()) return;
      schedulePeekClose();
    };

    pane.addEventListener("mouseenter", openPeek);
    pane.addEventListener("mouseleave", leavePeek);
    zone.addEventListener("mouseenter", openPeek);
    zone.addEventListener("mouseleave", leavePeek);

    document.addEventListener("mousemove", (e) => {
      if (isCompact() || !isDesktopCollapsed()) return;
      if (e.clientX <= EDGE_OPEN_PX) {
        clearPeekTimer();
        setPeek(true);
        return;
      }
      if (!isPeeking()) return;
      const width = pane.getBoundingClientRect().width;
      if (e.clientX > width + 12 && !pane.matches(":hover") && !zone.matches(":hover")) {
        schedulePeekClose();
      }
    });
  }

  function bind() {
    const pane = sidebar();
    if (pane && !pane.id) pane.id = SIDEBAR_ID;

    syncDeviceMode();
    restoreDesktopState();
    syncMobileTab();
    bindPeekInteractions(pane);

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
      });
    }

    if (!document.body.dataset.shellEscBound) {
      document.body.dataset.shellEscBound = "1";
      document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        if (isCompact()) closeMobile();
        else if (isPeeking()) setPeek(false);
        else setDesktopCollapsed(true);
      });
    }

    const onMq = () => {
      syncDeviceMode();
      document.body.classList.remove("sidebar-peek");
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
