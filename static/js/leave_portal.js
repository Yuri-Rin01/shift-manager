const STORAGE_KEY = "leave_portal_staff_id";
const REQUEST_OPTIONS = window.PORTAL_REQUEST_OPTIONS ?? [];
const PORTAL_SETTINGS = window.PORTAL_SETTINGS ?? {};

const TYPE_CLASS = {
  off: "type-off",
  paid_leave: "type-paid_leave",
  half_leave: "type-half_leave",
};

const TYPE_COLORS = {
  off: "#f59e0b",
  paid_leave: "#16a34a",
  half_leave: "#0891b2",
};

const FLICK_MAX_OPTIONS = 8;
const FLICK_MIN_DISTANCE = 28;
const POINTER_MOVE_CANCEL_PX = 12;
const TAP_CYCLE_DELAY_MS = 220;

const staffSelectPanel = document.getElementById("staff-select-panel");
const calendarPanel = document.getElementById("calendar-panel");
const staffSearch = document.getElementById("staff-search");
const staffIdInput = document.getElementById("staff-id");
const staffSuggestions = document.getElementById("staff-suggestions");
const staffMatchHint = document.getElementById("staff-match-hint");
const btnStartPortal = document.getElementById("btn-start-portal");
const btnChangeStaff = document.getElementById("btn-change-staff");
const btnPrevMonth = document.getElementById("btn-prev-month");
const btnNextMonth = document.getElementById("btn-next-month");
const portalStaffName = document.getElementById("portal-staff-name");
const portalPeriodLabel = document.getElementById("portal-period-label");
const portalMonthNavLabel = document.getElementById("portal-month-nav-label");
const portalDeadlineNote = document.getElementById("portal-deadline-note");
const portalLegend = document.getElementById("portal-legend");
const portalCalendarGrid = document.getElementById("portal-calendar-grid");
const portalRequestCount = document.getElementById("portal-request-count");
const portalAlert = document.getElementById("portal-alert");

let staffList = [];
let staffSuggestionIndex = -1;
let currentStaffId = null;
let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth() + 1;
let calendarData = null;

let flickPad = null;
let flickBackdrop = null;
let activeDayButton = null;
let dayPointer = null;
let dayTapTimer = null;

function flickInputEnabled() {
  return PORTAL_SETTINGS.cell_flick_input_enabled !== false;
}

function longPressMs() {
  const ms = Number(PORTAL_SETTINGS.cell_long_press_ms);
  if (!Number.isFinite(ms)) return 450;
  return Math.min(1500, Math.max(300, ms));
}

function showAlert(message, type = "info") {
  if (!portalAlert) return;
  portalAlert.textContent = message;
  portalAlert.className = `portal-alert is-${type}`;
  portalAlert.classList.remove("hidden");
  window.setTimeout(() => portalAlert.classList.add("hidden"), 4000);
}

function optionLabel(key) {
  if (!key) return "×";
  return REQUEST_OPTIONS.find((item) => item.key === key)?.short_label ?? key;
}

function getFlickOptions() {
  const clearOption = { key: null, label: "解除", short_label: "×" };
  return [...REQUEST_OPTIONS, clearOption].slice(0, FLICK_MAX_OPTIONS);
}

function flickDirClass(key) {
  if (!key) return "portal-flick-clear";
  return `portal-flick-${String(key).replaceAll("_", "-")}`;
}

function getFlickDirectionIndex(dx, dy) {
  const dist = Math.hypot(dx, dy);
  if (dist < FLICK_MIN_DISTANCE) return -1;
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
  return ((Math.round(angle / 45) + 2) % 8 + 8) % 8;
}

function ensureFlickPad() {
  if (flickPad) return flickPad;

  flickBackdrop = document.createElement("div");
  flickBackdrop.className = "portal-flick-backdrop hidden";
  flickBackdrop.setAttribute("aria-hidden", "true");
  flickBackdrop.addEventListener("click", () => {
    if (dayPointer?.flickActive) {
      closeFlickPad();
      resetDayPointer();
    }
  });
  document.body.appendChild(flickBackdrop);

  flickPad = document.createElement("div");
  flickPad.id = "portal-flick-pad";
  flickPad.className = "portal-flick-pad hidden";
  flickPad.setAttribute("role", "dialog");
  flickPad.setAttribute("aria-label", "フリックで休み希望を選択");
  document.body.appendChild(flickPad);
  return flickPad;
}

