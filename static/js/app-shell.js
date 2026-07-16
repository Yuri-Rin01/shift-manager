(() => {
  const MQ = window.matchMedia("(max-width: 1024px)");
  const SIDEBAR_ID = "app-sidebar";

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
    return MQ.matches;
  }

  function setOpen(open) {
    const next = Boolean(open) && isCompact();
    document.body.classList.toggle("sidebar-open", next);
    const btn = toggleBtn();
    if (btn) {
      btn.setAttribute("aria-expanded", next ? "true" : "false");
      btn.setAttribute("aria-label", next ? "メニューを閉じる" : "メニューを開く");
    }
    const pane = sidebar();
    if (pane) pane.setAttribute("aria-hidden", isCompact() && !next ? "true" : "false");
    const veil = overlay();
    if (veil) {
      if (next) veil.removeAttribute("hidden");
      else veil.setAttribute("hidden", "");
    }
  }

  function close() {
    setOpen(false);
  }

  function toggle() {
    setOpen(!document.body.classList.contains("sidebar-open"));
  }

  function ensureToggleButton() {
    if (toggleBtn()) return;
    const topbar = document.querySelector(".main > .topbar");
    if (!topbar) return;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = "nav-toggle";
    btn.className = "nav-toggle";
    btn.setAttribute("aria-label", "メニューを開く");
    btn.setAttribute("aria-controls", SIDEBAR_ID);
    btn.setAttribute("aria-expanded", "false");
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

  function bind() {
    ensureSidebarId();
    ensureToggleButton();

    const btn = toggleBtn();
    if (btn && !btn.dataset.bound) {
      btn.dataset.bound = "1";
      btn.addEventListener("click", (event) => {
        event.stopPropagation();
        toggle();
      });
    }

    const veil = overlay();
    if (veil && !veil.dataset.bound) {
      veil.dataset.bound = "1";
      veil.addEventListener("click", close);
    }

    const closeBtn = document.getElementById("sidebar-close");
    if (closeBtn && !closeBtn.dataset.bound) {
      closeBtn.dataset.bound = "1";
      closeBtn.addEventListener("click", close);
    }

    const pane = sidebar();
    if (pane && !pane.dataset.navBound) {
      pane.dataset.navBound = "1";
      pane.addEventListener("click", (event) => {
        const link = event.target.closest("a.nav-item");
        if (link && isCompact()) close();
      });
    }

    if (!document.body.dataset.shellEscBound) {
      document.body.dataset.shellEscBound = "1";
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") close();
      });
    }

    const onMq = () => {
      if (!isCompact()) setOpen(false);
      else {
        const paneEl = sidebar();
        if (paneEl) paneEl.setAttribute("aria-hidden", "true");
      }
    };
    if (typeof MQ.addEventListener === "function") MQ.addEventListener("change", onMq);
    else if (typeof MQ.addListener === "function") MQ.addListener(onMq);
    onMq();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
