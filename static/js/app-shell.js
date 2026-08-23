(() => {
  const COMPACT_MQ = window.matchMedia("(max-width: 900px)");
  const RAIL_KEY = "shift-manager.sidebar-rail";

  function sidebar() {
    return document.querySelector(".sidebar");
  }

  function isRailEnabled() {
    return document.body.classList.contains("sidebar-rail");
  }

  function setRail(rail) {
    if (COMPACT_MQ.matches) {
      document.body.classList.remove("sidebar-rail");
      return;
    }
    document.body.classList.toggle("sidebar-rail", rail);
    const btn = document.getElementById("sidebar-rail-toggle");
    if (btn) {
      btn.setAttribute("aria-label", rail ? "サイドバーを展開" : "サイドバーを折りたたむ");
      btn.title = rail ? "サイドバーを展開" : "サイドバーを折りたたむ";
    }
    if (rail) {
      localStorage.setItem(RAIL_KEY, "1");
    } else {
      localStorage.setItem(RAIL_KEY, "0");
    }
    window.dispatchEvent(new CustomEvent("sidebar-rail-change", { detail: { rail } }));
  }

  function initRailToggle() {
    const btn = document.getElementById("sidebar-rail-toggle");
    if (!btn) return;
    setRail(!COMPACT_MQ.matches && localStorage.getItem(RAIL_KEY) === "1");
    btn.addEventListener("click", () => {
      setRail(!isRailEnabled());
    });
  }

  function ensureOverlay() {
    let el = document.getElementById("sidebar-overlay");
    if (el) return el;
    el = document.createElement("button");
    el.type = "button";
    el.id = "sidebar-overlay";
    el.className = "sidebar-overlay";
    el.setAttribute("aria-label", "メニューを閉じる");
    el.addEventListener("click", closeSidebar);
    document.body.appendChild(el);
    return el;
  }

  function ensureMenuBtn() {
    const topbar = document.querySelector(".topbar");
    if (!topbar) return null;
    let btn = document.getElementById("topbar-menu-open");
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.id = "topbar-menu-open";
      btn.className = "topbar-menu-btn";
      btn.setAttribute("aria-label", "メニュー");
      btn.innerHTML = "<span></span><span></span><span></span>";
      btn.addEventListener("click", () => {
        document.body.classList.toggle("sidebar-open");
      });
      topbar.prepend(btn);
    }
    return btn;
  }

  function closeSidebar() {
    document.body.classList.remove("sidebar-open");
  }

  function sync() {
    const compact = COMPACT_MQ.matches;
    document.body.classList.toggle("is-compact", compact);
    ensureOverlay();
    const btn = ensureMenuBtn();
    if (btn) {
      if (compact) btn.removeAttribute("hidden");
      else btn.setAttribute("hidden", "");
    }
    if (!compact) {
      closeSidebar();
      setRail(localStorage.getItem(RAIL_KEY) === "1");
    } else {
      document.body.classList.remove("sidebar-rail");
    }
    if (sidebar()) {
      sidebar().setAttribute("aria-hidden", compact && !document.body.classList.contains("sidebar-open") ? "true" : "false");
    }
  }

  COMPACT_MQ.addEventListener("change", sync);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSidebar();
  });

  window.sidebarRail = { isRailEnabled, setRail };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initRailToggle();
      sync();
    });
  } else {
    initRailToggle();
    sync();
  }
})();