function hideFlickPad() {
  flickPad?.classList.add("hidden");
  flickPad?.replaceChildren();
  flickBackdrop?.classList.add("hidden");
}

function positionFlickPad(pad, button) {
  const rect = button.getBoundingClientRect();
  const size = 220;
  const margin = 8;
  let left = rect.left + rect.width / 2 - size / 2;
  let top = rect.top + rect.height / 2 - size / 2;

  left = Math.max(margin, Math.min(left, window.innerWidth - size - margin));
  top = Math.max(margin, Math.min(top, window.innerHeight - size - margin));

  pad.style.width = `${size}px`;
  pad.style.height = `${size}px`;
  pad.style.left = `${left}px`;
  pad.style.top = `${top}px`;
}

function updateFlickHighlight(directionIndex) {
  if (!flickPad) return;
  flickPad.querySelectorAll(".portal-flick-dir").forEach((node) => {
    const index = Number(node.dataset.dirIndex);
    node.classList.toggle("is-active", index === directionIndex);
  });
  const center = flickPad.querySelector(".portal-flick-center-symbol");
  const options = getFlickOptions();
  if (!center) return;
  if (directionIndex >= 0 && directionIndex < options.length) {
    center.textContent = options[directionIndex].short_label;
    center.style.color = options[directionIndex].key ? TYPE_COLORS[options[directionIndex].key] ?? "#0f172a" : "#64748b";
  } else {
    const currentType = getDayButtonType(activeDayButton);
    center.textContent = optionLabel(currentType);
    center.style.color = currentType ? TYPE_COLORS[currentType] ?? "#0f172a" : "#64748b";
  }
}

function getDayButtonType(button) {
  if (!button || !calendarData) return null;
  const day = calendarData.days.find((item) => item.date === button.dataset.date);
  return day?.request?.request_type ?? null;
}

function openFlickPad(button) {
  if (activeDayButton && activeDayButton !== button) {
    closeFlickPad();
  }

  activeDayButton = button;
  button.classList.add("is-editing");

  const pad = ensureFlickPad();
  const options = getFlickOptions();
  const currentType = getDayButtonType(button);
  const centerX = 110;
  const centerY = 110;
  const radius = 78;

  pad.replaceChildren();

  const center = document.createElement("div");
  center.className = "portal-flick-center";
  const centerSymbol = document.createElement("span");
  centerSymbol.className = "portal-flick-center-symbol";
  centerSymbol.textContent = optionLabel(currentType);
  centerSymbol.style.color = currentType ? TYPE_COLORS[currentType] ?? "#0f172a" : "#64748b";
  const centerHint = document.createElement("span");
  centerHint.className = "portal-flick-center-hint";
  centerHint.textContent = "方向へスライド";
  center.append(centerSymbol, centerHint);
  pad.appendChild(center);

  options.forEach((option, index) => {
    const angle = (-90 + index * 45) * (Math.PI / 180);
    const left = centerX + radius * Math.cos(angle) - 28;
    const top = centerY + radius * Math.sin(angle) - 28;

    const node = document.createElement("div");
    node.className = `portal-flick-dir ${flickDirClass(option.key)}`;
    node.dataset.dirIndex = String(index);

    const symbolSpan = document.createElement("span");
    symbolSpan.className = "portal-flick-dir-symbol";
    symbolSpan.textContent = option.short_label;
    symbolSpan.style.color = option.key ? TYPE_COLORS[option.key] ?? "#0f172a" : "#64748b";

    const labelSpan = document.createElement("span");
    labelSpan.className = "portal-flick-dir-label";
    labelSpan.textContent = option.label;

    node.append(symbolSpan, labelSpan);
    node.style.left = `${left}px`;
    node.style.top = `${top}px`;
    pad.appendChild(node);
  });

  flickBackdrop?.classList.remove("hidden");
  pad.classList.remove("hidden");
  window.requestAnimationFrame(() => positionFlickPad(pad, button));
}

function closeFlickPad() {
  hideFlickPad();
  if (activeDayButton) {
    activeDayButton.classList.remove("is-editing");
    activeDayButton = null;
  }
}

function resetDayPointer() {
  if (dayPointer?.longPressTimer) {
    clearTimeout(dayPointer.longPressTimer);
  }
  dayPointer = null;
}

