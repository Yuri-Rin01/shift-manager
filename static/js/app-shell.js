(() => {
  const COMPACT_MQ = window.matchMedia("(max-width: 900px)");

  function sidebar() {
    return document.querySelector(".sidebar");
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
    if (!compact) closeSidebar();
    if (sidebar()) {
      sidebar().setAttribute("aria-hidden", compact && !document.body.classList.contains("sidebar-open") ? "true" : "false");
    }
  }

  COMPACT_MQ.addEventListener("change", sync);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSidebar();
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync);
  } else {
    sync();
  }
})();
