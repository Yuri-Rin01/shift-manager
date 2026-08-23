(() => {
  const STORAGE_KEY = "shift-manager.sidebar-login-demo";

  function readSession() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function writeSession(data) {
    if (!data) {
      sessionStorage.removeItem(STORAGE_KEY);
      return;
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }

  function avatarInitial(name) {
    const text = String(name || "").trim();
    return text ? text.charAt(0) : "?";
  }

  function initPanel(panel) {
    if (!panel || panel.dataset.loginPanelInit === "1") return;
    panel.dataset.loginPanelInit = "1";

    const implemented = panel.dataset.loginImplemented === "true";
    const defaultAdmin = panel.dataset.defaultAdmin || "管理者";
    const defaultFacility = panel.dataset.defaultFacility || "";
    const defaultLabel = panel.dataset.defaultLabel || "";

    const toggle = panel.querySelector(".login-panel-toggle");
    const body = panel.querySelector(".login-panel-body");
    const avatar = panel.querySelector(".login-panel-avatar");
    const facilityEl = panel.querySelector(".login-panel-facility");
    const userEl = panel.querySelector(".login-panel-user");
    const badge = panel.querySelector(".login-panel-badge");
    const sessionView = panel.querySelector(".login-panel-session-view");
    const loggedInView = panel.querySelector(".login-panel-logged-in");
    const form = panel.querySelector(".login-panel-form");
    const emailInput = panel.querySelector('[name="login_email"]');
    const passwordInput = panel.querySelector('[name="login_password"]');
    const loginBtn = panel.querySelector(".login-panel-btn-login");
    const logoutBtn = panel.querySelector(".login-panel-btn-logout");
    const errorEl = panel.querySelector(".login-panel-error");

    function setOpen(open) {
      panel.classList.toggle("is-open", open);
      if (body) body.hidden = !open;
      if (toggle) toggle.setAttribute("aria-expanded", open ? "true" : "false");
    }

    function setError(message) {
      if (!errorEl) return;
      errorEl.textContent = message || "";
      errorEl.hidden = !message;
    }

    function render(session) {
      const displayName = session?.displayName || defaultAdmin;
      const facilityName = session?.facilityName || defaultFacility;
      const facilityLabel = session?.facilityLabel || defaultLabel;

      if (avatar) avatar.textContent = avatarInitial(displayName);
      if (facilityEl) facilityEl.textContent = facilityName;
      if (userEl) userEl.textContent = `${facilityLabel} / ${displayName}`;

      const loggedIn = Boolean(session?.loggedIn);
      if (sessionView) sessionView.hidden = loggedIn;
      if (loggedInView) loggedInView.hidden = !loggedIn;

      if (badge) {
        if (implemented) {
          badge.hidden = true;
        } else if (loggedIn) {
          badge.hidden = false;
          badge.className = "login-panel-badge is-success";
          badge.textContent = "UIプレビュー: ログイン状態（サーバー未連携）";
        } else {
          badge.hidden = false;
          badge.className = "login-panel-badge";
          badge.textContent = "ログイン機能は準備中です。UIのみ表示しています。";
        }
      }

      if (loginBtn) {
        loginBtn.disabled = !implemented;
        loginBtn.title = implemented ? "" : "管理者ログイン実装後に有効化予定";
      }
      if (logoutBtn) {
        logoutBtn.disabled = !loggedIn;
        logoutBtn.title = loggedIn ? "" : "ログイン後に利用できます";
      }
    }

    toggle?.addEventListener("click", () => {
      setOpen(!panel.classList.contains("is-open"));
    });

    form?.addEventListener("submit", (event) => {
      event.preventDefault();
      setError("");
      if (!implemented) return;

      const email = String(emailInput?.value || "").trim();
      const password = String(passwordInput?.value || "");
      if (!email || !password) {
        setError("メールアドレスとパスワードを入力してください。");
        return;
      }

      writeSession({
        loggedIn: true,
        displayName: email.split("@")[0] || defaultAdmin,
        facilityName: defaultFacility,
        facilityLabel: defaultLabel,
      });
      render(readSession());
      setOpen(false);
    });

    logoutBtn?.addEventListener("click", () => {
      writeSession(null);
      if (form) form.reset();
      setError("");
      render(null);
      setOpen(false);
    });

    const session = readSession();
    render(session?.loggedIn ? session : null);
    setOpen(false);
  }

  function initAll() {
    document.querySelectorAll(".sidebar-login-panel").forEach(initPanel);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