function isDayEditable(day) {
  if (!day) return false;
  return !day.is_past && day.request?.status !== "approved";
}

function renderLegend() {
  if (!portalLegend) return;
  portalLegend.innerHTML = [
    ...REQUEST_OPTIONS.map(
      (item) => `
      <span class="portal-legend-item">
        <span class="portal-legend-swatch" style="background:${TYPE_COLORS[item.key] ?? "#94a3b8"}"></span>
        ${item.label}
      </span>`
    ),
    '<span class="portal-legend-item"><span class="portal-legend-swatch" style="background:#e2e8f0"></span>長押し→フリック</span>',
  ].join("");
}

function getStoredStaffId() {
  const raw = localStorage.getItem(STORAGE_KEY);
  const parsed = Number.parseInt(raw ?? "", 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function storeStaffId(staffId) {
  localStorage.setItem(STORAGE_KEY, String(staffId));
}

function clearStoredStaffId() {
  localStorage.removeItem(STORAGE_KEY);
}

function staffMeta(staff) {
  const floors = (staff.departments ?? []).filter(Boolean).join("・") || "未設定";
  return `${floors} / ${staff.job_type || "未設定"}`;
}

function staffSearchText(staff) {
  return `${staff.name} ${staffMeta(staff)}`;
}

function normalizeQuery(value) {
  return String(value ?? "").trim().replace(/\s+/g, "");
}

function filterStaffList(query) {
  const normalized = normalizeQuery(query);
  if (!normalized) return staffList.slice(0, 12);
  return staffList
    .map((staff) => {
      const name = staff.name ?? "";
      const compactName = normalizeQuery(name);
      const fullText = normalizeQuery(staffSearchText(staff));
      let score = 0;
      if (compactName === normalized) score = 100;
      else if (compactName.startsWith(normalized)) score = 80;
      else if (compactName.includes(normalized)) score = 60;
      else if (fullText.includes(normalized)) score = 40;
      return { staff, score };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.staff.name.localeCompare(b.staff.name, "ja"))
    .map((item) => item.staff)
    .slice(0, 12);
}

function setStaffMatchHint(message, tone = "") {
  if (!staffMatchHint) return;
  staffMatchHint.textContent = message;
  staffMatchHint.className = `portal-staff-hint${tone ? ` is-${tone}` : ""}`;
}

function setStartEnabled(enabled) {
  if (btnStartPortal) btnStartPortal.disabled = !enabled;
}

function clearStaffSelection({ clearInput = false } = {}) {
  if (staffIdInput) staffIdInput.value = "";
  if (clearInput && staffSearch) staffSearch.value = "";
  staffSearch?.classList.remove("is-matched", "is-ambiguous");
  staffSuggestionIndex = -1;
  hideStaffSuggestions();
  setStartEnabled(false);
}

function selectStaff(staff, { silent = false } = {}) {
  if (!staff) return;
  if (staffSearch) {
    staffSearch.value = staff.name;
    staffSearch.classList.remove("is-ambiguous");
    staffSearch.classList.add("is-matched");
    staffSearch.setAttribute("aria-expanded", "false");
  }
  if (staffIdInput) staffIdInput.value = String(staff.id);
  setStaffMatchHint(`選択中: ${staff.name}（${staffMeta(staff)}）`, "ok");
  setStartEnabled(true);
  hideStaffSuggestions();
  if (!silent) staffSearch?.focus();
}

function hideStaffSuggestions() {
  staffSuggestions?.classList.add("hidden");
  staffSuggestions?.replaceChildren();
  staffSuggestionIndex = -1;
  staffSearch?.setAttribute("aria-expanded", "false");
}

function renderStaffSuggestions(matches) {
  if (!staffSuggestions) return;
  staffSuggestions.replaceChildren();
  if (!matches.length) {
    staffSuggestions.classList.add("hidden");
    staffSearch?.setAttribute("aria-expanded", "false");
    return;
  }
  matches.forEach((staff, index) => {
    const item = document.createElement("li");
    item.className = `portal-staff-suggestion${index === staffSuggestionIndex ? " is-active" : ""}`;
    item.setAttribute("role", "option");
    item.dataset.staffId = String(staff.id);
    item.innerHTML = `
      <span class="portal-staff-suggestion-name">${staff.name}</span>
      <span class="portal-staff-suggestion-meta">${staffMeta(staff)}</span>
    `;
    item.addEventListener("mousedown", (event) => {
      event.preventDefault();
      selectStaff(staff);
    });
    staffSuggestions.appendChild(item);
  });
  staffSuggestions.classList.remove("hidden");
  staffSearch?.setAttribute("aria-expanded", "true");
}

function syncStaffInputState() {
  const query = staffSearch?.value ?? "";
  const normalized = normalizeQuery(query);
  if (!normalized) {
    clearStaffSelection();
    setStaffMatchHint("名前の一部を入力すると候補が絞り込まれます。");
    return;
  }

  const exactMatches = staffList.filter((staff) => normalizeQuery(staff.name) === normalized);
  const matches = filterStaffList(query);

  if (exactMatches.length === 1) {
    const staff = exactMatches[0];
    if (staffIdInput?.value !== String(staff.id)) {
      if (staffIdInput) staffIdInput.value = String(staff.id);
      staffSearch.classList.remove("is-ambiguous");
      staffSearch.classList.add("is-matched");
      setStaffMatchHint(`選択中: ${staff.name}（${staffMeta(staff)}）`, "ok");
      setStartEnabled(true);
    }
    hideStaffSuggestions();
    return;
  }

  if (staffIdInput) staffIdInput.value = "";
  staffSearch.classList.remove("is-matched");
  setStartEnabled(false);

  if (matches.length === 1 && normalizeQuery(matches[0].name).startsWith(normalized)) {
    staffSearch.classList.remove("is-ambiguous");
    setStaffMatchHint(`候補: ${matches[0].name}（タップまたは Enter で確定）`);
    staffSuggestionIndex = 0;
    renderStaffSuggestions(matches);
    return;
  }

  if (matches.length > 0) {
    staffSearch.classList.add("is-ambiguous");
    setStaffMatchHint(`${matches.length}件の候補があります。一覧から選ぶか、名前を続けて入力してください。`, "warn");
    staffSuggestionIndex = Math.max(0, staffSuggestionIndex);
    if (staffSuggestionIndex >= matches.length) staffSuggestionIndex = 0;
    renderStaffSuggestions(matches);
    return;
  }

  staffSearch.classList.add("is-ambiguous");
  hideStaffSuggestions();
  setStaffMatchHint("一致する職員が見つかりません。名前を確認してください。", "error");
}

function getResolvedStaffId() {
  const fromHidden = Number.parseInt(staffIdInput?.value ?? "", 10);
  if (Number.isFinite(fromHidden)) return fromHidden;
  const query = staffSearch?.value ?? "";
  const exactMatches = staffList.filter((staff) => normalizeQuery(staff.name) === normalizeQuery(query));
  if (exactMatches.length === 1) return exactMatches[0].id;
  const matches = filterStaffList(query);
  if (matches.length === 1) return matches[0].id;
  return null;
}

function initStaffPicker() {
  staffSearch?.addEventListener("input", () => {
    staffSuggestionIndex = 0;
    syncStaffInputState();
  });

  staffSearch?.addEventListener("focus", () => {
    if (!staffSearch.value.trim()) {
      renderStaffSuggestions(staffList.slice(0, 12));
      setStaffMatchHint("一覧から選ぶか、名前を入力してください。");
      return;
    }
    syncStaffInputState();
  });

  staffSearch?.addEventListener("blur", () => {
    window.setTimeout(() => hideStaffSuggestions(), 120);
  });

  staffSearch?.addEventListener("keydown", (event) => {
    const getItems = () =>
      staffSuggestions ? Array.from(staffSuggestions.querySelectorAll(".portal-staff-suggestion")) : [];

    if (event.key === "ArrowDown") {
      event.preventDefault();
      const matches = filterStaffList(staffSearch.value);
      if (!matches.length) return;
      staffSuggestionIndex = staffSuggestionIndex < 0 ? 0 : (staffSuggestionIndex + 1) % matches.length;
      renderStaffSuggestions(matches);
      getItems()[staffSuggestionIndex]?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      const matches = filterStaffList(staffSearch.value);
      if (!matches.length) return;
      staffSuggestionIndex =
        staffSuggestionIndex < 0 ? matches.length - 1 : (staffSuggestionIndex - 1 + matches.length) % matches.length;
      renderStaffSuggestions(matches);
      getItems()[staffSuggestionIndex]?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const matches = filterStaffList(staffSearch.value);
      const pick = matches[staffSuggestionIndex] ?? matches[0];
      if (pick) {
        selectStaff(pick);
        return;
      }
      const staffId = getResolvedStaffId();
      if (Number.isFinite(staffId)) {
        startPortal(staffId);
      } else {
        showAlert("職員を候補から選ぶか、名前を正確に入力してください", "error");
      }
      return;
    }
    if (event.key === "Escape") {
      hideStaffSuggestions();
    }
  });
}

async function loadStaffList() {
  const response = await fetch("/api/staff");
  if (!response.ok) throw new Error("職員一覧の取得に失敗しました");
  staffList = await response.json();
  if (staffSearch) {
    staffSearch.disabled = false;
    staffSearch.placeholder = "名前を入力（候補が表示されます）";
  }
  setStartEnabled(false);
  setStaffMatchHint("名前の一部を入力すると候補が絞り込まれます。");
}

function showStaffSelect() {
  staffSelectPanel?.classList.remove("hidden");
  calendarPanel?.classList.add("hidden");
  currentStaffId = null;
  clearStaffSelection({ clearInput: true });
}

function showCalendar() {
  staffSelectPanel?.classList.add("hidden");
  calendarPanel?.classList.remove("hidden");
}

function changeMonth(delta) {
  currentMonth += delta;
  while (currentMonth < 1) {
    currentMonth += 12;
    currentYear -= 1;
  }
  while (currentMonth > 12) {
    currentMonth -= 12;
    currentYear += 1;
  }
  loadCalendar();
}

function cycleRequestType(currentType) {
  const keys = REQUEST_OPTIONS.map((item) => item.key);
  if (!keys.length) return null;
  if (!currentType) return keys[0];
  const index = keys.indexOf(currentType);
  if (index === -1) return keys[0];
  return index === keys.length - 1 ? null : keys[index + 1];
}

function leadingEmptyCells(days) {
  if (!days.length) return 0;
  const firstWeekday = new Date(`${days[0].date}T00:00:00`).getDay();
  return firstWeekday;
}

function syncRequestCount() {
  if (!portalRequestCount || !calendarData) return;
  const count = calendarData.requests.filter(
    (item) => item.status === "pending" || item.status === "approved"
  ).length;
  const limit = calendarData.limit_info;
  if (limit && Number.isFinite(limit.max_total)) {
    portalRequestCount.textContent = `希望: ${limit.total ?? count}/${limit.max_total}件`;
    portalRequestCount.classList.toggle("is-over-limit", Boolean(limit.is_over_limit));
  } else {
    portalRequestCount.textContent = `希望: ${count}件`;
    portalRequestCount.classList.remove("is-over-limit");
  }
}

function syncLimitWarning() {
  const limit = calendarData?.limit_info;
  if (!portalDeadlineNote || !limit) return;
  if (limit.is_over_limit && limit.over_limit_message) {
    portalDeadlineNote.textContent = limit.over_limit_message;
    portalDeadlineNote.classList.remove("hidden");
    portalDeadlineNote.classList.add("is-warn");
    return true;
  }
  return false;
}

function applyLocalRequest(shiftDate, requestPayload) {
  if (!calendarData) return;
  const day = calendarData.days.find((item) => item.date === shiftDate);
  if (day) {
    day.request = requestPayload;
  }
  if (requestPayload) {
    const index = calendarData.requests.findIndex((item) => item.shift_date === shiftDate);
    if (index >= 0) {
      calendarData.requests[index] = requestPayload;
    } else {
      calendarData.requests.push(requestPayload);
    }
  } else {
    calendarData.requests = calendarData.requests.filter((item) => item.shift_date !== shiftDate);
  }
  syncRequestCount();
}

function renderCalendar() {
  if (!portalCalendarGrid || !calendarData) return;

  portalStaffName.textContent = calendarData.staff_name;
  portalPeriodLabel.textContent = calendarData.period_label;
  portalMonthNavLabel.textContent = `${calendarData.year}年${calendarData.month}月`;
  syncRequestCount();

  const limitShown = syncLimitWarning();
  if (!limitShown && portalDeadlineNote) {
    if (calendarData.is_past_deadline) {
      portalDeadlineNote.textContent = `提出期限（毎月${calendarData.deadline_day_of_month}日）を過ぎています。変更は管理者へご相談ください。`;
      portalDeadlineNote.classList.remove("hidden");
      portalDeadlineNote.classList.add("is-warn");
    } else {
      portalDeadlineNote.textContent = `提出期限: 毎月${calendarData.deadline_day_of_month}日まで`;
      portalDeadlineNote.classList.remove("hidden", "is-warn");
    }
  }

  const blanks = leadingEmptyCells(calendarData.days);
  const cells = [];

  for (let index = 0; index < blanks; index += 1) {
    cells.push('<div class="portal-day is-outside" aria-hidden="true"></div>');
  }

  for (const day of calendarData.days) {
    const request = day.request;
    const requestType = request?.request_type ?? null;
    const status = request?.status ?? null;
    const badge = requestType
      ? `<span class="portal-day-badge ${TYPE_CLASS[requestType] ?? ""}">${optionLabel(requestType)}</span>`
      : "";
    const classes = [
      "portal-day",
      day.is_saturday ? "is-saturday" : "",
      day.is_sunday ? "is-sunday" : "",
      day.is_today ? "is-today" : "",
      day.is_past ? "is-past" : "",
      status === "pending" ? "is-pending" : "",
      status === "approved" ? "is-approved" : "",
    ]
      .filter(Boolean)
      .join(" ");

    const disabled = !isDayEditable(day);
    cells.push(`
      <button
        type="button"
        class="${classes}"
        data-date="${day.date}"
        ${disabled ? "disabled" : ""}
        aria-label="${day.month}月${day.day}日${requestType ? ` ${optionLabel(requestType)}` : ""}"
      >
        <span class="portal-day-num">${day.day}</span>
        ${badge}
      </button>`);
  }

  portalCalendarGrid.innerHTML = cells.join("");
}

async function loadCalendar() {
  if (!currentStaffId) return;
  const response = await fetch(
    `/api/calendar?staff_id=${currentStaffId}&year=${currentYear}&month=${currentMonth}`
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    showAlert(error.detail ?? "カレンダーの取得に失敗しました", "error");
    return;
  }
  calendarData = await response.json();
  renderCalendar();
  if (calendarData.limit_info?.is_over_limit) {
    showAlert(calendarData.limit_info.over_limit_message, "warn");
  }
}

async function saveDayRequest(shiftDate, requestType, options = {}) {
  if (!currentStaffId) return false;

  if (!requestType) {
    const response = await fetch(
      `/api/requests?staff_id=${currentStaffId}&shift_date=${shiftDate}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      showAlert(error.detail ?? "希望の取消に失敗しました", "error");
      return false;
    }
    applyLocalRequest(shiftDate, null);
    await loadCalendar();
    if (!options.silent) showAlert("希望を取り消しました", "success");
    return true;
  }

  const response = await fetch("/api/requests", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      staff_id: currentStaffId,
      shift_date: shiftDate,
      request_type: requestType,
      note: "",
    }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    showAlert(error.detail ?? "希望の保存に失敗しました", "error");
    return false;
  }
  const saved = await response.json();
  applyLocalRequest(shiftDate, saved);
  await loadCalendar();
  if (!options.silent) showAlert("希望を保存しました", "success");
  return true;
}

async function cycleDayRequest(button) {
  const shiftDate = button.dataset.date;
  const day = calendarData?.days.find((item) => item.date === shiftDate);
  if (!isDayEditable(day)) return;
  const currentType = day?.request?.request_type ?? null;
  const nextType = cycleRequestType(currentType);
  await saveDayRequest(shiftDate, nextType);
}

async function startPortal(staffId) {
  currentStaffId = staffId;
  storeStaffId(staffId);
  showCalendar();
  await loadCalendar();
}

function initDayPointerHandlers() {
  portalCalendarGrid?.addEventListener("pointerdown", (event) => {
    const button = event.target.closest(".portal-day[data-date]");
    if (!button || button.disabled || !portalCalendarGrid.contains(button)) return;
    if (event.button !== 0) return;

    if (dayTapTimer) {
      clearTimeout(dayTapTimer);
      dayTapTimer = null;
    }
    resetDayPointer();

    const day = calendarData?.days.find((item) => item.date === button.dataset.date);
    if (!isDayEditable(day)) return;

    const rect = button.getBoundingClientRect();
    dayPointer = {
      button,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: rect.left + rect.width / 2,
      originY: rect.top + rect.height / 2,
      longPressTimer: null,
      flickActive: false,
      directionIndex: -1,
      cancelled: false,
    };

    button.setPointerCapture?.(event.pointerId);

    if (flickInputEnabled()) {
      dayPointer.longPressTimer = window.setTimeout(() => {
        if (!dayPointer || dayPointer.cancelled || dayPointer.button !== button) return;
        dayPointer.flickActive = true;
        dayPointer.directionIndex = -1;
        openFlickPad(button);
        window.requestAnimationFrame(() => {
          if (!dayPointer?.flickActive || !flickPad) return;
          const padRect = flickPad.getBoundingClientRect();
          dayPointer.originX = padRect.left + padRect.width / 2;
          dayPointer.originY = padRect.top + padRect.height / 2;
        });
        navigator.vibrate?.(12);
      }, longPressMs());
    }
  });

  portalCalendarGrid?.addEventListener("pointermove", (event) => {
    if (!dayPointer || event.pointerId !== dayPointer.pointerId) return;

    const dx = event.clientX - dayPointer.startX;
    const dy = event.clientY - dayPointer.startY;

    if (!dayPointer.flickActive && dayPointer.longPressTimer) {
      if (Math.hypot(dx, dy) > POINTER_MOVE_CANCEL_PX) {
        clearTimeout(dayPointer.longPressTimer);
        dayPointer.longPressTimer = null;
        dayPointer.cancelled = true;
      }
      return;
    }

    if (!dayPointer.flickActive) return;

    event.preventDefault();
    const fdx = event.clientX - dayPointer.originX;
    const fdy = event.clientY - dayPointer.originY;
    const dirIndex = getFlickDirectionIndex(fdx, fdy);
    if (dirIndex !== dayPointer.directionIndex) {
      dayPointer.directionIndex = dirIndex;
      updateFlickHighlight(dirIndex);
    }
  });

  const finishDayPointer = async (event) => {
    if (!dayPointer || event.pointerId !== dayPointer.pointerId) return;

    const { button, longPressTimer, flickActive, directionIndex, cancelled, startX, startY } = dayPointer;

    if (longPressTimer) {
      clearTimeout(longPressTimer);
    }

    button.releasePointerCapture?.(event.pointerId);

    if (flickActive) {
      const options = getFlickOptions();
      if (directionIndex >= 0 && directionIndex < options.length) {
        const selected = options[directionIndex];
        closeFlickPad();
        await saveDayRequest(button.dataset.date, selected.key, { silent: true });
      } else {
        closeFlickPad();
      }
      resetDayPointer();
      return;
    }

    if (
      !cancelled &&
      Math.hypot(event.clientX - startX, event.clientY - startY) <= POINTER_MOVE_CANCEL_PX
    ) {
      dayTapTimer = window.setTimeout(async () => {
        dayTapTimer = null;
        await cycleDayRequest(button);
      }, TAP_CYCLE_DELAY_MS);
    }

    resetDayPointer();
  };

  portalCalendarGrid?.addEventListener("pointerup", finishDayPointer);
  portalCalendarGrid?.addEventListener("pointercancel", finishDayPointer);
}

btnStartPortal?.addEventListener("click", async () => {
  const staffId = getResolvedStaffId();
  if (!Number.isFinite(staffId)) {
    showAlert("職員を候補から選ぶか、名前を正確に入力してください", "error");
    syncStaffInputState();
    staffSearch?.focus();
    return;
  }
  await startPortal(staffId);
});

btnChangeStaff?.addEventListener("click", () => {
  clearStoredStaffId();
  showStaffSelect();
});

btnPrevMonth?.addEventListener("click", () => changeMonth(-1));
btnNextMonth?.addEventListener("click", () => changeMonth(1));

window.addEventListener("resize", () => {
  if (activeDayButton && flickPad && !flickPad.classList.contains("hidden")) {
    positionFlickPad(flickPad, activeDayButton);
  }
});

async function initPortal() {
  renderLegend();
  initDayPointerHandlers();
  initStaffPicker();
  try {
    await loadStaffList();
  } catch (error) {
    showAlert(error.message ?? "初期化に失敗しました", "error");
    return;
  }

  const storedId = getStoredStaffId();
  const storedStaff = staffList.find((staff) => staff.id === storedId);
  if (storedStaff) {
    selectStaff(storedStaff, { silent: true });
    await startPortal(storedStaff.id);
    return;
  }
  showStaffSelect();
}

initPortal();
