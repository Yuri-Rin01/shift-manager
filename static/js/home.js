const STORAGE_KEY = "shift-display-prefs";
const serverDefaults = window.APP_SETTINGS ?? {};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function defaultPrefs() {
  return {
    showJob: serverDefaults.default_show_job_column ?? true,
    colorCells: serverDefaults.default_color_cells ?? true,
    showSummary: serverDefaults.default_show_summary ?? true,
    tableZoom: (serverDefaults.default_table_zoom ?? 100) / 100,
  };
}

const printModal = document.getElementById("print-modal");
const printButton = document.getElementById("btn-print-settings");
const previewNote = document.getElementById("print-preview-note");
const previewRefresh = document.getElementById("btn-preview-refresh");
const shiftCalendar = document.getElementById("shift-calendar");
const tableWrap = shiftCalendar?.querySelector(".table-wrap");
const zoomControls = document.getElementById("calendar-zoom-controls");
const zoomInBtn = document.getElementById("calendar-zoom-in");
const zoomOutBtn = document.getElementById("calendar-zoom-out");
const calendarZoomSelect = document.getElementById("calendar-zoom-select");
const calendarSortSelect = document.getElementById("calendar-sort-mode");
const homeColorCells = document.getElementById("home-color-cells");
const homeShowJob = document.getElementById("home-show-job");
const homeShowSummary = document.getElementById("home-show-summary");

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2;
const ZOOM_STEP = 0.1;
const SUPPORTS_CSS_ZOOM = typeof CSS !== "undefined" && CSS.supports?.("zoom", "1");

let tableZoom = defaultPrefs().tableZoom;
const previewBox = document.getElementById("print-preview-box");
const printColJob = document.getElementById("print-col-job");
const printColorMode = document.getElementById("print-color-mode");
const btnPrevMonth = document.getElementById("btn-prev-month");
const btnNextMonth = document.getElementById("btn-next-month");
const btnPrevYear = document.getElementById("btn-prev-year");
const btnNextYear = document.getElementById("btn-next-year");
const btnShiftUndo = document.getElementById("btn-shift-undo");
const btnShiftRedo = document.getElementById("btn-shift-redo");

const undoStack = [];
const redoStack = [];
const MAX_SHIFT_HISTORY = 100;
let historyApplying = false;

const SORT_TO_DISPLAY = { position: "position", dept: "dept", job: "job", name: "all" };
const DISPLAY_TO_SORT = { position: "position", dept: "dept", job: "job", all: "name" };
const CALENDAR_POSITION_ORDER = window.STAFF_POSITION_ORDER ?? [];
const DEPT_ORDER = window.DEPT_ORDER ?? [];
const JOB_ORDER = window.JOB_ORDER ?? [];

function getCalendarYear() {
  return Number(window.CALENDAR_YEAR);
}

function getCalendarMonth() {
  return Number(window.CALENDAR_MONTH);
}

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function savePrefs(prefs) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

function getHomeDisplayInputs() {
  return {
    colorCells: document.getElementById("home-color-cells"),
    showJob: document.getElementById("home-show-job"),
    showSummary: document.getElementById("home-show-summary"),
  };
}

function getPrefs() {
  const defaults = defaultPrefs();
  const homeInputs = getHomeDisplayInputs();
  return {
    showJob: homeInputs.showJob?.checked ?? printColJob?.checked ?? defaults.showJob,
    colorCells: homeInputs.colorCells?.checked ?? printColorMode?.checked ?? defaults.colorCells,
    showSummary: homeInputs.showSummary?.checked ?? defaults.showSummary,
  };
}

function applyDisplayPrefs(prefs = getPrefs()) {
  if (shiftCalendar) {
    const foreignSheet = getCurrentSheetView() === "foreign-students";
    shiftCalendar.classList.toggle("hide-col-job", foreignSheet || !prefs.showJob);
    shiftCalendar.classList.toggle("hide-summary", foreignSheet || !prefs.showSummary);
    shiftCalendar.classList.toggle("color-cells", prefs.colorCells);
    shiftCalendar.classList.toggle("mono-cells", !prefs.colorCells);
  }
  if (previewBox?.querySelector(".shift-table")) {
    previewBox.classList.toggle("hide-col-job", !prefs.showJob);
    previewBox.classList.toggle("hide-summary", !prefs.showSummary);
    previewBox.classList.toggle("color-cells", prefs.colorCells);
    previewBox.classList.toggle("mono-cells", !prefs.colorCells);
  }
}

function syncControlsFromPrefs(prefs) {
  const homeInputs = getHomeDisplayInputs();
  if (homeInputs.showJob) homeInputs.showJob.checked = prefs.showJob;
  if (homeInputs.colorCells) homeInputs.colorCells.checked = prefs.colorCells;
  if (homeInputs.showSummary) homeInputs.showSummary.checked = prefs.showSummary;
  if (printColJob) printColJob.checked = prefs.showJob;
  if (printColorMode) printColorMode.checked = prefs.colorCells;
}

function updatePreviewNote() {
  if (!previewNote || !printModal) return;
  const paper = document.getElementById("print-paper")?.value ?? "A4 横";
  const scale = document.getElementById("print-scale")?.value ?? "100%";
  const prefs = getPrefs();
  const cols = ["職員名"];
  if (prefs.showJob) cols.push("職種");
  previewNote.textContent = `${paper} / ${scale} / ${cols.join("・")}${prefs.colorCells ? " / 色付き" : ""}`;
}

function getZoomOptions() {
  if (!calendarZoomSelect) return [];
  return [...calendarZoomSelect.options].map((option) => Number(option.value)).filter(Number.isFinite);
}

function nearestZoomPercent(pct) {
  const options = getZoomOptions();
  if (!options.length) return pct;
  return options.reduce(
    (best, value) => (Math.abs(value - pct) < Math.abs(best - pct) ? value : best),
    options[0]
  );
}

function syncZoomSelect() {
  if (!calendarZoomSelect) return;
  const pct = nearestZoomPercent(Math.round(tableZoom * 100));
  calendarZoomSelect.value = String(pct);
}

function applyTableZoom(zoom = tableZoom) {
  tableZoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom));
  if (tableWrap) {
    // Zoom the table, not the scrollport — zooming .table-wrap clips the bottom on iOS
    const table = tableWrap.querySelector(".shift-table");
    tableWrap.style.zoom = "";
    tableWrap.style.transform = "";
    tableWrap.style.transformOrigin = "";
    tableWrap.style.marginBottom = "";
    if (table) {
      if (SUPPORTS_CSS_ZOOM) {
        table.style.zoom = String(tableZoom);
        table.style.transform = "";
        table.style.transformOrigin = "";
        table.style.marginBottom = "";
      } else {
        table.style.zoom = "";
        table.style.transform = `scale(${tableZoom})`;
        table.style.transformOrigin = "top left";
        // transform does not expand layout; pad so the scroller can reach the bottom
        table.style.marginBottom = tableZoom > 1 ? `${Math.ceil(table.offsetHeight * (tableZoom - 1))}px` : "";
      }
    }
  }
  syncZoomSelect();
}

function stepZoom(direction) {
  const options = getZoomOptions();
  if (!options.length) {
    changeTableZoom(direction * ZOOM_STEP);
    return;
  }
  const current = nearestZoomPercent(Math.round(tableZoom * 100));
  const currentIndex = options.indexOf(current);
  const baseIndex = currentIndex >= 0 ? currentIndex : options.indexOf(nearestZoomPercent(100));
  const nextIndex = Math.min(options.length - 1, Math.max(0, baseIndex + direction));
  applyTableZoom(options[nextIndex] / 100);
  savePrefs({ ...loadPrefs(), ...getPrefs(), tableZoom });
}

function syncSortSegments(mode = getCurrentSortMode()) {
  document.querySelectorAll("[data-sort-mode]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.sortMode === mode);
  });
  updateSortSegmentIndicator(mode);
}

function updateSortSegmentIndicator(mode = getCurrentSortMode()) {
  const segment =
    document.querySelector("#home-filters-body .home-segment") ??
    document.querySelector(".home-segment");
  const indicator = segment?.querySelector(".home-segment-indicator");
  const active =
    segment?.querySelector(`[data-sort-mode="${mode}"]`) ??
    segment?.querySelector(".home-segment-btn.is-active");
  if (!segment || !indicator || !active) return;

  indicator.style.width = `${active.offsetWidth}px`;
  indicator.style.left = `${active.offsetLeft}px`;
  indicator.style.transform = "none";
  indicator.classList.add("is-visible");
}

function scheduleSortSegmentIndicatorUpdate() {
  requestAnimationFrame(() => {
    updateSortSegmentIndicator();
  });
}

function buildCalendarUrl(nextYear, nextMonth, displayMode) {
  const params = new URLSearchParams();
  params.set("year", String(nextYear));
  params.set("month", String(nextMonth));
  if (displayMode) {
    params.set("display", displayMode);
  }
  return `/?${params.toString()}`;
}

function navigateMonth(delta) {
  let nextYear = getCalendarYear();
  let nextMonth = getCalendarMonth() + delta;
  if (nextMonth < 1) {
    nextMonth = 12;
    nextYear -= 1;
  } else if (nextMonth > 12) {
    nextMonth = 1;
    nextYear += 1;
  }
  const displayMode = SORT_TO_DISPLAY[getCurrentSortMode()] ?? "";
  window.location.href = buildCalendarUrl(nextYear, nextMonth, displayMode);
}

function navigateYear(delta) {
  const nextYear = getCalendarYear() + delta;
  const nextMonth = getCalendarMonth();
  const displayMode = SORT_TO_DISPLAY[getCurrentSortMode()] ?? "";
  window.location.href = buildCalendarUrl(nextYear, nextMonth, displayMode);
}

function onHomeDisplayChange() {
  const prefs = getPrefs();
  savePrefs({ ...loadPrefs(), ...prefs, tableZoom });
  syncControlsFromPrefs(prefs);
  applyDisplayPrefs(prefs);
  updatePreviewNote();
}

function getCalendarSortSelect() {
  return document.getElementById("calendar-sort-mode");
}

function getCurrentSortMode() {
  return getCalendarSortSelect()?.value || serverDefaults.calendar_sort_mode || "dept";
}

function rowStaffName(row) {
  const nameCell = row.querySelector(".col-name");
  const link = nameCell?.querySelector(".staff-name-link");
  return (link?.textContent ?? nameCell?.textContent ?? "").trim();
}

function orderIndex(order, value) {
  const index = order.indexOf(value);
  return index < 0 ? 999 : index;
}

function compareCalendarRows(a, b, mode) {
  const nameA = rowStaffName(a);
  const nameB = rowStaffName(b);
  if (mode === "name") {
    return nameA.localeCompare(nameB, "ja");
  }
  if (mode === "position") {
    const positionOrder = Object.fromEntries(CALENDAR_POSITION_ORDER.map((label, index) => [label, index]));
    const rank = (value) => {
      if (!value) return 999;
      return positionOrder[value] ?? 998;
    };
    const posA = a.dataset.position ?? "";
    const posB = b.dataset.position ?? "";
    return rank(posA) - rank(posB) || nameA.localeCompare(nameB, "ja");
  }
  if (mode === "job") {
    const jobA = a.dataset.job ?? "";
    const jobB = b.dataset.job ?? "";
    const byJob = orderIndex(JOB_ORDER, jobA) - orderIndex(JOB_ORDER, jobB);
    return byJob || nameA.localeCompare(nameB, "ja");
  }
  const deptA = a.dataset.dept ?? "";
  const deptB = b.dataset.dept ?? "";
  const byDept = orderIndex(DEPT_ORDER, deptA) - orderIndex(DEPT_ORDER, deptB);
  return byDept || nameA.localeCompare(nameB, "ja");
}

function applyCalendarSort(mode = getCurrentSortMode()) {
  const tbody = shiftCalendar?.querySelector("tbody");
  if (!tbody) return;
  const rows = [...tbody.querySelectorAll("tr")];
  rows.sort((a, b) => compareCalendarRows(a, b, mode));
  rows.forEach((row) => tbody.appendChild(row));
}

function syncCalendarSortUrl(mode = getCurrentSortMode()) {
  const displayMode = SORT_TO_DISPLAY[mode] ?? "";
  const url = buildCalendarUrl(getCalendarYear(), getCalendarMonth(), displayMode);
  window.history.replaceState(null, "", url);
}

function resolveInitialSortMode() {
  const display = new URLSearchParams(window.location.search).get("display");
  if (display && DISPLAY_TO_SORT[display]) {
    return DISPLAY_TO_SORT[display];
  }
  const saved = loadPrefs().calendarSortMode;
  if (saved && SORT_TO_DISPLAY[saved]) {
    return saved;
  }
  return getCalendarSortSelect()?.value || serverDefaults.calendar_sort_mode || "dept";
}

function initSortState() {
  const mode = resolveInitialSortMode();
  const sortSelect = getCalendarSortSelect();
  if (sortSelect) {
    sortSelect.value = mode;
  }
  syncSortSegments(mode);
  applyCalendarSort(mode);
}

function getSelectedFilterValues(group) {
  const boxes = document.querySelectorAll(`[data-filter-group="${group}"] input[type="checkbox"]`);
  const selected = [...boxes].filter((box) => box.checked).map((box) => box.value);
  return selected;
}

function saveFilterPrefs() {
  savePrefs({
    ...loadPrefs(),
    ...getPrefs(),
    tableZoom,
    filterDepts: getSelectedFilterValues("dept"),
    filterJobs: getSelectedFilterValues("job"),
    filterPositions: getSelectedFilterValues("position"),
    calendarSortMode: getCurrentSortMode(),
  });
}

function setFilterGroupChecked(group, checked) {
  document
    .querySelectorAll(`[data-filter-group="${group}"] input[type="checkbox"]`)
    .forEach((box) => {
      box.checked = checked;
    });
}

function invertFilterGroupChecked(group) {
  document
    .querySelectorAll(`[data-filter-group="${group}"] input[type="checkbox"]`)
    .forEach((box) => {
      box.checked = !box.checked;
    });
}

const FOREIGN_STUDENT_JOB = "留学生";
const PINNED_SHEET_ID = "all";
const BUILTIN_SHEET_ORDER = ["all", "foreign-students"];
let sheetViewOrder = [...BUILTIN_SHEET_ORDER];
let sheetTabSuppressClick = false;
const DEFAULT_SHEET_VIEW_COLORS = {
  all: "#3B82F6",
  "foreign-students": "#217346",
};
const SHEET_VIEW_META = {
  all: { title: "全体シフト表.xlsx", foreign: false, jobs: null },
  "foreign-students": { title: "留学生用シフト表.xlsx", foreign: true, jobs: [FOREIGN_STUDENT_JOB] },
};
let customSheetViews = [];
const SHEET_FLIP_MS = 480;

let currentSheetView = "all";
let savedJobFilterBeforeSheet = null;
let sheetFlipBusy = false;
let sheetFlipTimer = null;
let sheetViewColors = { ...DEFAULT_SHEET_VIEW_COLORS };

function getCurrentSheetView() {
  return currentSheetView || "all";
}

function prefersReducedSheetMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
}

function normalizeSheetHex(value, fallback = "#3B82F6") {
  const raw = String(value ?? "").trim();
  if (!/^#?[0-9A-Fa-f]{6}$/.test(raw)) return fallback;
  return (raw.startsWith("#") ? raw : `#${raw}`).toUpperCase();
}

function hexToRgb(hex) {
  const normalized = normalizeSheetHex(hex);
  return {
    r: Number.parseInt(normalized.slice(1, 3), 16),
    g: Number.parseInt(normalized.slice(3, 5), 16),
    b: Number.parseInt(normalized.slice(5, 7), 16),
  };
}

function rgbToHex(r, g, b) {
  const to = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0");
  return `#${to(r)}${to(g)}${to(b)}`.toUpperCase();
}

function mixHex(hex, target, ratio) {
  const a = hexToRgb(hex);
  const b = hexToRgb(target);
  const t = Math.max(0, Math.min(1, ratio));
  return rgbToHex(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t);
}

function loadCustomSheetViews() {
  const raw = Array.isArray(serverDefaults.custom_sheet_views) ? serverDefaults.custom_sheet_views : [];
  customSheetViews = raw.filter(
    (item) => item && item.id && item.label && Array.isArray(item.job_types) && item.job_types.length
  );
  for (const key of Object.keys(SHEET_VIEW_META)) {
    if (!BUILTIN_SHEET_ORDER.includes(key)) delete SHEET_VIEW_META[key];
  }
  const customIds = [];
  for (const sheet of customSheetViews) {
    const jobs = sheet.job_types.map((job) => String(job));
    SHEET_VIEW_META[sheet.id] = {
      title: `${sheet.label}シフト表.xlsx`,
      foreign: false,
      jobs,
      custom: true,
      label: sheet.label,
    };
    sheetViewColors[sheet.id] = normalizeSheetHex(sheet.color, "#64748B");
    customIds.push(sheet.id);
  }
  sheetViewOrder = [PINNED_SHEET_ID, ...normalizeSheetTabOrder(serverDefaults.sheet_tab_order, customIds)];
}

function normalizeSheetTabOrder(value, customIds) {
  const allowed = ["foreign-students", ...customIds];
  const known = new Set(allowed);
  const result = [];
  for (const raw of Array.isArray(value) ? value : []) {
    const key = String(raw || "").trim();
    if (key === PINNED_SHEET_ID || !known.has(key) || result.includes(key)) continue;
    result.push(key);
  }
  for (const key of allowed) {
    if (!result.includes(key)) result.push(key);
  }
  return result;
}

function fixedJobsForSheet(view) {
  const jobs = SHEET_VIEW_META[view]?.jobs;
  return Array.isArray(jobs) && jobs.length ? jobs : null;
}

function installCustomSheetTabs() {
  const list = document.querySelector(".sheet-tabs");
  if (!list) return;
  const addButton = document.getElementById("btn-add-sheet-tab");
  list.querySelectorAll(".sheet-tab.is-custom").forEach((el) => el.remove());
  for (const sheet of customSheetViews) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sheet-tab is-custom";
    button.dataset.sheetView = sheet.id;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", "false");
    button.innerHTML = `<span class="sheet-tab-label"></span><span class="sheet-tab-count" aria-hidden="true">0</span>`;
    button.querySelector(".sheet-tab-label").textContent = sheet.label;
    if (addButton) list.insertBefore(button, addButton);
    else list.appendChild(button);
  }
  applySheetTabOrder();
  syncSheetAddButton();
}

function applySheetTabOrder() {
  const list = document.querySelector(".sheet-tabs");
  if (!list) return;
  const addButton = document.getElementById("btn-add-sheet-tab");
  const pinned = list.querySelector(`[data-sheet-view="${PINNED_SHEET_ID}"]`);
  const buttons = new Map();
  list.querySelectorAll(".sheet-tab[data-sheet-view]").forEach((el) => {
    const view = el.dataset.sheetView || "";
    if (view && view !== PINNED_SHEET_ID) buttons.set(view, el);
    const fixed = view === PINNED_SHEET_ID;
    el.classList.toggle("is-pinned", fixed);
    if (fixed) el.removeAttribute("title");
    else el.title = "ドラッグして並べ替え";
  });
  if (pinned) list.insertBefore(pinned, list.firstChild);
  const order = sheetViewOrder.filter((id) => buttons.has(id));
  for (const id of buttons.keys()) {
    if (!order.includes(id)) order.push(id);
  }
  for (const id of order) {
    if (addButton) list.insertBefore(buttons.get(id), addButton);
    else list.appendChild(buttons.get(id));
  }
  sheetViewOrder = [PINNED_SHEET_ID, ...order];
}

function readMovableSheetOrder() {
  return [...document.querySelectorAll(".sheet-tab[data-sheet-view]")]
    .map((el) => el.dataset.sheetView || "")
    .filter((id) => id && id !== PINNED_SHEET_ID);
}

function initSheetTabDrag() {
  const list = document.querySelector(".sheet-tabs");
  if (!list || list.dataset.reorderReady) return;
  list.dataset.reorderReady = "1";
  let drag = null;

  const clearDrag = () => {
    drag?.tab.classList.remove("is-dragging");
    list.classList.remove("is-reordering");
    drag = null;
  };

  list.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const tab = event.target.closest(".sheet-tab[data-sheet-view]");
    if (!tab || !list.contains(tab) || tab.dataset.sheetView === PINNED_SHEET_ID) return;
    drag = {
      tab,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      active: false,
    };
  });

  list.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (!drag.active) {
      if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < 6) return;
      drag.active = true;
      sheetTabSuppressClick = true;
      drag.tab.classList.add("is-dragging");
      list.classList.add("is-reordering");
      try {
        drag.tab.setPointerCapture?.(event.pointerId);
      } catch {
        /* ポインタが既に解放されているときは並べ替えだけ続ける */
      }
    }
    const target = sheetTabDropTarget(list, event.clientX, drag.tab);
    if (!target || target === drag.tab) return;
    if (target.id === "btn-add-sheet-tab") {
      list.insertBefore(drag.tab, target);
      return;
    }
    const rect = target.getBoundingClientRect();
    const after = event.clientX > rect.left + rect.width / 2;
    list.insertBefore(drag.tab, after ? target.nextElementSibling : target);
  });

  const finish = (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const moved = drag.active;
    clearDrag();
    if (!moved) return;
    sheetTabSuppressClick = true;
    window.setTimeout(() => {
      sheetTabSuppressClick = false;
    }, 50);
    const order = readMovableSheetOrder();
    sheetViewOrder = [PINNED_SHEET_ID, ...order];
    persistSheetTabOrder(order);
  };
  list.addEventListener("pointerup", finish);
  list.addEventListener("pointercancel", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    clearDrag();
    applySheetTabOrder();
  });
}

function sheetTabDropTarget(list, clientX, dragging) {
  const tabs = [...list.querySelectorAll(".sheet-tab[data-sheet-view]")].filter(
    (el) => el !== dragging && el.dataset.sheetView !== PINNED_SHEET_ID
  );
  for (const tab of tabs) {
    const rect = tab.getBoundingClientRect();
    if (clientX >= rect.left && clientX <= rect.right) return tab;
  }
  const addButton = document.getElementById("btn-add-sheet-tab");
  if (addButton && clientX >= addButton.getBoundingClientRect().left) return addButton;
  return null;
}

async function persistSheetTabOrder(order) {
  const previous = Array.isArray(serverDefaults.sheet_tab_order) ? serverDefaults.sheet_tab_order.slice() : [];
  try {
    const loaded = await fetch("/api/settings");
    if (!loaded.ok) throw new Error("設定を読み込めませんでした。");
    const settings = await loaded.json();
    settings.sheet_tab_order = order;
    const savedResponse = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    if (!savedResponse.ok) throw new Error("並びを保存できませんでした。");
    const saved = await savedResponse.json();
    serverDefaults.sheet_tab_order = Array.isArray(saved.sheet_tab_order) ? saved.sheet_tab_order : order;
    sheetViewOrder = [PINNED_SHEET_ID, ...serverDefaults.sheet_tab_order];
    applySheetTabOrder();
  } catch {
    serverDefaults.sheet_tab_order = previous;
    sheetViewOrder = [PINNED_SHEET_ID, ...normalizeSheetTabOrder(previous, customSheetViews.map((sheet) => sheet.id))];
    applySheetTabOrder();
  }
}

const MAX_CUSTOM_SHEETS = 8;
const CUSTOM_SHEET_COLORS = ["#64748b", "#0f766e", "#b45309", "#7c3aed", "#be123c", "#0369a1", "#4d7c0f", "#9a3412"];

function syncSheetAddButton() {
  const button = document.getElementById("btn-add-sheet-tab");
  if (!button) return;
  const full = customSheetViews.length >= MAX_CUSTOM_SHEETS;
  button.disabled = full;
  button.title = full ? "追加シートは8件までです" : "シートを追加";
}

function allocateCustomSheetId(existingIds) {
  const used = new Set(existingIds);
  for (let index = 1; index < 1000; index += 1) {
    const candidate = `custom-${index}`;
    if (!used.has(candidate)) return candidate;
  }
  return `custom-${Date.now().toString(36)}`;
}

function sheetAddError(message) {
  const error = document.getElementById("sheet-add-error");
  if (!error) return;
  error.textContent = message || "";
  error.classList.toggle("hidden", !message);
}

function renderSheetAddJobs() {
  const box = document.getElementById("sheet-add-jobs");
  if (!box || box.childElementCount) return;
  const jobs = Array.isArray(window.JOB_ORDER) ? window.JOB_ORDER : [];
  box.innerHTML = jobs
    .map(
      (label) => `<label class="check-row sheet-add-job">
        <input type="checkbox" class="sheet-add-job-input" value="${escapeHtml(label)}">
        <span>${escapeHtml(label)}</span>
      </label>`
    )
    .join("");
}

function placeSheetAddPopover() {
  const button = document.getElementById("btn-add-sheet-tab");
  const popover = document.getElementById("sheet-add-popover");
  const stage = document.querySelector(".shift-sheet-stage");
  if (!button || !popover || !stage) return;
  const stageRect = stage.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const width = popover.getBoundingClientRect().width || 440;
  let left = buttonRect.left - stageRect.left;
  const maxLeft = Math.max(8, stageRect.width - width - 8);
  if (left > maxLeft) left = maxLeft;
  popover.style.left = `${Math.max(8, left)}px`;
  popover.style.top = `${buttonRect.bottom - stageRect.top + 6}px`;
}

function openSheetAddPopover() {
  if (customSheetViews.length >= MAX_CUSTOM_SHEETS) return;
  const popover = document.getElementById("sheet-add-popover");
  const label = document.getElementById("sheet-add-label");
  const color = document.getElementById("sheet-add-color");
  if (!popover) return;
  renderSheetAddJobs();
  sheetAddError("");
  if (label) label.value = "";
  if (color) {
    color.value = CUSTOM_SHEET_COLORS[customSheetViews.length % CUSTOM_SHEET_COLORS.length];
  }
  popover.querySelectorAll(".sheet-add-job-input").forEach((input) => {
    input.checked = false;
  });
  popover.classList.remove("hidden");
  popover.setAttribute("aria-hidden", "false");
  placeSheetAddPopover();
  label?.focus();
}

function closeSheetAddPopover() {
  const popover = document.getElementById("sheet-add-popover");
  if (!popover) return;
  popover.classList.add("hidden");
  popover.setAttribute("aria-hidden", "true");
  sheetAddError("");
}

function refreshSheetCatalog() {
  loadCustomSheetViews();
  loadSheetViewColors();
  installCustomSheetTabs();
  syncSheetTabColors();
  updateSheetTabCounts();
}

async function saveSheetFromHome() {
  const labelInput = document.getElementById("sheet-add-label");
  const colorInput = document.getElementById("sheet-add-color");
  const saveButton = document.getElementById("btn-sheet-add-save");
  const label = labelInput?.value.trim() ?? "";
  const jobs = [...document.querySelectorAll(".sheet-add-job-input:checked")].map((input) => input.value);
  if (!label) {
    sheetAddError("シート名を入力してください。");
    labelInput?.focus();
    return;
  }
  if (!jobs.length) {
    sheetAddError("職種を1つ以上選んでください。");
    return;
  }
  if (saveButton) saveButton.disabled = true;
  try {
    const loaded = await fetch("/api/settings");
    if (!loaded.ok) throw new Error("設定を読み込めませんでした。");
    const settings = await loaded.json();
    const sheets = Array.isArray(settings.custom_sheet_views) ? settings.custom_sheet_views.slice() : [];
    if (sheets.length >= MAX_CUSTOM_SHEETS) {
      sheetAddError("追加シートは8件までです。");
      syncSheetAddButton();
      return;
    }
    const id = allocateCustomSheetId(sheets.map((item) => item.id));
    sheets.push({
      id,
      label,
      job_types: jobs,
      color: colorInput?.value || CUSTOM_SHEET_COLORS[0],
    });
    settings.custom_sheet_views = sheets;
    const savedResponse = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    if (!savedResponse.ok) {
      const error = await savedResponse.json().catch(() => ({}));
      throw new Error(typeof error.detail === "string" ? error.detail : "シートを追加できませんでした。");
    }
    const saved = await savedResponse.json();
    serverDefaults.custom_sheet_views = Array.isArray(saved.custom_sheet_views) ? saved.custom_sheet_views : sheets;
    const created = serverDefaults.custom_sheet_views.find((item) => item.label === label) || serverDefaults.custom_sheet_views.at(-1);
    closeSheetAddPopover();
    refreshSheetCatalog();
    if (created?.id) setSheetView(created.id);
  } catch (error) {
    sheetAddError(error.message || "シートを追加できませんでした。");
  } finally {
    if (saveButton) saveButton.disabled = false;
  }
}

function initSheetAddPopover() {
  const popover = document.getElementById("sheet-add-popover");
  document.getElementById("btn-add-sheet-tab")?.addEventListener("click", () => {
    const open = popover && !popover.classList.contains("hidden");
    if (open) closeSheetAddPopover();
    else openSheetAddPopover();
  });
  document.getElementById("btn-sheet-add-cancel")?.addEventListener("click", closeSheetAddPopover);
  document.getElementById("btn-sheet-add-save")?.addEventListener("click", saveSheetFromHome);
  document.getElementById("sheet-add-label")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveSheetFromHome();
    }
  });
  document.addEventListener("click", (event) => {
    if (!popover || popover.classList.contains("hidden")) return;
    if (event.target.closest("#sheet-add-popover, #btn-add-sheet-tab")) return;
    closeSheetAddPopover();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSheetAddPopover();
  });
}

function loadSheetViewColors() {
  const fromSettings = serverDefaults.sheet_view_colors;
  const customColors = Object.fromEntries(
    customSheetViews.map((sheet) => [sheet.id, normalizeSheetHex(sheet.color, "#64748B")])
  );
  sheetViewColors = {
    ...DEFAULT_SHEET_VIEW_COLORS,
    ...(fromSettings && typeof fromSettings === "object" ? fromSettings : {}),
    ...customColors,
  };
  for (const key of sheetViewOrder) {
    sheetViewColors[key] = normalizeSheetHex(
      sheetViewColors[key],
      DEFAULT_SHEET_VIEW_COLORS[key] || "#64748B"
    );
  }
  return sheetViewColors;
}

function getSheetColor(view = getCurrentSheetView()) {
  return normalizeSheetHex(
    sheetViewColors[view],
    DEFAULT_SHEET_VIEW_COLORS[view] || DEFAULT_SHEET_VIEW_COLORS.all
  );
}

function applySheetTheme(view = getCurrentSheetView()) {
  const workspace = document.querySelector(".shift-workspace");
  if (!workspace) return;
  const accent = getSheetColor(view);
  const soft = mixHex(accent, "#FFFFFF", 0.86);
  const softStrong = mixHex(accent, "#FFFFFF", 0.72);
  const header = mixHex(accent, "#000000", 0.08);
  const headerStrong = mixHex(accent, "#000000", 0.22);
  workspace.style.setProperty("--sheet-accent", accent);
  workspace.style.setProperty("--sheet-accent-soft", soft);
  workspace.style.setProperty("--sheet-accent-soft-strong", softStrong);
  workspace.style.setProperty("--sheet-header-bg", header);
  workspace.style.setProperty("--sheet-header-bg-strong", headerStrong);
  workspace.classList.add("is-sheet-themed");
  syncSheetTabColors();
}

function syncSheetTabColors() {
  document.querySelectorAll(".sheet-tab[data-sheet-view]").forEach((el) => {
    if (!(el instanceof HTMLElement)) return;
    const key = el.dataset.sheetView || "all";
    const accent = getSheetColor(key);
    const soft = mixHex(accent, "#FFFFFF", 0.84);
    const softMid = mixHex(accent, "#EEF2F7", 0.55);
    const softTop = mixHex(accent, "#FFFFFF", 0.76);
    const bar = mixHex(accent, "#FFFFFF", 0.28);
    const border = mixHex(accent, "#AEB8C6", 0.45);
    el.style.setProperty("--sheet-tab-color", accent);
    el.style.setProperty("--sheet-tab-soft", soft);
    el.style.setProperty("--sheet-tab-soft-mid", softMid);
    el.style.setProperty("--sheet-tab-soft-top", softTop);
    el.style.setProperty("--sheet-tab-bar", bar);
    el.style.setProperty("--sheet-tab-border", border);
    // 文字色は常に固定の濃い色（アクセントカラーに依存しない）
    el.style.setProperty("--sheet-tab-ink", "#1e293b");
  });
}

function syncJobFilterPanelForSheet(view = getCurrentSheetView()) {
  const panel = document.getElementById("home-filter-panel-job");
  const note = document.getElementById("home-filter-job-lock-note");
  const locked = Boolean(fixedJobsForSheet(view));
  panel?.classList.toggle("is-sheet-locked", locked);
  note?.classList.toggle("hidden", !locked);
  if (note && locked) {
    const jobs = fixedJobsForSheet(view) || [];
    note.textContent = view === "foreign-students"
      ? "留学生用シートでは職種「留学生」のみ表示します"
      : `このシートでは職種「${jobs.join("」「")}」のみ表示します`;
  }
  panel?.querySelectorAll(".home-filter-action").forEach((button) => {
    if (!(button instanceof HTMLButtonElement)) return;
    button.disabled = locked;
  });
  panel?.querySelectorAll('input[type="checkbox"]').forEach((box) => {
    if (!(box instanceof HTMLInputElement)) return;
    box.disabled = locked;
  });
}

function updateSheetEmptyState() {
  const empty = document.getElementById("sheet-empty-state");
  const legend = document.getElementById("sheet-legend");
  const tbody = shiftCalendar?.querySelector("tbody");
  if (!empty || !tbody) return;

  const view = getCurrentSheetView();
  const fixed = fixedJobsForSheet(view);
  const visibleCount = [...tbody.querySelectorAll("tr")].filter((row) => !row.hidden).length;
  const showEmpty = Boolean(fixed) && visibleCount === 0;
  const title = empty.querySelector(".sheet-empty-title");
  const body = empty.querySelector(".sheet-empty-body");
  if (showEmpty && title && body) {
    if (view === "foreign-students") {
      title.textContent = "表示できる留学生がいません";
      body.textContent = "職員管理で職種を「留学生」にした職員を登録すると、ここに表が表示されます。";
    } else {
      const label = SHEET_VIEW_META[view]?.label || "このシート";
      title.textContent = `${label}に表示できる職員がいません`;
      body.textContent = `職種が「${fixed.join("」「")}」の職員を登録すると、ここに表が表示されます。`;
    }
  }
  empty.classList.toggle("hidden", !showEmpty);
  shiftCalendar?.classList.toggle("hidden", showEmpty);
  legend?.classList.toggle("hidden", showEmpty);
}

function applySheetViewContent(next, prev) {
  currentSheetView = next;

  const workspace = document.querySelector(".shift-workspace");
  workspace?.setAttribute("data-sheet-view", next);
  workspace?.classList.toggle("is-sheet-foreign", Boolean(SHEET_VIEW_META[next]?.foreign));
  applySheetTheme(next);

  // 留学生シートは職種列・施設集計を隠して表を見やすくする
  if (shiftCalendar) {
    if (SHEET_VIEW_META[next]?.foreign) {
      shiftCalendar.classList.add("hide-col-job", "hide-summary");
    } else {
      const prefs = getPrefs();
      shiftCalendar.classList.toggle("hide-col-job", !prefs.showJob);
      shiftCalendar.classList.toggle("hide-summary", !prefs.showSummary);
    }
  }

  document.querySelectorAll(".sheet-tab[data-sheet-view]").forEach((el) => {
    if (!(el instanceof HTMLElement)) return;
    const active = el.dataset.sheetView === next;
    el.classList.toggle("is-active", active);
    el.setAttribute("aria-selected", active ? "true" : "false");
  });

  updateSheetTabCounts();
  syncJobFilterPanelForSheet(next);
  syncStudentLaborPanelVisibility(next);

  const nextJobs = fixedJobsForSheet(next);
  const prevJobs = fixedJobsForSheet(prev);
  if (nextJobs && !prevJobs) {
    savedJobFilterBeforeSheet = getSelectedFilterValues("job");
  }
  if (nextJobs) {
    const allowed = new Set(nextJobs);
    document.querySelectorAll('[data-filter-group="job"] input[type="checkbox"]').forEach((box) => {
      box.checked = allowed.has(box.value);
    });
  } else if (prevJobs) {
    const jobBoxes = [...document.querySelectorAll('[data-filter-group="job"] input[type="checkbox"]')];
    if (Array.isArray(savedJobFilterBeforeSheet)) {
      jobBoxes.forEach((box) => {
        box.checked = savedJobFilterBeforeSheet.includes(box.value);
      });
    } else {
      jobBoxes.forEach((box) => {
        box.checked = true;
      });
    }
    savedJobFilterBeforeSheet = null;
  }

  applyRowFilters();
  savePrefs({
    ...loadPrefs(),
    ...getPrefs(),
    tableZoom,
    sheetView: next,
  });
}

const PART_TIME_JOB = "パート";

function laborAudience(view = getCurrentSheetView()) {
  const jobs = fixedJobsForSheet(view);
  const all = view === "all" || !jobs;
  return {
    students: all || view === "foreign-students" || jobs.includes(FOREIGN_STUDENT_JOB),
    partTime: all || jobs.includes(PART_TIME_JOB),
  };
}

const laborSummaryCache = { key: "", student: null, partTime: null };

function currentLaborKey() {
  return `${getCalendarYear()}-${getCalendarMonth()}`;
}

function readLaborCache(kind) {
  if (laborSummaryCache.key !== currentLaborKey()) return null;
  return laborSummaryCache[kind];
}

function rememberLaborCache(kind, data) {
  const key = currentLaborKey();
  if (laborSummaryCache.key !== key) {
    laborSummaryCache.key = key;
    laborSummaryCache.student = null;
    laborSummaryCache.partTime = null;
  }
  laborSummaryCache[kind] = data;
}

function syncStudentLaborPanelVisibility(view = getCurrentSheetView()) {
  const panel = document.getElementById("student-labor-panel");
  if (!panel) return;
  const audience = laborAudience(view);
  const show = audience.students || audience.partTime;
  panel.classList.toggle("hidden", !show);
  panel.classList.toggle("is-split", audience.students && audience.partTime);
  panel.closest(".shift-workspace")?.classList.toggle("has-student-labor-panel", show);
  document.getElementById("student-labor-section")?.classList.toggle("hidden", !audience.students);
  document.getElementById("part-time-labor-section")?.classList.toggle("hidden", !audience.partTime);
  loadStudentLaborSummary();
  loadPartTimeHours();
}

function refreshLaborPanels() {
  laborSummaryCache.key = "";
  laborSummaryCache.student = null;
  laborSummaryCache.partTime = null;
  loadStudentLaborSummary({ refresh: true });
  loadPartTimeHours({ refresh: true });
}

let staffGaugeHoverId = null;
let staffGaugeHideTimer = null;

function hideStaffGaugePopover() {
  staffGaugeHoverId = null;
  const pop = document.getElementById("staff-gauge-popover");
  if (!pop) return;
  pop.classList.add("hidden");
  pop.setAttribute("aria-hidden", "true");
  pop.innerHTML = "";
  delete pop.dataset.staffId;
}

function placeStaffGaugePopover(anchor) {
  const pop = document.getElementById("staff-gauge-popover");
  if (!pop || !anchor) return;
  const rect = anchor.getBoundingClientRect();
  const width = pop.offsetWidth || 280;
  const height = pop.offsetHeight || 160;
  let left = rect.right + 8;
  if (left + width > window.innerWidth - 8) left = Math.max(8, rect.left - width - 8);
  let top = rect.top;
  if (top + height > window.innerHeight - 8) top = Math.max(8, window.innerHeight - height - 8);
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
}

function renderStaffGaugePopover(link, staffId) {
  const pop = document.getElementById("staff-gauge-popover");
  if (!pop || staffGaugeHoverId !== staffId) return;
  const student = (readLaborCache("student")?.rows || []).find((row) => String(row.staff_id) === staffId);
  const partData = readLaborCache("partTime");
  const part = (partData?.rows || []).find((row) => String(row.staff_id) === staffId);
  if (!student && !part) {
    pop.classList.add("hidden");
    pop.setAttribute("aria-hidden", "true");
    delete pop.dataset.staffId;
    return;
  }
  if (pop.dataset.staffId === staffId && !pop.classList.contains("hidden")) {
    placeStaffGaugePopover(link);
    return;
  }
  const statutory = Number(partData?.statutory_weekly_minutes) || 40 * 60;
  const insurance = Number(partData?.insurance_weekly_minutes) || 20 * 60;
  pop.innerHTML = [
    student ? buildStudentLaborGaugeCard(student) : "",
    part ? buildPartTimeGaugeCard(part, statutory, insurance) : "",
  ].join("");
  pop.dataset.staffId = staffId;
  pop.classList.remove("hidden");
  pop.setAttribute("aria-hidden", "false");
  placeStaffGaugePopover(link);
}

async function showStaffGaugePopover(link) {
  const staffId = String(link.closest("tr")?.dataset.staffId || "");
  if (!staffId) return;
  staffGaugeHoverId = staffId;
  if (readLaborCache("student") && readLaborCache("partTime")) {
    renderStaffGaugePopover(link, staffId);
    return;
  }
  if (!readLaborCache("student")) await loadStudentLaborSummary();
  if (staffGaugeHoverId !== staffId) return;
  if (!readLaborCache("partTime")) await loadPartTimeHours();
  if (staffGaugeHoverId !== staffId) return;
  renderStaffGaugePopover(link, staffId);
}

function initStaffGaugeHover() {
  const calendar = document.getElementById("shift-calendar");
  const pop = document.getElementById("staff-gauge-popover");
  if (!calendar || !pop || calendar.dataset.staffGaugeReady) return;
  calendar.dataset.staffGaugeReady = "1";

  const cancelHide = () => {
    if (staffGaugeHideTimer) {
      window.clearTimeout(staffGaugeHideTimer);
      staffGaugeHideTimer = null;
    }
  };
  const scheduleHide = () => {
    cancelHide();
    staffGaugeHideTimer = window.setTimeout(() => hideStaffGaugePopover(), 140);
  };

  calendar.addEventListener("pointerover", (event) => {
    const link = event.target.closest(".staff-name-link");
    if (!link || !calendar.contains(link)) return;
    cancelHide();
    showStaffGaugePopover(link);
  });
  calendar.addEventListener("pointerout", (event) => {
    const link = event.target.closest(".staff-name-link");
    if (!link || !calendar.contains(link)) return;
    const next = event.relatedTarget;
    if (next instanceof Node && (link.contains(next) || pop.contains(next))) return;
    scheduleHide();
  });
  pop.addEventListener("pointerenter", cancelHide);
  pop.addEventListener("pointerleave", scheduleHide);
  document.getElementById("sheet-main-scroll")?.addEventListener("scroll", () => hideStaffGaugePopover(), { passive: true });
}

function formatStudentLaborDateRange(startIso, endIso) {
  if (!startIso || !endIso) return "";
  const fmt = (iso) => {
    const [y, m, d] = String(iso).split("-");
    return `${Number(y)}年${Number(m)}月${Number(d)}日`;
  };
  return `${fmt(startIso)}～${fmt(endIso)}`;
}

function applyStudentLaborSummary(weekData) {
  const list = document.getElementById("student-labor-gauge-list");
  const rangeEl = document.getElementById("student-labor-week-range");
  if (!list || !weekData) return;
  if (rangeEl) {
    rangeEl.textContent = formatStudentLaborDateRange(
      weekData.period_start || weekData.week_start,
      weekData.period_end || weekData.week_end
    );
  }
  renderStudentLaborGaugeCards(list, weekData.rows || []);
}

async function loadStudentLaborSummary(options = {}) {
  const list = document.getElementById("student-labor-gauge-list");
  if (!list) return;

  const year = getCalendarYear();
  const month = getCalendarMonth();
  if (!year || !month) return;

  const cached = options.refresh ? null : readLaborCache("student");
  if (cached) {
    applyStudentLaborSummary(cached);
    return;
  }

  if (!list.querySelector(".student-labor-gauge-card")) {
    list.innerHTML = `<p class="student-labor-empty">読み込み中…</p>`;
  }

  try {
    const weekRes = await fetch(`/api/shifts/student-labor-summary?year=${year}&month=${month}`);
    if (!weekRes.ok) {
      list.innerHTML = `<p class="student-labor-empty">読み込みに失敗しました</p>`;
      return;
    }
    const weekData = await weekRes.json();
    rememberLaborCache("student", weekData);
    applyStudentLaborSummary(weekData);
  } catch {
    list.innerHTML = `<p class="student-labor-empty">通信エラー</p>`;
  }
}

function formatStudentLaborClock(minutes) {
  const value = Math.max(0, Math.round(Number(minutes) || 0));
  const hours = Math.floor(value / 60);
  const mins = String(value % 60).padStart(2, "0");
  return `${hours}:${mins}`;
}

function studentLaborUsagePercent(usedMinutes, limitMinutes) {
  const limit = Number(limitMinutes) || 0;
  const used = Number(usedMinutes) || 0;
  if (limit <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((used / limit) * 100)));
}

function studentLaborGaugeTone(usedMinutes, limitMinutes) {
  const limit = Number(limitMinutes) || 0;
  const used = Number(usedMinutes) || 0;
  if (limit <= 0) return "ok";
  if (used > limit) return "over";
  if (used >= limit) return "reached";
  if (used / limit >= 0.85) return "approach";
  return "ok";
}

function renderStudentLaborGaugeCards(list, rows) {
  if (!rows.length) {
    list.innerHTML = `<p class="student-labor-empty">対象の留学生がいません</p>`;
    return;
  }

  list.innerHTML = rows.map(buildStudentLaborGaugeCard).join("");
}

function formatStudentLaborWeekLabel(startIso, endIso, index) {
  const short = (iso) => {
    const [, month, day] = String(iso || "").split("-");
    return `${Number(month)}/${Number(day)}`;
  };
  if (!startIso || !endIso) return `第${index + 1}週`;
  return `第${index + 1}週 ${short(startIso)}〜${short(endIso)}`;
}

function buildStudentLaborGaugeCard(row) {
  const name = row.name || "—";
  const weeks = Array.isArray(row.weeks) && row.weeks.length ? row.weeks : [row];
  const statusPriority = { blocked: 6, need_confirm: 5, over: 4, reached: 3, approach: 2, ok: 1 };
  const status = weeks.reduce(
    (worst, week) =>
      (statusPriority[week.status] || 0) > (statusPriority[worst] || 0) ? week.status : worst,
    "ok"
  );
  const staffId = row.staff_id ?? "";

  return `<article class="student-labor-gauge-card status-${escapeHtml(status)}" data-staff-id="${staffId}">
    <h4 class="student-labor-gauge-name">${escapeHtml(name)}</h4>
    <div class="student-labor-gauge-metrics">
      ${weeks
        .map((week, index) => {
          const used = Number(week.total_week_minutes) || 0;
          const limit = Number(week.limit_week_minutes) || 28 * 60;
          return renderStudentLaborGaugeRow({
            label: formatStudentLaborWeekLabel(week.display_start || week.week_start, week.display_end || week.week_end, index),
            used,
            limit,
            pct: studentLaborUsagePercent(used, limit),
            tone: studentLaborGaugeTone(used, limit),
          });
        })
        .join("")}
    </div>
  </article>`;
}

function renderStudentLaborGaugeRow({ label, used, limit, pct, tone }) {
  const ratio = `${formatStudentLaborClock(used)}/${formatStudentLaborClock(limit)}`;
  return `<div class="student-labor-gauge-row tone-${escapeHtml(tone)}">
    <div class="student-labor-gauge-meta">
      <span class="student-labor-gauge-label">${escapeHtml(label)}</span>
      <span class="student-labor-gauge-ratio">${escapeHtml(ratio)}</span>
    </div>
    <div
      class="student-labor-gauge"
      role="progressbar"
      aria-label="${escapeHtml(label)}"
      aria-valuemin="0"
      aria-valuemax="100"
      aria-valuenow="${pct}"
      aria-valuetext="${escapeHtml(ratio)}"
    >
      <span class="student-labor-gauge-fill" style="width:${pct}%"></span>
    </div>
  </div>`;
}

function applyPartTimeHours(data) {
  const list = document.getElementById("part-time-gauge-list");
  const rangeEl = document.getElementById("part-time-week-range");
  if (!list || !data) return;
  if (rangeEl) {
    rangeEl.textContent = formatStudentLaborDateRange(data.period_start, data.period_end);
  }
  renderPartTimeGaugeCards(list, data.rows || [], data);
}

async function loadPartTimeHours(options = {}) {
  const list = document.getElementById("part-time-gauge-list");
  if (!list) return;

  const year = getCalendarYear();
  const month = getCalendarMonth();
  if (!year || !month) return;

  const cached = options.refresh ? null : readLaborCache("partTime");
  if (cached) {
    applyPartTimeHours(cached);
    return;
  }

  if (!list.querySelector(".student-labor-gauge-card")) {
    list.innerHTML = `<p class="student-labor-empty">読み込み中…</p>`;
  }

  try {
    const response = await fetch(`/api/shifts/part-time-hours?year=${year}&month=${month}`);
    if (!response.ok) {
      list.innerHTML = `<p class="student-labor-empty">読み込みに失敗しました</p>`;
      return;
    }
    const data = await response.json();
    rememberLaborCache("partTime", data);
    applyPartTimeHours(data);
  } catch {
    list.innerHTML = `<p class="student-labor-empty">通信エラー</p>`;
  }
}

function partTimeGaugeTone(usedMinutes, statutoryMinutes, insuranceMinutes) {
  const used = Number(usedMinutes) || 0;
  const statutory = Number(statutoryMinutes) || 40 * 60;
  const insurance = Number(insuranceMinutes) || 20 * 60;
  if (used > statutory) return "overtime";
  if (used >= insurance) return "statutory";
  return "within";
}

function renderPartTimeGaugeCards(list, rows, data) {
  if (!rows.length) {
    list.innerHTML = `<p class="student-labor-empty">対象のパート職員がいません</p>`;
    return;
  }
  const statutory = Number(data.statutory_weekly_minutes) || 40 * 60;
  const insurance = Number(data.insurance_weekly_minutes) || 20 * 60;
  list.innerHTML = rows.map((row) => buildPartTimeGaugeCard(row, statutory, insurance)).join("");
}

function buildPartTimeGaugeCard(row, statutory, insurance) {
  const name = row.name || "—";
  const weeks = Array.isArray(row.weeks) && row.weeks.length ? row.weeks : [];
  const status = row.status || "within";
  const staffId = row.staff_id ?? "";
  const markPct = statutory > 0 ? Math.round((insurance / statutory) * 100) : 50;

  return `<article class="student-labor-gauge-card status-${escapeHtml(status)}" data-staff-id="${staffId}">
    <h4 class="student-labor-gauge-name">${escapeHtml(name)}</h4>
    <div class="student-labor-gauge-metrics">
      ${weeks
        .map((week, index) => {
          const used = Number(week.week_minutes) || 0;
          const limit = Number(week.limit_week_minutes) || statutory;
          const dailyOver = Number(week.daily_over_count) || 0;
          return renderPartTimeGaugeRow({
            label: formatStudentLaborWeekLabel(week.display_start || week.week_start, week.display_end || week.week_end, index),
            used,
            limit,
            pct: studentLaborUsagePercent(used, limit),
            tone: partTimeGaugeTone(used, limit, Number(week.insurance_week_minutes) || insurance),
            dailyOver,
            markPct,
          });
        })
        .join("")}
    </div>
  </article>`;
}

function renderPartTimeGaugeRow({ label, used, limit, pct, tone, dailyOver, markPct }) {
  const ratio = `${formatStudentLaborClock(used)}/${formatStudentLaborClock(limit)}`;
  const note = dailyOver > 0 ? `8時間超 ${dailyOver}日` : "";
  const valueText = note ? `${ratio} ${note}` : ratio;
  return `<div class="student-labor-gauge-row tone-${escapeHtml(tone)} is-part-time">
    <div class="student-labor-gauge-meta">
      <span class="student-labor-gauge-label">${escapeHtml(label)}</span>
      <span class="student-labor-gauge-ratio">${escapeHtml(ratio)}</span>
    </div>
    ${note ? `<p class="part-time-daily-note">${escapeHtml(note)}</p>` : ""}
    <div
      class="part-time-gauge"
      role="progressbar"
      aria-label="${escapeHtml(label)}"
      aria-valuemin="0"
      aria-valuemax="100"
      aria-valuenow="${pct}"
      aria-valuetext="${escapeHtml(valueText)}"
    >
      <span class="part-time-gauge-track">
        <span class="student-labor-gauge-fill" style="width:${pct}%"></span>
      </span>
      <span class="part-time-gauge-mark" style="left:${markPct}%" title="週20時間"></span>
    </div>
  </div>`;
}

function clearSheetFlipClasses(viewport) {
  viewport?.classList.remove(
    "is-flipping",
    "is-flipping-forward",
    "is-flipping-back",
    "is-flip-mid"
  );
}

function setSheetView(view, opts = {}) {
  const next = SHEET_VIEW_META[view] ? view : "all";
  const prev = currentSheetView;
  const animate = opts.animate !== false;
  if (next === prev && !opts.force) {
    updateSheetTabCounts();
    return;
  }
  if (sheetFlipBusy) return;

  const viewport = document.getElementById("sheet-flip-viewport");
  const canAnimate =
    animate &&
    Boolean(viewport) &&
    prev !== next &&
    !prefersReducedSheetMotion();

  if (!canAnimate) {
    applySheetViewContent(next, prev);
    return;
  }

  const prevIndex = sheetViewOrder.indexOf(prev);
  const nextIndex = sheetViewOrder.indexOf(next);
  const forward = nextIndex >= prevIndex;
  sheetFlipBusy = true;
  clearSheetFlipClasses(viewport);
  viewport.classList.add("is-flipping", forward ? "is-flipping-forward" : "is-flipping-back");

  if (sheetFlipTimer) {
    window.clearTimeout(sheetFlipTimer);
  }
  sheetFlipTimer = window.setTimeout(() => {
    viewport.classList.add("is-flip-mid");
    applySheetViewContent(next, prev);
  }, Math.round(SHEET_FLIP_MS * 0.48));

  const finish = () => {
    viewport.removeEventListener("animationend", onEnd);
    if (sheetFlipTimer) {
      window.clearTimeout(sheetFlipTimer);
      sheetFlipTimer = null;
    }
    clearSheetFlipClasses(viewport);
    sheetFlipBusy = false;
  };
  const onEnd = (event) => {
    if (event.target !== document.getElementById("sheet-flip-page")) return;
    finish();
  };
  viewport.addEventListener("animationend", onEnd);
  window.setTimeout(finish, SHEET_FLIP_MS + 80);
}

function updateSheetTabCounts() {
  const tbody = shiftCalendar?.querySelector("tbody");
  if (!tbody) return;
  const rows = [...tbody.querySelectorAll("tr")];

  document.querySelectorAll(".sheet-tab[data-sheet-view]").forEach((el) => {
    const view = el.dataset.sheetView || "all";
    const fixed = fixedJobsForSheet(view);
    const count = fixed
      ? rows.filter((row) => fixed.includes(row.dataset.job ?? "")).length
      : rows.length;
    const badge = el.querySelector(".sheet-tab-count");
    if (badge) badge.textContent = String(count);
  });
}

function initSheetViews() {
  const saved = loadPrefs();
  const tabList = document.querySelector(".sheet-tabs");
  loadCustomSheetViews();
  loadSheetViewColors();
  installCustomSheetTabs();
  syncSheetTabColors();
  initSheetAddPopover();
  initStaffGaugeHover();

  initSheetTabDrag();

  tabList?.addEventListener("click", (event) => {
    if (sheetTabSuppressClick) {
      sheetTabSuppressClick = false;
      return;
    }
    const tab = event.target.closest(".sheet-tab[data-sheet-view]");
    if (!tab || !tabList.contains(tab)) return;
    setSheetView(tab.dataset.sheetView || "all");
  });

  const initial = SHEET_VIEW_META[saved.sheetView] ? saved.sheetView : "all";
  setSheetView(initial, { animate: false, force: true });
}

function applyRowFilters() {
  const selectedDepts = getSelectedFilterValues("dept");
  const selectedJobs = getSelectedFilterValues("job");
  const filterableJobs = Array.isArray(window.JOB_FILTER_TYPES) ? window.JOB_FILTER_TYPES : [];
  const jobFilterActive =
    filterableJobs.length > 0 &&
    selectedJobs.length > 0 &&
    selectedJobs.length < filterableJobs.length;
  const selectedPositions = getSelectedFilterValues("position");
  const sheetView = getCurrentSheetView();
  const tbody = shiftCalendar?.querySelector("tbody");
  if (!tbody) return;

  tbody.querySelectorAll("tr").forEach((row) => {
    const floors = (row.dataset.floors ?? row.dataset.dept ?? "").split(",").filter(Boolean);
    const matchDept =
      selectedDepts.length === 0 || floors.some((floor) => selectedDepts.includes(floor));
    const job = row.dataset.job ?? "";
    const fixedJobs = fixedJobsForSheet(sheetView);
    const matchJob = fixedJobs
      ? fixedJobs.includes(job)
      : !jobFilterActive || selectedJobs.includes(job);
    const rowPosition = row.dataset.position ?? "";
    const matchPosition =
      selectedPositions.length === 0 || selectedPositions.includes(rowPosition);
    row.hidden = !(matchDept && matchJob && matchPosition);
  });
  refreshSummaryCounts();
  updateFiltersSummary();
  updateSheetEmptyState();
  saveFilterPrefs();
}

function countCheckedInGroup(group) {
  const boxes = [...document.querySelectorAll(`[data-filter-group="${group}"] input[type="checkbox"]`)];
  if (!boxes.length) return { selected: 0, total: 0 };
  return {
    selected: boxes.filter((box) => box.checked).length,
    total: boxes.length,
  };
}

function updateFiltersSummary() {
  const btnText = document.getElementById("home-filters-btn-text");
  const badge = document.getElementById("home-filters-btn-badge");
  const toggle = document.getElementById("btn-toggle-filters");
  const block = document.getElementById("home-filters-collapse");
  if (!btnText || !toggle) return;

  const dept = countCheckedInGroup("dept");
  const job = countCheckedInGroup("job");
  const position = countCheckedInGroup("position");
  const hiddenCount =
    Math.max(0, dept.total - dept.selected) +
    Math.max(0, job.total - job.selected) +
    Math.max(0, position.total - position.selected);
  const isFiltered = hiddenCount > 0;
  const isOpen = !block?.classList.contains("is-collapsed");

  btnText.textContent = isOpen ? "閉じる" : "開く";
  toggle.classList.toggle("is-open", isOpen);
  toggle.classList.toggle("is-filtered", isFiltered);
  toggle.title = isOpen
    ? "絞り込みパネルを閉じます"
    : isFiltered
      ? `絞り込み中（非表示 ${hiddenCount} 項目）`
      : "並び順・表示・フロア・職種・役職を設定します";

  if (badge) {
    if (isFiltered) {
      badge.textContent = String(hiddenCount);
      badge.classList.remove("hidden");
    } else {
      badge.textContent = "";
      badge.classList.add("hidden");
    }
  }
}

function setFiltersPanelCollapsed(collapsed) {
  const block = document.getElementById("home-filters-collapse");
  const toggle = document.getElementById("btn-toggle-filters");
  const body = document.getElementById("home-filters-body");
  if (!block || !toggle) return;
  block.classList.toggle("is-collapsed", collapsed);
  toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  if (body) {
    body.hidden = collapsed;
  }
  updateFiltersSummary();
  if (!collapsed) {
    scheduleSortSegmentIndicatorUpdate();
  }
  savePrefs({
    ...loadPrefs(),
    ...getPrefs(),
    tableZoom,
    calendarSortMode: getCurrentSortMode(),
    filtersPanelCollapsed: collapsed,
  });
}

function initFiltersPanelCollapse() {
  const toggle = document.getElementById("btn-toggle-filters");
  if (!toggle) return;
  const saved = loadPrefs();
  const collapsed = saved.filtersPanelCollapsed !== false;
  setFiltersPanelCollapsed(collapsed);
  toggle.addEventListener("click", () => {
    const block = document.getElementById("home-filters-collapse");
    setFiltersPanelCollapsed(!block?.classList.contains("is-collapsed"));
  });
}

function initRowFilters() {
  const saved = loadPrefs();
  if (Array.isArray(saved.filterDepts)) {
    const deptBoxes = document.querySelectorAll('[data-filter-group="dept"] input[type="checkbox"]');
    deptBoxes.forEach((box) => {
      box.checked = saved.filterDepts.includes(box.value);
    });
  }
  if (Array.isArray(saved.filterJobs)) {
    const jobBoxes = document.querySelectorAll('[data-filter-group="job"] input[type="checkbox"]');
    jobBoxes.forEach((box) => {
      box.checked = saved.filterJobs.includes(box.value);
    });
  }
  if (Array.isArray(saved.filterPositions)) {
    const positionBoxes = document.querySelectorAll('[data-filter-group="position"] input[type="checkbox"]');
    positionBoxes.forEach((box) => {
      box.checked = saved.filterPositions.includes(box.value);
    });
  }
  applyRowFilters();
}

function onCalendarSortChange() {
  const mode = getCurrentSortMode();
  applyCalendarSort(mode);
  syncCalendarSortUrl(mode);
  syncSortSegments(mode);
  saveFilterPrefs();
}

function initCalendarControls() {
  btnPrevMonth?.addEventListener("click", () => navigateMonth(-1));
  btnNextMonth?.addEventListener("click", () => navigateMonth(1));
  btnPrevYear?.addEventListener("click", () => navigateYear(-1));
  btnNextYear?.addEventListener("click", () => navigateYear(1));

  const homeToolbarTools = document.querySelector(".home-toolbar-inline-tools");
  const filtersBody = document.getElementById("home-filters-body");
  filtersBody?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-sort-mode]");
    if (!button || !filtersBody.contains(button)) return;
    const sortSelect = getCalendarSortSelect();
    if (!sortSelect) return;
    sortSelect.value = button.dataset.sortMode ?? "dept";
    onCalendarSortChange();
  });
  getCalendarSortSelect()?.addEventListener("change", onCalendarSortChange);

  calendarZoomSelect?.addEventListener("change", () => {
    const selected = Number(calendarZoomSelect.value);
    if (!Number.isFinite(selected)) return;
    applyTableZoom(selected / 100);
    savePrefs({ ...loadPrefs(), ...getPrefs(), tableZoom });
  });
  filtersBody?.addEventListener("change", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    if (!["home-color-cells", "home-show-job", "home-show-summary"].includes(input.id)) {
      return;
    }
    onHomeDisplayChange();
  });
  document.querySelectorAll("[data-select-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      setFilterGroupChecked(button.dataset.selectFilter, true);
      applyRowFilters();
    });
  });
  document.querySelectorAll("[data-clear-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      setFilterGroupChecked(button.dataset.clearFilter, false);
      applyRowFilters();
    });
  });
  document.querySelectorAll("[data-invert-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      invertFilterGroupChecked(button.dataset.invertFilter);
      applyRowFilters();
    });
  });
  document.querySelectorAll(".filter-dept-cb, .filter-job-cb, .filter-position-cb").forEach((input) => {
    input.addEventListener("change", applyRowFilters);
  });
  initRowFilters();
  initSortState();
  initFiltersPanelCollapse();
  initSheetViews();
  initPullToReload();
  scheduleSortSegmentIndicatorUpdate();
  window.addEventListener("resize", scheduleSortSegmentIndicatorUpdate);
  const sortSegment =
    document.querySelector("#home-filters-body .home-segment") ??
    document.querySelector(".home-segment");
  if (sortSegment && typeof ResizeObserver !== "undefined") {
    const segmentObserver = new ResizeObserver(scheduleSortSegmentIndicatorUpdate);
    segmentObserver.observe(sortSegment);
  }
  document.fonts?.ready?.then(scheduleSortSegmentIndicatorUpdate);
}

function changeTableZoom(delta) {
  applyTableZoom(tableZoom + delta);
  savePrefs({ ...loadPrefs(), ...getPrefs(), tableZoom });
}

function handleZoomWheel(event) {
  event.preventDefault();
  changeTableZoom(event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP);
}

function initDisplayFromSettings() {
  const saved = loadPrefs();
  const prefs = {
    ...defaultPrefs(),
    showJob: saved.showJob ?? defaultPrefs().showJob,
    colorCells: saved.colorCells ?? defaultPrefs().colorCells,
    showSummary: saved.showSummary ?? defaultPrefs().showSummary,
  };
  syncControlsFromPrefs(prefs);
  applyDisplayPrefs(prefs);
  updatePreviewNote();
}

function initTableZoom() {
  const saved = loadPrefs();
  const compact = window.matchMedia("(max-width: 1024px)").matches;
  const phone = window.matchMedia("(max-width: 768px)").matches;
  let baseZoom = saved.tableZoom ?? defaultPrefs().tableZoom;

  // Prefer readable size on touch devices (was 80%/90% and felt too small)
  if (compact) {
    const target = phone ? 1.1 : 1.0;
    if (saved.tableZoom == null) {
      baseZoom = target;
      savePrefs({ ...saved, tableZoom: target, sheetReadableV1: true });
    } else if (!saved.sheetReadableV1 && Number(saved.tableZoom) < target) {
      // One-time bump for users stuck on the old compact default
      baseZoom = target;
      savePrefs({ ...saved, tableZoom: target, sheetReadableV1: true });
    } else if (!saved.sheetReadableV1) {
      savePrefs({ ...saved, sheetReadableV1: true });
    }
  }

  applyTableZoom(baseZoom);
  zoomControls?.addEventListener("wheel", handleZoomWheel, { passive: false });
  shiftCalendar?.addEventListener(
    "wheel",
    (event) => {
      if (!event.ctrlKey || !event.target.closest(".table-wrap")) return;
      handleZoomWheel(event);
    },
    { passive: false }
  );
  zoomInBtn?.addEventListener("click", () => stepZoom(1));
  zoomOutBtn?.addEventListener("click", () => stepZoom(-1));
}

function syncPreviewFromCalendar() {
  if (!previewBox || !shiftCalendar) return;
  const sourceTable = shiftCalendar.querySelector(".shift-table");
  if (!sourceTable) return;

  const table = sourceTable.cloneNode(true);
  table.classList.add("shift-table-compact");
  table.querySelectorAll("tbody tr").forEach((row) => {
    const sourceRow = sourceTable.querySelector(`tbody tr[data-staff-id="${row.dataset.staffId}"]`);
    if (sourceRow?.hidden) {
      row.remove();
    }
  });
  table.querySelectorAll(".shift-td-editable").forEach((cell) => {
    cell.classList.remove("shift-td-editable", "is-editing");
    cell.removeAttribute("title");
    cell.removeAttribute("data-staff-id");
    cell.removeAttribute("data-day");
  });
  table.querySelectorAll(".staff-name-link").forEach((link) => {
    link.replaceWith(link.textContent);
  });
  previewBox.replaceChildren(table);
}

function refreshDisplay() {
  const prefs = getPrefs();
  savePrefs({ ...loadPrefs(), ...prefs, tableZoom });
  syncControlsFromPrefs(prefs);
  syncPreviewFromCalendar();
  applyDisplayPrefs(prefs);
  updatePreviewNote();
  previewBox?.scrollTo(0, 0);
}

function openPrintModal() {
  if (!printModal) return;
  closeCellEditor();
  printModal.classList.remove("hidden");
  printModal.setAttribute("aria-hidden", "false");
  refreshDisplay();
}

function closePrintModal() {
  if (!printModal) return;
  printModal.classList.add("hidden");
  printModal.setAttribute("aria-hidden", "true");
}

initDisplayFromSettings();
initTableZoom();
initCalendarControls();
btnShiftUndo?.addEventListener("click", () => undoShiftEdit());
btnShiftRedo?.addEventListener("click", () => redoShiftEdit());
updateHistoryButtons();

printButton?.addEventListener("click", openPrintModal);

document.querySelectorAll("[data-close-print-modal]").forEach((element) => {
  element.addEventListener("click", closePrintModal);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (activeEditCell) {
      closeCellEditor();
      return;
    }
    if (printModal && !printModal.classList.contains("hidden")) {
      closePrintModal();
    }
    return;
  }

  if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
  const target = event.target;
  if (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  ) {
    return;
  }

  const key = event.key.toLowerCase();
  if (key === "z" && !event.shiftKey) {
    event.preventDefault();
    undoShiftEdit();
    return;
  }
  if (key === "y" || (key === "z" && event.shiftKey)) {
    event.preventDefault();
    redoShiftEdit();
  }
});

document.querySelectorAll("[data-select-group]").forEach((button) => {
  button.addEventListener("click", () => {
    const list = printModal?.querySelector(`.print-filter-list[data-group="${button.dataset.selectGroup}"]`);
    if (!list) return;
    list.querySelectorAll('input[type="checkbox"]').forEach((box) => {
      box.checked = true;
    });
  });
});

document.querySelectorAll("[data-clear-group]").forEach((button) => {
  button.addEventListener("click", () => {
    const list = printModal?.querySelector(`.print-filter-list[data-group="${button.dataset.clearGroup}"]`);
    if (!list) return;
    list.querySelectorAll('input[type="checkbox"]').forEach((box) => {
      box.checked = false;
    });
  });
});

document.querySelectorAll("[data-invert-group]").forEach((button) => {
  button.addEventListener("click", () => {
    const list = printModal?.querySelector(`.print-filter-list[data-group="${button.dataset.invertGroup}"]`);
    if (!list) return;
    list.querySelectorAll('input[type="checkbox"]').forEach((box) => {
      box.checked = !box.checked;
    });
  });
});

[printColJob, printColorMode].forEach((input) => {
  input?.addEventListener("change", refreshDisplay);
});

printModal?.querySelectorAll(".print-form-field select").forEach((select) => {
  select.addEventListener("change", updatePreviewNote);
});

previewRefresh?.addEventListener("click", refreshDisplay);

document.querySelector(".print-modal-footer-actions .btn-primary")?.addEventListener("click", () => {
  document.body.classList.add("print-preview-active");
  window.print();
  window.addEventListener(
    "afterprint",
    () => document.body.classList.remove("print-preview-active"),
    { once: true }
  );
});

const shiftOptions = window.SHIFT_OPTIONS ?? [];
const symbolClassMap = {
  ...(window.SYMBOL_CLASS_MAP ?? {}),
  ...Object.fromEntries(shiftOptions.map((item) => [item.symbol, item.class])),
};

let activeEditCell = null;
let shiftPicker = null;

function ensureShiftPicker() {
  if (shiftPicker) return shiftPicker;
  shiftPicker = document.createElement("div");
  shiftPicker.id = "shift-cell-picker";
  shiftPicker.className = "shift-cell-picker hidden";
  shiftPicker.setAttribute("role", "listbox");
  shiftPicker.setAttribute("aria-label", "シフトを選択");
  document.body.appendChild(shiftPicker);
  return shiftPicker;
}

function hideShiftPicker() {
  shiftPicker?.classList.add("hidden");
  shiftPicker?.classList.remove("is-bulk");
  shiftPicker?.replaceChildren();
}

function positionShiftPicker(picker, td) {
  const rect = td.getBoundingClientRect();
  const margin = 8;
  let left = rect.left + rect.width / 2 - picker.offsetWidth / 2;
  let top = rect.bottom + 6;

  left = Math.max(margin, Math.min(left, window.innerWidth - picker.offsetWidth - margin));
  if (top + picker.offsetHeight > window.innerHeight - margin) {
    top = rect.top - picker.offsetHeight - 6;
  }
  top = Math.max(margin, top);

  picker.style.left = `${left}px`;
  picker.style.top = `${top}px`;
}

function closeCellEditor() {
  if (activeEditCell) {
    activeEditCell.classList.remove("is-editing");
    activeEditCell = null;
  }
  hideShiftPicker();
  hideFlickPad();
  clearRangeSelection();
}

let rangeSelectedCells = [];
let rangeAnchorTd = null;

function clearRangeSelection() {
  for (const td of rangeSelectedCells) {
    td.classList.remove("is-range-selected", "is-range-anchor");
  }
  rangeSelectedCells = [];
  rangeAnchorTd = null;
}

function editableCellFromPoint(clientX, clientY) {
  const prevPad = flickPad?.style.pointerEvents;
  const prevBack = flickBackdrop?.style.pointerEvents;
  const prevPicker = shiftPicker?.style.pointerEvents;
  if (flickPad) flickPad.style.pointerEvents = "none";
  if (flickBackdrop) flickBackdrop.style.pointerEvents = "none";
  if (shiftPicker) shiftPicker.style.pointerEvents = "none";
  const el = document.elementFromPoint(clientX, clientY);
  if (flickPad) flickPad.style.pointerEvents = prevPad || "";
  if (flickBackdrop) flickBackdrop.style.pointerEvents = prevBack || "";
  if (shiftPicker) shiftPicker.style.pointerEvents = prevPicker || "";
  const td = el?.closest?.(".shift-td-editable");
  if (!td || !shiftCalendar?.contains(td)) return null;
  return td;
}

function getEditableCellsInRect(startTd, endTd) {
  if (!startTd) return [];
  if (!endTd || endTd === startTd) return [startTd];
  const table = startTd.closest("table.shift-table");
  if (!table || !table.contains(endTd)) return [startTd];

  const rows = [...table.querySelectorAll("tbody tr[data-staff-id]")];
  const startRow = startTd.closest("tr");
  const endRow = endTd.closest("tr");
  const startRowIdx = rows.indexOf(startRow);
  const endRowIdx = rows.indexOf(endRow);
  if (startRowIdx < 0 || endRowIdx < 0) return [startTd];

  const startCells = [...startRow.querySelectorAll(".shift-td-editable")];
  const endCells = [...endRow.querySelectorAll(".shift-td-editable")];
  const startDayIdx = startCells.indexOf(startTd);
  const endDayIdx = endCells.indexOf(endTd);
  if (startDayIdx < 0 || endDayIdx < 0) return [startTd];

  const minRow = Math.min(startRowIdx, endRowIdx);
  const maxRow = Math.max(startRowIdx, endRowIdx);
  const minDay = Math.min(startDayIdx, endDayIdx);
  const maxDay = Math.max(startDayIdx, endDayIdx);

  const selected = [];
  for (let r = minRow; r <= maxRow; r += 1) {
    const cells = rows[r].querySelectorAll(".shift-td-editable");
    for (let d = minDay; d <= maxDay; d += 1) {
      if (cells[d]) selected.push(cells[d]);
    }
  }
  return selected;
}

function updateRangeSelection(startTd, endTd) {
  const next = getEditableCellsInRect(startTd, endTd);
  const nextSet = new Set(next);
  for (const td of rangeSelectedCells) {
    if (!nextSet.has(td)) td.classList.remove("is-range-selected", "is-range-anchor");
  }
  for (const td of next) {
    td.classList.add("is-range-selected");
    td.classList.toggle("is-range-anchor", td === startTd);
  }
  rangeSelectedCells = next;
  rangeAnchorTd = startTd;
}

function flickInputEnabled() {
  return serverDefaults.cell_flick_input_enabled !== false;
}

function longPressMs() {
  const ms = Number(serverDefaults.cell_long_press_ms);
  if (!Number.isFinite(ms)) return 450;
  return Math.min(1500, Math.max(300, ms));
}

const FLICK_MAX_OPTIONS = 8;
const FLICK_MIN_DISTANCE = 28;
const POINTER_MOVE_CANCEL_PX = 12;
const RANGE_DRAG_START_PX = 4;

let flickPad = null;
let flickBackdrop = null;

function getFlickOptions() {
  const assigned = Array.isArray(serverDefaults.cell_flick_directions)
    ? serverDefaults.cell_flick_directions
    : [];
  const hasCustom = assigned.some((symbol) => String(symbol || "").trim());
  if (!hasCustom) {
    const defaults = shiftOptions.slice(0, FLICK_MAX_OPTIONS);
    while (defaults.length < FLICK_MAX_OPTIONS) defaults.push(null);
    return defaults;
  }

  const bySymbol = new Map(shiftOptions.map((item) => [item.symbol, item]));
  const options = [];
  for (let i = 0; i < FLICK_MAX_OPTIONS; i += 1) {
    const key = String(assigned[i] || "").trim();
    options.push(key ? bySymbol.get(key) || null : null);
  }
  return options;
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
  flickBackdrop.className = "shift-flick-backdrop hidden";
  flickBackdrop.setAttribute("aria-hidden", "true");
  flickBackdrop.addEventListener("click", () => {
    if (cellPointer?.flickActive) {
      closeFlickPad();
      resetCellPointer();
    }
  });
  document.body.appendChild(flickBackdrop);

  flickPad = document.createElement("div");
  flickPad.id = "shift-flick-pad";
  flickPad.className = "shift-flick-pad hidden";
  flickPad.setAttribute("role", "dialog");
  flickPad.setAttribute("aria-label", "フリックでシフトを選択");
  document.body.appendChild(flickPad);
  return flickPad;
}

function hideFlickPad() {
  flickPad?.classList.add("hidden");
  flickPad?.replaceChildren();
  flickBackdrop?.classList.add("hidden");
}

function positionFlickPad(pad, td) {
  const rect = td.getBoundingClientRect();
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
  flickPad.querySelectorAll(".shift-flick-dir").forEach((node) => {
    const index = Number(node.dataset.dirIndex);
    node.classList.toggle("is-active", index === directionIndex);
  });
  const center = flickPad.querySelector(".shift-flick-center-symbol");
  const options = getFlickOptions();
  if (center) {
    if (directionIndex >= 0 && directionIndex < options.length && options[directionIndex]) {
      center.classList.toggle("is-long-symbol", isLongShiftSymbol(options[directionIndex].symbol));
      center.textContent = isLongShiftSymbol(options[directionIndex].symbol)
        ? formatShiftSymbolForCell(options[directionIndex].symbol)
        : options[directionIndex].symbol;
      center.className = `shift-flick-center-symbol ${options[directionIndex].class}`;
    } else {
      const currentSymbol = activeEditCell?.dataset.symbol ?? "";
      const currentOption = shiftOptions.find((item) => item.symbol === currentSymbol);
      center.classList.toggle("is-long-symbol", isLongShiftSymbol(currentSymbol));
      center.textContent = isLongShiftSymbol(currentSymbol)
        ? formatShiftSymbolForCell(currentSymbol)
        : (currentSymbol || "·");
      center.className = `shift-flick-center-symbol ${currentOption?.class ?? "shift-off"}${isLongShiftSymbol(currentSymbol) ? " is-long-symbol" : ""}`;
    }
  }
}

function openFlickPad(td) {
  if (activeEditCell && activeEditCell !== td) {
    closeCellEditor();
  }

  activeEditCell = td;
  td.classList.add("is-editing");

  const pad = ensureFlickPad();
  const options = getFlickOptions();
  const currentSymbol = td.dataset.symbol ?? "";
  const currentOption = shiftOptions.find((item) => item.symbol === currentSymbol);
  const centerX = 110;
  const centerY = 110;
  const radius = 78;

  pad.replaceChildren();

  const center = document.createElement("div");
  center.className = "shift-flick-center";
  const centerSymbol = document.createElement("span");
  centerSymbol.className = `shift-flick-center-symbol ${currentOption?.class ?? "shift-off"}`;
  centerSymbol.textContent = currentSymbol || "·";
  const centerHint = document.createElement("span");
  centerHint.className = "shift-flick-center-hint";
  centerHint.textContent = "方向へスライド";
  center.append(centerSymbol, centerHint);
  pad.appendChild(center);

  options.forEach((option, index) => {
    if (!option) return;
    const angle = (-90 + index * 45) * (Math.PI / 180);
    const left = centerX + radius * Math.cos(angle) - 28;
    const top = centerY + radius * Math.sin(angle) - 28;

    const button = document.createElement("div");
    button.className = `shift-flick-dir ${option.class}`;
    button.dataset.dirIndex = String(index);
    button.style.left = `${left}px`;
    button.style.top = `${top}px`;

    const symbolSpan = document.createElement("span");
    symbolSpan.className = `shift-flick-dir-symbol${isLongShiftSymbol(option.symbol) ? " is-long-symbol" : ""}`;
    symbolSpan.textContent = isLongShiftSymbol(option.symbol)
      ? formatShiftSymbolForCell(option.symbol)
      : option.symbol;

    const labelSpan = document.createElement("span");
    labelSpan.className = "shift-flick-dir-label";
    labelSpan.textContent = option.label;

    button.append(symbolSpan, labelSpan);
    pad.appendChild(button);
  });

  flickBackdrop?.classList.remove("hidden");
  pad.classList.remove("hidden");
  window.requestAnimationFrame(() => positionFlickPad(pad, td));
}

function closeFlickPad() {
  hideFlickPad();
  if (activeEditCell && (!shiftPicker || shiftPicker.classList.contains("hidden"))) {
    activeEditCell.classList.remove("is-editing");
    activeEditCell = null;
  }
}


function symbolCharLength(symbol) {
  return [...String(symbol || "")].length;
}

function isLongShiftSymbol(symbol) {
  return symbolCharLength(symbol) > 2;
}

function isTimeRangeShiftSymbol(symbol) {
  return /^\d{1,2}:\d{2}\s*[-〜～~－]\s*\d{1,2}:\d{2}$/.test(String(symbol || "").trim());
}

function formatShiftSymbolForCell(symbol) {
  const raw = String(symbol || "").trim();
  if (!raw) return "";
  const match = raw.match(/^(\d{1,2}:\d{2})\s*[-〜～~－]\s*(\d{1,2}:\d{2})$/);
  if (match) return `${match[1]}\n${match[2]}`;
  if (symbolCharLength(raw) > 6) {
    const mid = Math.ceil(symbolCharLength(raw) / 2);
    const chars = [...raw];
    return `${chars.slice(0, mid).join("")}\n${chars.slice(mid).join("")}`;
  }
  return raw;
}

function paintShiftSymbolElement(element, symbol) {
  if (!element) return;
  const value = symbol || "";
  element.dataset.symbol = value;
  const long = isLongShiftSymbol(value);
  element.classList.toggle("is-long-symbol", long);
  if (long) {
    element.textContent = formatShiftSymbolForCell(value);
  } else {
    element.textContent = "";
  }
}

function syncShiftTableLongSymbolMode() {
  const table = document.querySelector(".shift-table");
  if (!table) return;
  let maxLen = 1;
  for (const item of shiftOptions) {
    maxLen = Math.max(maxLen, symbolCharLength(item?.symbol));
  }
  table.querySelectorAll(".shift-cell[data-symbol], .shift-td[data-symbol]").forEach((el) => {
    maxLen = Math.max(maxLen, symbolCharLength(el.dataset.symbol));
  });
  table.classList.toggle("has-long-symbols", maxLen > 2);
  table.classList.toggle("has-xl-symbols", maxLen > 8);
  table.dataset.symbolMaxLen = String(maxLen);
}

function refreshRenderedShiftSymbols() {
  document.querySelectorAll(".shift-table .shift-cell[data-symbol]").forEach((span) => {
    paintShiftSymbolElement(span, span.dataset.symbol || "");
  });
  document.querySelectorAll(".legend-symbol").forEach((el) => {
    const symbol = (el.textContent || el.dataset.symbol || "").trim();
    if (!symbol || symbol === "手" || symbol === "休") return;
    el.classList.toggle("is-long-symbol", isLongShiftSymbol(symbol));
  });
  syncShiftTableLongSymbolMode();
}

function shiftClassList(symbol) {
  if (!symbol) return "shift-off";
  return symbolClassMap[symbol] ?? "shift-off";
}

function applyCellSymbol(td, symbol, options = {}) {
  const shiftClass = shiftClassList(symbol);
  const source = options.source ?? (options.manual ? "manual" : td.dataset.source ?? "");
  td.dataset.symbol = symbol;
  td.title = "クリックで編集";
  delete td.dataset.placementFloor;
  delete td.dataset.placementRole;
  if (source) {
    td.dataset.source = source;
  } else {
    delete td.dataset.source;
  }

  let className = `day-col shift-td shift-td-editable ${shiftClass}`;
  if (source === "manual") className += " is-manual";
  if (source === "leave") className += " is-leave-request";
  td.className = className;

  const hit = document.createElement("span");
  hit.className = "shift-cell-hit";
  hit.setAttribute("aria-hidden", "true");

  const span = document.createElement("span");
  span.className = `shift-cell ${shiftClass}${source === "leave" ? " is-leave-request" : ""}`;
  span.setAttribute("aria-label", symbol || "未入力");
  // Short symbols stay in data-symbol (::after). Long/time-range symbols use text for wrapping.
  paintShiftSymbolElement(span, symbol || "");
  // Transparent hit layer sits above the glyph so iOS callout has no text target
  td.replaceChildren(hit, span);
  syncShiftTableLongSymbolMode();
}

function captureCellState(td) {
  if (!td) return null;
  return {
    staffId: Number(td.dataset.staffId),
    year: Number(td.dataset.year),
    month: Number(td.dataset.month),
    day: Number(td.dataset.day),
    symbol: td.dataset.symbol ?? "",
    source: td.dataset.source ?? "",
  };
}

function findCellTd(state) {
  if (!state?.staffId) return null;
  return shiftCalendar?.querySelector(
    `.shift-td-editable[data-staff-id="${state.staffId}"][data-year="${state.year}"][data-month="${state.month}"][data-day="${state.day}"]`
  );
}

function applyCellState(state) {
  const td = findCellTd(state);
  if (!td || !state) return;
  applyCellSymbol(td, state.symbol, { source: state.source || "" });
}

function statesSnapshotEqual(beforeStates, afterStates) {
  return JSON.stringify(beforeStates) === JSON.stringify(afterStates);
}

function updateHistoryButtons() {
  if (btnShiftUndo) btnShiftUndo.disabled = undoStack.length === 0;
  if (btnShiftRedo) btnShiftRedo.disabled = redoStack.length === 0;
}

function pushShiftHistory(beforeStates, afterStates) {
  if (historyApplying) return;
  const before = beforeStates.filter(Boolean);
  const after = afterStates.filter(Boolean);
  if (!before.length || statesSnapshotEqual(before, after)) return;
  undoStack.push({ before, after });
  if (undoStack.length > MAX_SHIFT_HISTORY) undoStack.shift();
  redoStack.length = 0;
  updateHistoryButtons();
}

function findRelatedTd(related) {
  if (!related?.shift_date) return null;
  const [y, m, d] = related.shift_date.split("-").map(Number);
  return shiftCalendar?.querySelector(
    `.shift-td-editable[data-staff-id="${related.staff_id}"][data-year="${y}"][data-month="${m}"][data-day="${d}"]`
  );
}

function relatedToState(related) {
  if (!related?.shift_date) return null;
  const [y, m, d] = related.shift_date.split("-").map(Number);
  return {
    staffId: Number(related.staff_id),
    year: y,
    month: m,
    day: d,
    symbol: related.symbol ?? "",
    source: related.source ?? "",
  };
}

async function persistCellState(state, options = {}) {
  const response = await fetch("/api/shifts/cell", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      staff_id: state.staffId,
      year: state.year,
      month: state.month,
      day: state.day,
      symbol: state.symbol,
    }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(formatCellErrorDetail(error.detail));
  }
  const data = await response.json().catch(() => ({}));
  if (!options.deferDomApply) {
    applyCellState(state);
    if (!options.skipRelatedFromApi) {
      for (const related of data.related ?? []) {
        const relatedState = relatedToState(related);
        if (relatedState) applyCellState(relatedState);
      }
    }
  }
  return data;
}

async function restoreHistoryStates(states) {
  historyApplying = true;
  try {
    const uniqueStates = [];
    const seen = new Set();
    for (const state of states) {
      const key = `${state.staffId}-${state.year}-${state.month}-${state.day}`;
      if (seen.has(key)) continue;
      seen.add(key);
      uniqueStates.push(state);
    }
    for (const state of uniqueStates) {
      await persistCellState(state, { deferDomApply: true, skipRelatedFromApi: true });
    }
    for (const state of uniqueStates) {
      applyCellState(state);
    }
    refreshSummaryCounts();
  } finally {
    historyApplying = false;
  }
}

async function undoShiftEdit() {
  if (!undoStack.length) return;
  const entry = undoStack.pop();
  try {
    await restoreHistoryStates(entry.before);
    redoStack.push(entry);
  } catch (error) {
    undoStack.push(entry);
    window.alert(error.message || "取り消しに失敗しました。");
  }
  updateHistoryButtons();
}

async function redoShiftEdit() {
  if (!redoStack.length) return;
  const entry = redoStack.pop();
  try {
    await restoreHistoryStates(entry.after);
    undoStack.push(entry);
  } catch (error) {
    redoStack.push(entry);
    window.alert(error.message || "やり直しに失敗しました。");
  }
  updateHistoryButtons();
}

function refreshSummaryCounts() {
  const tbody = shiftCalendar?.querySelector("tbody");
  if (!tbody) return;
  const bodyRows = [...tbody.querySelectorAll("tr")].filter((row) => !row.hidden);
  if (!bodyRows.length) return;

  shiftCalendar.querySelectorAll("tfoot [data-summary-symbol]").forEach((summaryRow) => {
    const symbol = summaryRow.dataset.summarySymbol;
    const countCells = summaryRow.querySelectorAll(".summary-count");
    countCells.forEach((countCell, columnIndex) => {
      let total = 0;
      bodyRows.forEach((row) => {
        const shiftCell = row.querySelectorAll(".shift-td")[columnIndex];
        if (shiftCell?.dataset.symbol === symbol) total += 1;
      });
      countCell.textContent = String(total);
    });
  });
}

function openCellEditor(td) {
  if (activeEditCell === td && shiftPicker && !shiftPicker.classList.contains("hidden")) {
    closeCellEditor();
    return;
  }

  if (activeEditCell && activeEditCell !== td) {
    closeCellEditor();
  }

  clearRangeSelection();
  activeEditCell = td;
  td.classList.add("is-editing");

  const picker = ensureShiftPicker();
  picker.classList.remove("is-bulk");
  const currentSymbol = td.dataset.symbol ?? "";

  picker.replaceChildren();
  shiftOptions.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `shift-picker-option ${option.class}${option.symbol === currentSymbol ? " is-current" : ""}`;
    button.dataset.symbol = option.symbol;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", option.symbol === currentSymbol ? "true" : "false");

    const symbolSpan = document.createElement("span");
    symbolSpan.className = `shift-picker-symbol${isLongShiftSymbol(option.symbol) ? " is-long-symbol" : ""}`;
    symbolSpan.textContent = isLongShiftSymbol(option.symbol)
      ? formatShiftSymbolForCell(option.symbol)
      : option.symbol;

    const labelSpan = document.createElement("span");
    labelSpan.className = "shift-picker-label";
    labelSpan.textContent = option.label;

    button.append(symbolSpan, labelSpan);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      saveCellSymbol(td, option.symbol);
    });
    picker.appendChild(button);
  });

  picker.classList.remove("hidden");
  picker.setAttribute("aria-label", "シフトを選択");
  window.requestAnimationFrame(() => positionShiftPicker(picker, td));
}

function openBulkCellEditor(cells, anchorTd) {
  const targets = [...new Set((cells || []).filter(Boolean))];
  if (!targets.length) return;

  closeFlickPad();
  if (activeEditCell) {
    activeEditCell.classList.remove("is-editing");
    activeEditCell = null;
  }
  hideShiftPicker();

  for (const td of rangeSelectedCells) {
    if (!targets.includes(td)) td.classList.remove("is-range-selected", "is-range-anchor");
  }
  rangeSelectedCells = targets;
  rangeAnchorTd = anchorTd && targets.includes(anchorTd) ? anchorTd : targets[0];
  for (const td of targets) {
    td.classList.add("is-range-selected");
    td.classList.toggle("is-range-anchor", td === rangeAnchorTd);
  }

  const pivot = rangeAnchorTd;
  activeEditCell = pivot;
  pivot.classList.add("is-editing");

  const picker = ensureShiftPicker();
  const symbols = new Set(targets.map((td) => td.dataset.symbol ?? ""));
  const currentSymbol = symbols.size === 1 ? [...symbols][0] : null;
  const hasManual = targets.some((td) => td.dataset.source === "manual");

  picker.replaceChildren();
  picker.classList.add("is-bulk");

  const heading = document.createElement("div");
  heading.className = "shift-picker-bulk-heading";
  heading.textContent = `${targets.length}件を一括入力`;
  picker.appendChild(heading);

  const body = document.createElement("div");
  body.className = "shift-picker-bulk-body";

  const optionsCol = document.createElement("div");
  optionsCol.className = "shift-picker-bulk-options";
  optionsCol.setAttribute("role", "listbox");

  shiftOptions.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `shift-picker-option ${option.class}${option.symbol === currentSymbol ? " is-current" : ""}`;
    button.dataset.symbol = option.symbol;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", option.symbol === currentSymbol ? "true" : "false");

    const symbolSpan = document.createElement("span");
    symbolSpan.className = `shift-picker-symbol${isLongShiftSymbol(option.symbol) ? " is-long-symbol" : ""}`;
    symbolSpan.textContent = isLongShiftSymbol(option.symbol)
      ? formatShiftSymbolForCell(option.symbol)
      : option.symbol;

    const labelSpan = document.createElement("span");
    labelSpan.className = "shift-picker-label";
    labelSpan.textContent = option.label;

    button.append(symbolSpan, labelSpan);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      saveBulkCellSymbols(targets, option.symbol);
    });
    optionsCol.appendChild(button);
  });

  const actionsRow = document.createElement("div");
  actionsRow.className = "shift-picker-bulk-actions";

  const unlockBtn = document.createElement("button");
  unlockBtn.type = "button";
  unlockBtn.className = "shift-picker-action shift-picker-action-unlock";
  unlockBtn.textContent = "固定解除";
  unlockBtn.title = "選択セルの手動固定を解除";
  unlockBtn.disabled = !hasManual;
  unlockBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    unlockBulkCells(targets);
  });

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "shift-picker-action shift-picker-action-delete";
  deleteBtn.textContent = "削除";
  deleteBtn.title = "選択セルのシフトを削除";
  deleteBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    saveBulkCellSymbols(targets, "");
  });

  actionsRow.append(unlockBtn, deleteBtn);
  body.append(optionsCol, actionsRow);
  picker.appendChild(body);

  picker.classList.remove("hidden");
  picker.setAttribute("aria-label", "選択セルに一括入力");
  window.requestAnimationFrame(() => positionShiftPicker(picker, pivot));
}

async function saveBulkCellSymbols(cells, symbol) {
  const targets = [...new Set((cells || []).filter(Boolean))];
  if (!targets.length) return;

  const beforeStates = [];
  const previousSnapshots = [];
  for (const td of targets) {
    const staffId = Number(td.dataset.staffId);
    const year = Number(td.dataset.year);
    const month = Number(td.dataset.month);
    const day = Number(td.dataset.day);
    if (!staffId || !year || !month || !day) continue;
    beforeStates.push(captureCellState(td));
    previousSnapshots.push({
      td,
      symbol: td.dataset.symbol ?? "",
      source: td.dataset.source ?? "",
    });
  }
  if (!previousSnapshots.length) return;

  const selectedSet = new Set(previousSnapshots.map((item) => item.td));
  hideShiftPicker();
  if (activeEditCell) {
    activeEditCell.classList.remove("is-editing");
    activeEditCell = null;
  }
  clearRangeSelection();

  for (const { td } of previousSnapshots) {
    applyCellSymbol(td, symbol, { source: symbol ? "manual" : "" });
  }

  const relatedBeforeMap = new Map();
  const relatedAfterStates = [];
  let errorMessage = null;

  for (const { td } of previousSnapshots) {
    const response = await fetch("/api/shifts/cell", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        staff_id: Number(td.dataset.staffId),
        year: Number(td.dataset.year),
        month: Number(td.dataset.month),
        day: Number(td.dataset.day),
        symbol,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      errorMessage = formatCellErrorDetail(error.detail);
      break;
    }

    const data = await response.json().catch(() => ({}));
    for (const related of data.related ?? []) {
      const relatedTd = findRelatedTd(related);
      if (!relatedTd || selectedSet.has(relatedTd)) continue;
      const key = `${related.staff_id}-${related.shift_date}`;
      if (!relatedBeforeMap.has(key)) {
        relatedBeforeMap.set(key, captureCellState(relatedTd));
      }
      if (related.symbol) {
        applyCellSymbol(relatedTd, related.symbol, { source: related.source ?? "auto" });
      } else {
        applyCellSymbol(relatedTd, "", { source: "" });
        delete relatedTd.dataset.source;
      }
      relatedAfterStates.push(captureCellState(relatedTd));
    }
  }

  if (errorMessage) {
    for (const snap of previousSnapshots) {
      applyCellSymbol(snap.td, snap.symbol, { source: snap.source });
    }
    for (const state of relatedBeforeMap.values()) {
      applyCellState(state);
    }
    window.alert(errorMessage);
    refreshSummaryCounts();
    return;
  }

  const afterStates = previousSnapshots.map(({ td }) => captureCellState(td));
  pushShiftHistory(
    [...beforeStates, ...relatedBeforeMap.values()],
    [...afterStates, ...relatedAfterStates]
  );
  refreshSummaryCounts();
  refreshLaborPanels();
}

async function saveCellSymbol(td, symbol, options = {}) {
  const staffId = Number(td.dataset.staffId);
  const year = Number(td.dataset.year);
  const month = Number(td.dataset.month);
  const day = Number(td.dataset.day);
  if (!staffId || !year || !month || !day) return;

  const previous = td.dataset.symbol;
  const previousSource = td.dataset.source;
  const primaryBefore = options.skipHistory ? null : captureCellState(td);
  closeCellEditor();
  applyCellSymbol(td, symbol, { source: "manual" });

  const response = await fetch("/api/shifts/cell", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      staff_id: staffId,
      year,
      month,
      day,
      symbol,
    }),
  });

  if (!response.ok) {
    applyCellSymbol(td, previous, { source: previousSource });
    const error = await response.json().catch(() => ({}));
    window.alert(formatCellErrorDetail(error.detail));
    return;
  }

  const data = await response.json().catch(() => ({}));
  const beforeStates = primaryBefore ? [primaryBefore] : [];
  const relatedUpdates = [];

  for (const related of data.related ?? []) {
    const relatedTd = findRelatedTd(related);
    if (!relatedTd) continue;
    if (primaryBefore) beforeStates.push(captureCellState(relatedTd));
    relatedUpdates.push({ relatedTd, related });
  }

  for (const { relatedTd, related } of relatedUpdates) {
    if (related.symbol) {
      applyCellSymbol(relatedTd, related.symbol, { source: related.source ?? "auto" });
    } else {
      applyCellSymbol(relatedTd, "", { source: "" });
      delete relatedTd.dataset.source;
    }
  }

  if (primaryBefore) {
    const afterStates = [captureCellState(td)];
    for (const { relatedTd } of relatedUpdates) {
      afterStates.push(captureCellState(relatedTd));
    }
    pushShiftHistory(beforeStates, afterStates);
  }

  refreshSummaryCounts();
  refreshLaborPanels();
}

async function unlockBulkCells(cells) {
  const targets = [...new Set((cells || []).filter((td) => td && td.dataset.source === "manual"))];
  if (!targets.length) {
    hideShiftPicker();
    if (activeEditCell) {
      activeEditCell.classList.remove("is-editing");
      activeEditCell = null;
    }
    clearRangeSelection();
    return;
  }

  const beforeStates = [];
  const previousSnapshots = [];
  for (const td of targets) {
    beforeStates.push(captureCellState(td));
    previousSnapshots.push({
      td,
      symbol: td.dataset.symbol ?? "",
      source: td.dataset.source ?? "",
    });
  }

  hideShiftPicker();
  if (activeEditCell) {
    activeEditCell.classList.remove("is-editing");
    activeEditCell = null;
  }
  clearRangeSelection();

  for (const { td, symbol } of previousSnapshots) {
    applyCellSymbol(td, symbol, { source: "auto" });
  }

  const relatedBeforeMap = new Map();
  const relatedAfterStates = [];
  let errorMessage = null;

  for (const { td, symbol, source } of previousSnapshots) {
    const response = await fetch("/api/shifts/cell/unlock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        staff_id: Number(td.dataset.staffId),
        year: Number(td.dataset.year),
        month: Number(td.dataset.month),
        day: Number(td.dataset.day),
      }),
    });

    if (!response.ok) {
      applyCellSymbol(td, symbol, { source });
      const error = await response.json().catch(() => ({}));
      errorMessage = formatCellErrorDetail(error.detail);
      break;
    }

    const data = await response.json().catch(() => ({}));
    for (const related of data.related ?? []) {
      const relatedTd = findRelatedTd(related);
      if (!relatedTd) continue;
      const key = `${related.staff_id}-${related.shift_date}`;
      if (!relatedBeforeMap.has(key)) {
        relatedBeforeMap.set(key, captureCellState(relatedTd));
      }
      const relatedState = relatedToState(related);
      if (relatedState) applyCellState(relatedState);
      relatedAfterStates.push(captureCellState(relatedTd));
    }
  }

  if (errorMessage) {
    for (const snap of previousSnapshots) {
      applyCellSymbol(snap.td, snap.symbol, { source: snap.source });
    }
    for (const state of relatedBeforeMap.values()) {
      applyCellState(state);
    }
    window.alert(errorMessage);
    refreshSummaryCounts();
    return;
  }

  const afterStates = previousSnapshots.map(({ td }) => captureCellState(td));
  pushShiftHistory(
    [...beforeStates, ...relatedBeforeMap.values()],
    [...afterStates, ...relatedAfterStates]
  );
  refreshSummaryCounts();
  refreshLaborPanels();
}

async function unlockManualCell(td) {
  const staffId = Number(td.dataset.staffId);
  const year = Number(td.dataset.year);
  const month = Number(td.dataset.month);
  const day = Number(td.dataset.day);
  if (!staffId || !year || !month || !day) return;
  if (td.dataset.source !== "manual") return;

  const symbol = td.dataset.symbol ?? "";
  const beforeState = captureCellState(td);
  const previousSource = td.dataset.source;
  applyCellSymbol(td, symbol, { source: "auto" });

  const response = await fetch("/api/shifts/cell/unlock", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      staff_id: staffId,
      year,
      month,
      day,
    }),
  });

  if (!response.ok) {
    applyCellSymbol(td, symbol, { source: previousSource });
    const error = await response.json().catch(() => ({}));
    window.alert(formatCellErrorDetail(error.detail));
    return;
  }

  const data = await response.json().catch(() => ({}));
  const beforeStates = [beforeState];
  const relatedUpdates = [];
  for (const related of data.related ?? []) {
    const relatedTd = findRelatedTd(related);
    if (!relatedTd) continue;
    beforeStates.push(captureCellState(relatedTd));
    relatedUpdates.push({ relatedTd, related });
  }
  for (const { relatedTd, related } of relatedUpdates) {
    const relatedState = relatedToState(related);
    if (relatedState) applyCellState(relatedState);
  }
  const afterStates = [captureCellState(td)];
  for (const { relatedTd } of relatedUpdates) {
    afterStates.push(captureCellState(relatedTd));
  }
  pushShiftHistory(beforeStates, afterStates);
}

let cellClickTimer = null;
let cellPointer = null;

function resetCellPointer() {
  if (cellPointer?.longPressTimer) {
    clearTimeout(cellPointer.longPressTimer);
  }
  if (cellPointer?.flickDelayTimer) {
    clearTimeout(cellPointer.flickDelayTimer);
  }
  cellPointer = null;
}

function clearDomSelection() {
  const sel = window.getSelection?.();
  if (sel && sel.rangeCount) sel.removeAllRanges();
}

function initShiftSelectionGuard() {
  if (!shiftCalendar || shiftCalendar.dataset.selectionGuardBound === "1") return;
  shiftCalendar.dataset.selectionGuardBound = "1";

  const isIos =
    /iP(hone|ad|od)/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (isIos) document.body.classList.add("is-ios");

  let fingerDown = false;
  let clearTimer = null;
  let holdTimer = null;
  let touchOrigin = null;

  function selectionInsideCalendar() {
    const sel = window.getSelection?.();
    if (!sel || !sel.rangeCount) return false;
    const node = sel.anchorNode;
    if (!node) return false;
    const el = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    return Boolean(el && shiftCalendar.contains(el));
  }

  function scrubSelection() {
    if (fingerDown || selectionInsideCalendar()) clearDomSelection();
  }

  function blockZoomWheel(event) {
    // Trackpad pinch-zoom sends wheel + ctrl/meta on iPad / Magic Keyboard
    if (event.ctrlKey || event.metaKey) event.preventDefault();
  }

  document.addEventListener("selectionchange", scrubSelection);

  // iOS gesture pinch zoom (Safari-specific events)
  ["gesturestart", "gesturechange", "gestureend"].forEach((type) => {
    document.addEventListener(
      type,
      (event) => {
        if (!shiftCalendar.contains(event.target) && event.target !== shiftCalendar) return;
        event.preventDefault();
      },
      { passive: false, capture: true }
    );
  });

  // Wheel / trackpad pinch-zoom: keep normal scroll, block zoom
  shiftCalendar.addEventListener("wheel", blockZoomWheel, { passive: false });
  document.addEventListener(
    "wheel",
    (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (!shiftCalendar.contains(event.target) && event.target !== shiftCalendar) return;
      event.preventDefault();
    },
    { passive: false, capture: true }
  );

  shiftCalendar.addEventListener(
    "touchstart",
    (event) => {
      if (event.target.closest("input, textarea, select")) return;
      if (!event.target.closest(".shift-table, .sheet-tabs, .student-labor-panel")) return;

      if (event.touches.length > 1) {
        event.preventDefault();
        clearDomSelection();
        return;
      }

      fingerDown = true;
      clearDomSelection();
      if (clearTimer) window.clearInterval(clearTimer);
      if (holdTimer) window.clearTimeout(holdTimer);
      // Keep clearing while the finger is down (iOS inserts a selection mid-hold)
      clearTimer = window.setInterval(scrubSelection, 40);

      const touch = event.touches[0];
      touchOrigin = touch ? { x: touch.clientX, y: touch.clientY } : null;
      // Mid-hold scrub: iOS often injects "Select All" just before the callout
      holdTimer = window.setTimeout(() => {
        scrubSelection();
        clearDomSelection();
      }, 280);
    },
    { passive: false }
  );

  shiftCalendar.addEventListener(
    "touchmove",
    (event) => {
      if (event.touches.length > 1) {
        event.preventDefault();
        if (holdTimer) {
          window.clearTimeout(holdTimer);
          holdTimer = null;
        }
        return;
      }
      if (!touchOrigin || !event.touches[0]) return;
      const dx = event.touches[0].clientX - touchOrigin.x;
      const dy = event.touches[0].clientY - touchOrigin.y;
      if (Math.hypot(dx, dy) > 8 && holdTimer) {
        window.clearTimeout(holdTimer);
        holdTimer = null;
      }
    },
    { passive: false }
  );

  const endTouch = () => {
    fingerDown = false;
    touchOrigin = null;
    if (clearTimer) {
      window.clearInterval(clearTimer);
      clearTimer = null;
    }
    if (holdTimer) {
      window.clearTimeout(holdTimer);
      holdTimer = null;
    }
    clearDomSelection();
    window.setTimeout(clearDomSelection, 0);
    window.setTimeout(clearDomSelection, 80);
    window.setTimeout(clearDomSelection, 200);
  };

  shiftCalendar.addEventListener("touchend", endTouch, { passive: true });
  shiftCalendar.addEventListener("touchcancel", endTouch, { passive: true });

  // Extra belt: never start a text selection from the grid
  shiftCalendar.addEventListener(
    "selectstart",
    (event) => {
      if (event.target.closest("input, textarea, select")) return;
      event.preventDefault();
    },
    { capture: true }
  );
}

function initShiftCellEditor() {
  shiftCalendar?.addEventListener("pointerdown", (event) => {
    const td = event.target.closest(".shift-td-editable");
    if (!td || !shiftCalendar.contains(td)) return;
    const isRight = event.button === 2;
    const isPrimary = event.button === 0;
    if (!isRight && !isPrimary) return;

    if (cellClickTimer) {
      clearTimeout(cellClickTimer);
      cellClickTimer = null;
    }
    resetCellPointer();
    if (shiftPicker && !shiftPicker.classList.contains("hidden")) {
      hideShiftPicker();
    }
    if (activeEditCell) {
      activeEditCell.classList.remove("is-editing");
      activeEditCell = null;
    }
    hideFlickPad();
    clearRangeSelection();

    const rect = td.getBoundingClientRect();
    cellPointer = {
      td,
      pointerId: event.pointerId,
      button: event.button,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      originX: rect.left + rect.width / 2,
      originY: rect.top + rect.height / 2,
      longPressTimer: null,
      flickDelayTimer: null,
      flickActive: false,
      holdReady: false,
      rangeActive: false,
      rangeStart: td,
      rangeEnd: td,
      directionIndex: -1,
      cancelled: false,
      capturing: false,
    };

    const sel = window.getSelection?.();
    if (sel && sel.rangeCount) sel.removeAllRanges();

    if (isRight) {
      // Right-click: flick wheel
      event.preventDefault();
      closeCellEditor();
      cellPointer.capturing = true;
      td.setPointerCapture?.(event.pointerId);
      if (flickInputEnabled()) {
        cellPointer.flickActive = true;
        cellPointer.directionIndex = -1;
        cellPointer.holdReady = true;
        openFlickPad(td);
        window.requestAnimationFrame(() => {
          if (!cellPointer?.flickActive || !flickPad) return;
          const padRect = flickPad.getBoundingClientRect();
          cellPointer.originX = padRect.left + padRect.width / 2;
          cellPointer.originY = padRect.top + padRect.height / 2;
        });
        navigator.vibrate?.(12);
      } else {
        cellPointer.rangeActive = true;
        cellPointer.holdReady = true;
        updateRangeSelection(td, td);
      }
      return;
    }

    // Primary button: range select starts immediately on drag (no long-press wait)
  });

  shiftCalendar?.addEventListener("pointermove", (event) => {
    if (!cellPointer || event.pointerId !== cellPointer.pointerId) return;

    cellPointer.lastX = event.clientX;
    cellPointer.lastY = event.clientY;
    const dx = event.clientX - cellPointer.startX;
    const dy = event.clientY - cellPointer.startY;

    if (!cellPointer.flickActive && !cellPointer.rangeActive && cellPointer.button === 0) {
      if (Math.hypot(dx, dy) > RANGE_DRAG_START_PX) {
        if (cellPointer.longPressTimer) {
          clearTimeout(cellPointer.longPressTimer);
          cellPointer.longPressTimer = null;
        }
        closeCellEditor();
        cellPointer.holdReady = true;
        cellPointer.rangeActive = true;
        cellPointer.rangeStart = cellPointer.td;
        cellPointer.capturing = true;
        cellPointer.td.setPointerCapture?.(event.pointerId);
        const over =
          editableCellFromPoint(event.clientX, event.clientY) || cellPointer.td;
        cellPointer.rangeEnd = over;
        updateRangeSelection(cellPointer.td, over);
        event.preventDefault();
        return;
      }
      return;
    }

    if (cellPointer.rangeActive) {
      event.preventDefault();
      if (!cellPointer.capturing) {
        cellPointer.capturing = true;
        cellPointer.td.setPointerCapture?.(event.pointerId);
      }
      const over =
        editableCellFromPoint(event.clientX, event.clientY) || cellPointer.rangeEnd || cellPointer.td;
      cellPointer.rangeEnd = over;
      updateRangeSelection(cellPointer.rangeStart || cellPointer.td, over);
      return;
    }

    if (!cellPointer.flickActive) return;

    event.preventDefault();
    const fdx = event.clientX - cellPointer.originX;
    const fdy = event.clientY - cellPointer.originY;
    const dirIndex = getFlickDirectionIndex(fdx, fdy);
    if (dirIndex !== cellPointer.directionIndex) {
      cellPointer.directionIndex = dirIndex;
      updateFlickHighlight(dirIndex);
    }
  });

  const finishCellPointer = (event) => {
    if (!cellPointer || event.pointerId !== cellPointer.pointerId) return;

    const {
      td,
      longPressTimer,
      flickActive,
      rangeActive,
      holdReady,
      directionIndex,
      cancelled,
      startX,
      startY,
      rangeStart,
      rangeEnd,
      button,
    } = cellPointer;

    if (longPressTimer) {
      clearTimeout(longPressTimer);
    }
    if (cellPointer.flickDelayTimer) {
      clearTimeout(cellPointer.flickDelayTimer);
      cellPointer.flickDelayTimer = null;
    }

    if (cellPointer.capturing) {
      cellPointer.td.releasePointerCapture?.(event.pointerId);
      cellPointer.capturing = false;
    }

    if (rangeActive) {
      const cells = getEditableCellsInRect(rangeStart || td, rangeEnd || td);
      resetCellPointer();
      if (cells.length) {
        openBulkCellEditor(cells, rangeEnd || rangeStart || td);
      } else {
        clearRangeSelection();
      }
      return;
    }

    if (flickActive) {
      const options = getFlickOptions();
      const selected = directionIndex >= 0 ? options[directionIndex] : null;
      if (selected?.symbol) {
        saveCellSymbol(td, selected.symbol);
      } else {
        closeFlickPad();
      }
      resetCellPointer();
      return;
    }

    if (holdReady) {
      // Edge case: armed but neither mode engaged
      resetCellPointer();
      openCellEditor(td);
      return;
    }

    if (
      button === 0 &&
      !cancelled &&
      Math.hypot(event.clientX - startX, event.clientY - startY) <= POINTER_MOVE_CANCEL_PX
    ) {
      cellClickTimer = window.setTimeout(() => {
        cellClickTimer = null;
        openCellEditor(td);
      }, 220);
    }

    resetCellPointer();
  };

  shiftCalendar?.addEventListener("pointerup", finishCellPointer);
  shiftCalendar?.addEventListener("pointercancel", (event) => {
    if (!cellPointer || event.pointerId !== cellPointer.pointerId) return;
    if (cellPointer.flickActive) {
      closeFlickPad();
    }
    if (cellPointer.rangeActive) {
      clearRangeSelection();
    }
    resetCellPointer();
  });

  shiftCalendar?.addEventListener("contextmenu", (event) => {
    if (event.target.closest("input, textarea, select")) return;
    if (!shiftCalendar.contains(event.target)) return;
    event.preventDefault();
  });

  shiftCalendar?.addEventListener("selectstart", (event) => {
    if (event.target.closest("input, textarea, select")) return;
    event.preventDefault();
  });

  initShiftSelectionGuard();

  shiftCalendar?.addEventListener("dblclick", (event) => {
    const td = event.target.closest(".shift-td-editable");
    if (!td || !shiftCalendar.contains(td)) return;
    event.preventDefault();
    event.stopPropagation();
    if (cellClickTimer) {
      clearTimeout(cellClickTimer);
      cellClickTimer = null;
    }
    resetCellPointer();
    closeCellEditor();
    if (td.dataset.source === "manual") {
      unlockManualCell(td);
    }
  });

  document.addEventListener("click", (event) => {
    if (!activeEditCell && !rangeSelectedCells.length) return;
    const pickerOpen = shiftPicker && !shiftPicker.classList.contains("hidden");
    const flickOpen = flickPad && !flickPad.classList.contains("hidden");
    if (!pickerOpen && !flickOpen && !rangeSelectedCells.length) return;
    if (
      shiftPicker?.contains(event.target) ||
      flickPad?.contains(event.target) ||
      activeEditCell?.contains(event.target) ||
      event.target.closest?.(".shift-td-editable.is-range-selected")
    ) {
      return;
    }
    closeCellEditor();
  });

  tableWrap?.addEventListener(
    "scroll",
    () => {
      if (activeEditCell || rangeSelectedCells.length) closeCellEditor();
    },
    { passive: true }
  );

  window.addEventListener("resize", () => {
    if (activeEditCell && shiftPicker && !shiftPicker.classList.contains("hidden")) {
      positionShiftPicker(shiftPicker, activeEditCell);
    }
    if (activeEditCell && flickPad && !flickPad.classList.contains("hidden")) {
      positionFlickPad(flickPad, activeEditCell);
    }
  });
}

initShiftCellEditor();
refreshRenderedShiftSymbols();

const autoGenerateButton = document.getElementById("btn-auto-generate");
const autoGenerateModal = document.getElementById("auto-generate-modal");
const autoGenerateModalTitle = document.getElementById("auto-generate-modal-title");
const autoGenerateModalSubtitle = document.getElementById("auto-generate-modal-subtitle");
const autoGenerateSummary = document.getElementById("auto-generate-summary");
const autoGenerateResultSummary = document.getElementById("auto-generate-result-summary");
const autoGenerateMessagesWrap = document.getElementById("auto-generate-messages-wrap");
const autoGenerateMessages = document.getElementById("auto-generate-messages");
const autoGenerateCloseBtn = document.getElementById("auto-generate-close-btn");
const autoGenerateConfirmModal = document.getElementById("auto-generate-confirm-modal");
const autoGenerateConfirmSubtitle = document.getElementById("auto-generate-confirm-subtitle");
const autoGenerateConfirmSummary = document.getElementById("auto-generate-confirm-summary");
const autoGenerateConfirmWarningsWrap = document.getElementById("auto-generate-confirm-warnings-wrap");
const autoGenerateConfirmWarnings = document.getElementById("auto-generate-confirm-warnings");
const autoGenerateConfirmRun = document.getElementById("auto-generate-confirm-run");
const autoGenerateYear = document.getElementById("auto-generate-year");
const autoGenerateMonth = document.getElementById("auto-generate-month");
const autoGenerateScopeStart = document.getElementById("auto-generate-scope-start");
const autoGenerateScopeEnd = document.getElementById("auto-generate-scope-end");
const autoGenerateFloors = document.getElementById("auto-generate-floors");
const autoGenerateScopeRefresh = document.getElementById("auto-generate-scope-refresh");
const autoGenerateScopeStatus = document.getElementById("auto-generate-scope-status");

let autoGenerateShouldReload = false;
let pendingPreflight = null;
let autoGenerateScopeSyncing = false;
let autoGeneratePreflightSeq = 0;

const AUTO_GENERATE_LEVEL_LABELS = {
  error: "エラー",
  warn: "警告",
  info: "情報",
};

function formatCellErrorDetail(detail) {
  if (detail == null || detail === "") return "シフトの保存に失敗しました。";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          return item.msg || item.message || JSON.stringify(item);
        }
        return String(item);
      })
      .join("\n");
  }
  if (typeof detail === "object") {
    return detail.message || JSON.stringify(detail, null, 2);
  }
  return String(detail);
}

function formatApiErrorDetail(detail) {
  if (detail == null || detail === "") return "自動生成に失敗しました。";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const location = Array.isArray(item.loc)
            ? item.loc.filter((part) => part !== "body").join(".")
            : "";
          const message = item.msg || item.message || JSON.stringify(item);
          return location ? `${location}: ${message}` : message;
        }
        return String(item);
      })
      .join("\n");
  }
  if (typeof detail === "object") {
    return detail.message || JSON.stringify(detail, null, 2);
  }
  return String(detail);
}

function sortAutoGenerateMessages(messages) {
  const order = { error: 0, warn: 1, info: 2 };
  return [...messages].sort((left, right) => {
    const levelDiff = (order[left.level] ?? 9) - (order[right.level] ?? 9);
    if (levelDiff !== 0) return levelDiff;
    return String(left.message).localeCompare(String(right.message), "ja");
  });
}

function renderAutoGenerateMessages(messages) {
  if (!autoGenerateMessages || !autoGenerateMessagesWrap) return;
  autoGenerateMessages.replaceChildren();
  if (!messages.length) {
    autoGenerateMessagesWrap.classList.add("hidden");
    return;
  }
  autoGenerateMessagesWrap.classList.remove("hidden");
  sortAutoGenerateMessages(messages).forEach((item) => {
    const level = item.level === "error" || item.level === "warn" ? item.level : "info";
    const li = document.createElement("li");
    li.className = `auto-generate-message auto-generate-message--${level}`;
    const label = document.createElement("span");
    label.className = "auto-generate-message-label";
    label.textContent = `[${AUTO_GENERATE_LEVEL_LABELS[level] ?? "情報"}]`;
    const body = document.createElement("div");
    body.className = "auto-generate-message-body";
    const text = document.createElement("span");
    text.textContent = item.message || item.code || "詳細不明";
    body.appendChild(text);
    if (item.suggestion) {
      const tip = document.createElement("p");
      tip.className = "auto-generate-suggestion";
      tip.textContent = `改善の提案: ${item.suggestion}`;
      body.appendChild(tip);
      if (item.href) {
        const link = document.createElement("a");
        link.className = "auto-generate-suggestion-link";
        link.href = item.href;
        link.textContent = item.action_label || "設定を開く";
        body.appendChild(link);
      }
    }
    li.append(label, body);
    autoGenerateMessages.appendChild(li);
  });
}

function renderSuggestionsBlock(suggestions) {
  if (!autoGenerateResultSummary) return;
  if (!Array.isArray(suggestions) || !suggestions.length) return "";
  const items = suggestions
    .map((item) => {
      const link =
        item.href
          ? `<a class="auto-generate-suggestion-link" href="${item.href}">${item.action_label || "開く"}</a>`
          : "";
      return `<li><strong>${item.suggestion || ""}</strong>${link ? ` ${link}` : ""}${
        item.message ? `<span class="auto-generate-suggestion-context">${item.message}</span>` : ""
      }</li>`;
    })
    .join("");
  return `<section class="auto-generate-result-section auto-generate-suggestions-section"><h4>改善の提案</h4><ul>${items}</ul></section>`;
}

function renderResultSummaryBlock(summary) {
  if (!autoGenerateResultSummary) return;
  if (!summary) {
    autoGenerateResultSummary.classList.add("hidden");
    autoGenerateResultSummary.replaceChildren();
    return;
  }
  const sections = [
    ["正常に配置できた勤務", [`生成セル ${summary.placed_cells ?? 0} 件`, `希望休の維持 ${summary.leave_kept ?? 0} 件`, `手動入力の維持 ${summary.manual_kept ?? 0} 件`]],
    ["人数不足の日", summary.understaffed],
    ["配置できなかった箇所", summary.unfilled_days],
    ["夜勤リーダーの不足", summary.leader_issues],
    ["希望条件を満たせなかった箇所", summary.unmet_preferences],
    ["夜勤回数の偏り", summary.night_imbalance],
    ["公休数の偏り", summary.off_imbalance],
    ["修正が必要な箇所", summary.fix_needed],
  ];
  const html = sections
    .filter(([, items]) => Array.isArray(items) && items.length)
    .map(([title, items]) => {
      const list = items
        .map((text) => `<li>${String(text)}</li>`)
        .join("");
      return `<section class="auto-generate-result-section"><h4>${title}</h4><ul>${list}</ul></section>`;
    })
    .join("");
  const suggestionsHtml = renderSuggestionsBlock(summary.suggestions);
  if (!html && !suggestionsHtml) {
    autoGenerateResultSummary.innerHTML = '<p class="field-hint">特記事項はありません。</p>';
    autoGenerateResultSummary.classList.remove("hidden");
    return;
  }
  autoGenerateResultSummary.innerHTML = `${suggestionsHtml}${html}`;
  autoGenerateResultSummary.classList.remove("hidden");
}

function showAutoGenerateResult({ success, title, subtitle, summary, messages = [], resultSummary = null, reload = false }) {
  autoGenerateShouldReload = reload;
  if (!autoGenerateModal) {
    window.alert([summary, ...messages.map((item) => item.message)].filter(Boolean).join("\n"));
    if (reload) window.location.reload();
    return;
  }
  if (autoGenerateModalTitle) autoGenerateModalTitle.textContent = title;
  if (autoGenerateModalSubtitle) autoGenerateModalSubtitle.textContent = subtitle || "";
  if (autoGenerateSummary) autoGenerateSummary.textContent = summary || "";
  renderResultSummaryBlock(resultSummary);
  renderAutoGenerateMessages(messages);
  autoGenerateModal.classList.remove("hidden");
  autoGenerateModal.setAttribute("aria-hidden", "false");
}

function closeAutoGenerateModal() {
  if (!autoGenerateModal) return;
  autoGenerateModal.classList.add("hidden");
  autoGenerateModal.setAttribute("aria-hidden", "true");
  if (autoGenerateShouldReload) window.location.reload();
  autoGenerateShouldReload = false;
}

function closeAutoGenerateConfirmModal() {
  if (!autoGenerateConfirmModal) return;
  autoGenerateConfirmModal.classList.add("hidden");
  autoGenerateConfirmModal.setAttribute("aria-hidden", "true");
  pendingPreflight = null;
  setAutoGenerateScopeStatus("");
  if (autoGenerateConfirmRun) autoGenerateConfirmRun.disabled = false;
}


function ensureAutoGenerateYearOptions(selectedYear) {
  if (!autoGenerateYear) return;
  const current = Number(selectedYear) || Number(window.CALENDAR_YEAR) || new Date().getFullYear();
  const existing = new Set([...autoGenerateYear.options].map((opt) => Number(opt.value)));
  for (let year = current - 2; year <= current + 2; year += 1) {
    if (existing.has(year)) continue;
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = `${year}年`;
    autoGenerateYear.appendChild(option);
    existing.add(year);
  }
  [...autoGenerateYear.options]
    .sort((a, b) => Number(a.value) - Number(b.value))
    .forEach((option) => autoGenerateYear.appendChild(option));
  autoGenerateYear.value = String(current);
}

function renderAutoGenerateFloorChecks(available, selected) {
  if (!autoGenerateFloors) return;
  const availableList = Array.isArray(available) && available.length
    ? available
    : Array.isArray(window.DEPT_ORDER) ? window.DEPT_ORDER : [];
  const selectedSet = new Set(
    Array.isArray(selected) && selected.length ? selected : availableList
  );
  autoGenerateFloors.replaceChildren();
  availableList.forEach((floor) => {
    const label = document.createElement("label");
    label.className = "check-row";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = floor;
    input.checked = selectedSet.has(floor);
    input.dataset.autoGenerateFloor = "1";
    const span = document.createElement("span");
    span.textContent = floor;
    label.append(input, span);
    autoGenerateFloors.appendChild(label);
  });
}

function getAutoGenerateScopeParams() {
  const year = Number(autoGenerateYear?.value || window.CALENDAR_YEAR || 0);
  const month = Number(autoGenerateMonth?.value || window.CALENDAR_MONTH || 0);
  const scopeStart = autoGenerateScopeStart?.value || "";
  const scopeEnd = autoGenerateScopeEnd?.value || "";
  const floors = [...(autoGenerateFloors?.querySelectorAll('input[type="checkbox"]') || [])]
    .filter((input) => input.checked)
    .map((input) => input.value);
  return { year, month, scopeStart, scopeEnd, floors };
}

function buildAutoGeneratePreflightQuery(params) {
  const query = new URLSearchParams();
  query.set("year", String(params.year));
  query.set("month", String(params.month));
  if (params.scopeStart) query.set("scope_start", params.scopeStart);
  if (params.scopeEnd) query.set("scope_end", params.scopeEnd);
  if (params.floors && params.floors.length) query.set("floors", params.floors.join(","));
  return query.toString();
}

function syncAutoGenerateScopeControls(preflight, { preserveDates = false } = {}) {
  if (!preflight) return;
  autoGenerateScopeSyncing = true;
  try {
    ensureAutoGenerateYearOptions(preflight.year);
    if (autoGenerateYear) autoGenerateYear.value = String(preflight.year);
    if (autoGenerateMonth) autoGenerateMonth.value = String(preflight.month);
    const periodStart = preflight.period_start || preflight.scope_start || "";
    const periodEnd = preflight.period_end || preflight.scope_end || "";
    if (autoGenerateScopeStart) {
      autoGenerateScopeStart.min = periodStart || "";
      autoGenerateScopeStart.max = periodEnd || "";
      if (!preserveDates || !autoGenerateScopeStart.value) {
        autoGenerateScopeStart.value = preflight.scope_start || periodStart || "";
      }
    }
    if (autoGenerateScopeEnd) {
      autoGenerateScopeEnd.min = periodStart || "";
      autoGenerateScopeEnd.max = periodEnd || "";
      if (!preserveDates || !autoGenerateScopeEnd.value) {
        autoGenerateScopeEnd.value = preflight.scope_end || periodEnd || "";
      }
    }
    renderAutoGenerateFloorChecks(
      preflight.available_floors || preflight.departments || window.DEPT_ORDER || [],
      preflight.selected_floors || preflight.departments || []
    );
  } finally {
    autoGenerateScopeSyncing = false;
  }
}

function setAutoGenerateScopeStatus(message) {
  if (autoGenerateScopeStatus) autoGenerateScopeStatus.textContent = message || "";
}

function showAutoGenerateConfirm(preflight, { syncControls = true } = {}) {
  pendingPreflight = preflight;
  if (!autoGenerateConfirmModal) {
    const ok = window.confirm(
      `${preflight.scope_label}\n職員 ${preflight.staff_count} 人 / 夜勤可能 ${preflight.night_capable_count} 人\n生成を実行しますか？`
    );
    if (ok) executeAutoGenerate();
    return;
  }
  if (syncControls) {
    syncAutoGenerateScopeControls(preflight);
  } else {
    // サーバー側で丸められた日付だけ反映（フロア選択は維持）
    autoGenerateScopeSyncing = true;
    try {
      if (autoGenerateScopeStart && preflight.scope_start) {
        autoGenerateScopeStart.value = preflight.scope_start;
      }
      if (autoGenerateScopeEnd && preflight.scope_end) {
        autoGenerateScopeEnd.value = preflight.scope_end;
      }
      if (autoGenerateScopeStart && preflight.period_start) {
        autoGenerateScopeStart.min = preflight.period_start;
        autoGenerateScopeStart.max = preflight.period_end || "";
      }
      if (autoGenerateScopeEnd && preflight.period_end) {
        autoGenerateScopeEnd.min = preflight.period_start || "";
        autoGenerateScopeEnd.max = preflight.period_end;
      }
    } finally {
      autoGenerateScopeSyncing = false;
    }
  }
  if (autoGenerateConfirmSubtitle) {
    autoGenerateConfirmSubtitle.textContent = preflight.scope_label || "";
  }
  const hint = document.getElementById("auto-generate-confirm-hint");
  if (hint) {
    const floors = (preflight.selected_floors || preflight.departments || []).join("、") || "全フロア";
    hint.textContent = `手動入力済みセル（赤枠）と希望休は上書きしません。続行すると ${preflight.scope_label || "選択範囲"}（${floors}）の自動生成セルを置き換えます。`;
  }
  if (autoGenerateConfirmSummary) {
    const floors = preflight.night_mins_by_floor || {};
    const floorCounts = preflight.night_floor_counts || {};
    const needLines = Object.entries(floors)
      .filter(([, n]) => Number(n) > 0)
      .map(([floor, n]) => `${floor}夜勤 ${n}人/日`)
      .join("、");
    const advanced = (preflight.advanced_settings_used || []).join("、") || "標準のみ";
    autoGenerateConfirmSummary.innerHTML = `
      <ul class="auto-generate-confirm-list">
        <li><span>対象年月</span><strong>${preflight.year}年${preflight.month}月</strong></li>
        <li><span>対象フロア</span><strong>${(preflight.departments || []).join("、") || "—"}</strong></li>
        <li><span>職員数</span><strong>${preflight.staff_count} 人</strong></li>
        <li><span>希望休</span><strong>${preflight.leave_count} 件</strong></li>
        <li><span>夜勤可能者</span><strong>${preflight.night_capable_count} 人${
          preflight.night_guidance?.recommended_capable_total != null
            ? `（目安 ${preflight.night_guidance.recommended_capable_total} 人以上）`
            : ""
        }</strong></li>
        <li><span>夜勤リーダー可能者</span><strong>${preflight.night_leader_count} 人${
          preflight.night_guidance?.recommended_leaders != null
            ? `（目安 ${preflight.night_guidance.recommended_leaders} 人以上）`
            : ""
        }</strong></li>
        <li><span>1F夜勤対応</span><strong>${floorCounts["1F"] ?? 0} 人${
          preflight.night_guidance?.recommended_by_floor?.["1F"] != null
            ? `（目安 ${preflight.night_guidance.recommended_by_floor["1F"]} 人以上）`
            : ""
        }</strong></li>
        <li><span>2F夜勤対応</span><strong>${floorCounts["2F"] ?? 0} 人${
          preflight.night_guidance?.recommended_by_floor?.["2F"] != null
            ? `（目安 ${preflight.night_guidance.recommended_by_floor["2F"]} 人以上）`
            : ""
        }</strong></li>
        <li><span>休みの数</span><strong>${preflight.off_days_per_period ?? "土日相当"} 日</strong></li>
        <li><span>必要人数（夜勤）</span><strong>${needLines || "—"}</strong></li>
        <li><span>使用する詳細設定</span><strong>${advanced}</strong></li>
      </ul>
      ${
        preflight.night_guidance?.night_summary
          ? `<p class="auto-gen-guidance-body" style="margin-top:0.75rem">${escapeHtml(preflight.night_guidance.night_summary)}</p>`
          : ""
      }
      ${
        preflight.night_guidance?.leader_summary
          ? `<p class="auto-gen-guidance-body">${escapeHtml(preflight.night_guidance.leader_summary)}</p>`
          : ""
      }`;
  }
  if (autoGenerateConfirmWarnings && autoGenerateConfirmWarningsWrap) {
    const warnings = Array.isArray(preflight.warnings) ? preflight.warnings : [];
    autoGenerateConfirmWarnings.replaceChildren();
    if (!warnings.length) {
      autoGenerateConfirmWarningsWrap.classList.add("hidden");
    } else {
      autoGenerateConfirmWarningsWrap.classList.remove("hidden");
      warnings.forEach((item) => {
        const level = item.level === "error" || item.level === "warn" ? item.level : "info";
        const li = document.createElement("li");
        li.className = `auto-generate-message auto-generate-message--${level}`;
        const label = document.createElement("span");
        label.className = "auto-generate-message-label";
        label.textContent = item.blocking ? "[要対応]" : `[${AUTO_GENERATE_LEVEL_LABELS[level] ?? "情報"}]`;
        const body = document.createElement("div");
        body.className = "auto-generate-message-body";
        const text = document.createElement("span");
        text.textContent = item.message || "";
        body.appendChild(text);
        if (item.suggestion) {
          const tip = document.createElement("p");
          tip.className = "auto-generate-suggestion";
          tip.textContent = `改善の提案: ${item.suggestion}`;
          body.appendChild(tip);
          if (item.href) {
            const link = document.createElement("a");
            link.className = "auto-generate-suggestion-link";
            link.href = item.href;
            link.textContent = item.action_label || "設定を開く";
            body.appendChild(link);
          }
        }
        li.append(label, body);
        autoGenerateConfirmWarnings.appendChild(li);
      });
    }
  }
  if (autoGenerateConfirmRun) {
    autoGenerateConfirmRun.disabled = preflight.can_generate === false;
    autoGenerateConfirmRun.textContent =
      preflight.can_generate === false ? "問題を解消してから生成できます" : "この内容で生成する";
  }
  autoGenerateConfirmModal.classList.remove("hidden");
  autoGenerateConfirmModal.setAttribute("aria-hidden", "false");
}

async function fetchAutoGeneratePreflight(params) {
  const query = buildAutoGeneratePreflightQuery(params);
  const response = await fetch(`/api/shifts/generate/preflight?${query}`);
  const rawText = await response.text();
  let data = {};
  try {
    data = rawText ? JSON.parse(rawText) : {};
  } catch {
    data = { detail: rawText || "確認情報の取得に失敗しました。" };
  }
  if (!response.ok) {
    const error = new Error(formatApiErrorDetail(data.detail));
    error.status = response.status;
    error.payload = data;
    throw error;
  }
  return data;
}

async function refreshAutoGeneratePreflight({ syncControls = false } = {}) {
  const params = getAutoGenerateScopeParams();
  if (!params.year || !params.month) return null;
  const seq = ++autoGeneratePreflightSeq;
  setAutoGenerateScopeStatus("確認中…");
  if (autoGenerateConfirmRun) autoGenerateConfirmRun.disabled = true;
  try {
    const data = await fetchAutoGeneratePreflight(params);
    if (seq !== autoGeneratePreflightSeq) return null;
    showAutoGenerateConfirm(data, { syncControls });
    setAutoGenerateScopeStatus("範囲を反映しました");
    return data;
  } catch (error) {
    if (seq !== autoGeneratePreflightSeq) return null;
    setAutoGenerateScopeStatus(error instanceof Error ? error.message : "確認に失敗しました");
    if (autoGenerateConfirmRun) {
      autoGenerateConfirmRun.disabled = true;
      autoGenerateConfirmRun.textContent = "問題を解消してから生成できます";
    }
    return null;
  }
}

async function openAutoGenerateConfirm() {
  const year = window.CALENDAR_YEAR;
  const month = window.CALENDAR_MONTH;
  if (!year || !month) return;

  ensureAutoGenerateYearOptions(year);
  if (autoGenerateYear) autoGenerateYear.value = String(year);
  if (autoGenerateMonth) autoGenerateMonth.value = String(month);
  if (autoGenerateScopeStart) autoGenerateScopeStart.value = "";
  if (autoGenerateScopeEnd) autoGenerateScopeEnd.value = "";
  renderAutoGenerateFloorChecks(window.DEPT_ORDER || [], window.DEPT_ORDER || []);

  autoGenerateButton.disabled = true;
  autoGenerateButton.textContent = "確認中…";
  setAutoGenerateScopeStatus("確認中…");
  try {
    const data = await fetchAutoGeneratePreflight({
      year,
      month,
      scopeStart: "",
      scopeEnd: "",
      floors: window.DEPT_ORDER || [],
    });
    showAutoGenerateConfirm(data, { syncControls: true });
  } catch (error) {
    showAutoGenerateResult({
      success: false,
      title: "確認に失敗しました",
      subtitle: error?.status ? `HTTP ${error.status}` : "通信エラー",
      summary: error instanceof Error ? error.message : "確認情報の取得中にエラーが発生しました。",
    });
  } finally {
    autoGenerateButton.disabled = false;
    autoGenerateButton.textContent = "シフト自動生成";
  }
}

async function executeAutoGenerate() {
  const params = getAutoGenerateScopeParams();
  const year = params.year || window.CALENDAR_YEAR;
  const month = params.month || window.CALENDAR_MONTH;
  if (!year || !month) return;

  closeAutoGenerateConfirmModal();
  autoGenerateButton.disabled = true;
  autoGenerateButton.textContent = "生成中…";
  try {
    const response = await fetch("/api/shifts/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        year,
        month,
        preview: false,
        scope_start: params.scopeStart || null,
        scope_end: params.scopeEnd || null,
        floors: params.floors && params.floors.length ? params.floors : null,
      }),
    });
    const rawText = await response.text();
    let data = {};
    try {
      data = rawText ? JSON.parse(rawText) : {};
    } catch {
      data = { detail: rawText || "サーバーから不正な応答が返されました。" };
    }

    if (!response.ok) {
      showAutoGenerateResult({
        success: false,
        title: "自動生成に失敗しました",
        subtitle: `HTTP ${response.status}`,
        summary: formatApiErrorDetail(data.detail),
        messages: Array.isArray(data.warnings) ? data.warnings : [],
        resultSummary: data.result_summary || null,
      });
      return;
    }

    const messages = Array.isArray(data.warnings) ? data.warnings : [];
    const errorCount = messages.filter((item) => item.level === "error").length;
    const warnCount = messages.filter((item) => item.level === "warn").length;
    const applied = data.applied === true;
    const success = applied && errorCount === 0;

    const scopeLabel = data.stats?.scope_label || `${year}年${month}月`;
    const scopeRange =
      data.stats?.scope_start && data.stats?.scope_end
        ? `${data.stats.scope_start} 〜 ${data.stats.scope_end}`
        : "";

    if (!applied) {
      showAutoGenerateResult({
        success: false,
        title: "自動生成に失敗しました",
        subtitle: scopeRange ? `${scopeLabel}（${scopeRange}）` : scopeLabel,
        summary: [
          data.save_error ? `保存エラー: ${data.save_error}` : "シフトを保存できませんでした。",
          errorCount ? `エラー: ${errorCount} 件` : "",
          warnCount ? `警告: ${warnCount} 件` : "",
        ]
          .filter(Boolean)
          .join("\n"),
        messages,
        resultSummary: data.result_summary || null,
      });
      return;
    }

    showAutoGenerateResult({
      success,
      title: success
        ? warnCount > 0
          ? "自動生成が完了しました（要確認あり）"
          : "自動生成が完了しました"
        : "自動生成は保存しました（要修正あり）",
      subtitle: scopeRange ? `${scopeLabel}（${scopeRange}）` : scopeLabel,
      summary: [
        data.message ? String(data.message) : "",
        `対象: ${scopeLabel}（${data.stats?.period_days ?? 0} 日）`,
        `生成セル: ${data.stats?.generated_cells ?? 0}`,
        `手動保持: ${data.stats?.manual_locked ?? 0}`,
        `希望休: ${data.stats?.leave_locked ?? 0}`,
        errorCount ? `エラー: ${errorCount} 件` : "",
        warnCount ? `警告: ${warnCount} 件` : "",
      ]
        .filter(Boolean)
        .join("\n"),
      messages,
      resultSummary: data.result_summary || null,
      reload: true,
    });
  } catch (error) {
    showAutoGenerateResult({
      success: false,
      title: "自動生成に失敗しました",
      subtitle: "通信エラー",
      summary: error instanceof Error ? error.message : "自動生成中に通信エラーが発生しました。",
    });
  } finally {
    autoGenerateButton.disabled = false;
    autoGenerateButton.textContent = "シフト自動生成";
  }
}

// generation.js owns the auto-generation button and transactional preview flow.

const clearShiftsButton = document.getElementById("btn-clear-shifts");

async function runClearShifts() {
  const year = window.CALENDAR_YEAR;
  const month = window.CALENDAR_MONTH;
  if (!year || !month) return;

  const confirmed = window.confirm(
    `${year}年${month}月の表示期間のシフトをすべて削除します。\n` +
      "手動入力・希望休・自動生成の区別なく、すべてのセルが空白になります。\n\n実行しますか？"
  );
  if (!confirmed) return;

  clearShiftsButton.disabled = true;
  const originalLabel = clearShiftsButton.textContent;
  clearShiftsButton.textContent = "クリア中…";
  try {
    const response = await fetch("/api/shifts/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year, month }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      window.alert(data.detail || "シフトのクリアに失敗しました。");
      return;
    }
    const range =
      data.period_start && data.period_end
        ? `\n対象: ${data.period_start} 〜 ${data.period_end}`
        : "";
    window.alert(`${year}年${month}月のシフトをクリアしました。${range}\n削除: ${data.deleted_count ?? 0} 件`);
    window.location.reload();
  } catch (error) {
    window.alert(error instanceof Error ? error.message : "シフトのクリア中に通信エラーが発生しました。");
  } finally {
    clearShiftsButton.disabled = false;
    clearShiftsButton.textContent = originalLabel;
  }
}

clearShiftsButton?.addEventListener("click", runClearShifts);

function initPullToReload() {
  const THRESHOLD = 72;
  const MAX_PULL = 120;
  // Page-level host (not the sheet). Pull from topbar/toolbar chrome.
  const host = document.querySelector(".main") || document.body;
  if (!host || host.dataset.pullReloadBound === "1") return;
  host.dataset.pullReloadBound = "1";

  function pageScrollTop() {
    const content = document.querySelector(".content");
    return Math.max(
      window.scrollY || 0,
      document.documentElement.scrollTop || 0,
      document.body.scrollTop || 0,
      content?.scrollTop || 0
    );
  }

  function isSheetSurface(target) {
    if (!(target instanceof Element)) return false;
    // Sheet / table gestures must keep native scrolling — never hijack those
    return Boolean(
      target.closest(
        ".table-wrap, .calendar-scroll, .sheet-main-scroll, .student-labor-panel, .sheet-flip-viewport, .sheet-empty-state"
      )
    );
  }

  let indicator = document.getElementById("pull-reload-indicator");
  if (!indicator) {
    indicator = document.createElement("div");
    indicator.id = "pull-reload-indicator";
    indicator.className = "pull-reload-indicator";
    indicator.setAttribute("aria-live", "polite");
    indicator.innerHTML = `<span class="pull-reload-spinner" aria-hidden="true"></span><span class="pull-reload-text">引き下げて再読み込み</span>`;
    host.prepend(indicator);
  }

  let startY = 0;
  let pulling = false;
  let armed = false;
  let reloading = false;
  let tracking = false;

  function setIndicator(distance) {
    const progress = Math.min(1, distance / THRESHOLD);
    indicator.style.setProperty("--pull", String(progress));
    indicator.classList.toggle("is-visible", distance > 8);
    indicator.classList.toggle("is-ready", distance >= THRESHOLD);
    const text = indicator.querySelector(".pull-reload-text");
    if (text) {
      text.textContent = distance >= THRESHOLD ? "離すと再読み込み" : "引き下げて再読み込み";
    }
  }

  function resetIndicator() {
    indicator.classList.remove("is-visible", "is-ready", "is-reloading");
    indicator.style.setProperty("--pull", "0");
    const text = indicator.querySelector(".pull-reload-text");
    if (text) text.textContent = "引き下げて再読み込み";
  }

  function canPull() {
    if (reloading) return false;
    if (document.body.classList.contains("sidebar-open")) return false;
    if (document.querySelector(".shift-picker:not(.hidden), .cell-editor:not(.hidden), .modal:not(.hidden)")) {
      return false;
    }
    return pageScrollTop() <= 1;
  }

  host.classList.add("pull-reload-host");

  host.addEventListener(
    "touchstart",
    (event) => {
      if (reloading || event.touches.length !== 1) return;
      if (event.target.closest("input, textarea, select, button, a, label")) return;
      if (isSheetSurface(event.target)) {
        tracking = false;
        pulling = false;
        return;
      }
      if (!canPull()) {
        tracking = false;
        pulling = false;
        return;
      }
      startY = event.touches[0].clientY;
      tracking = true;
      pulling = false;
      armed = false;
    },
    { passive: true }
  );

  host.addEventListener(
    "touchmove",
    (event) => {
      if (!tracking || reloading) return;
      if (!canPull()) {
        tracking = false;
        pulling = false;
        resetIndicator();
        return;
      }
      const dy = event.touches[0].clientY - startY;
      if (dy <= 0) {
        pulling = false;
        armed = false;
        resetIndicator();
        return;
      }
      pulling = true;
      const distance = Math.min(MAX_PULL, dy * 0.55);
      armed = distance >= THRESHOLD;
      setIndicator(distance);
      if (dy > 12) event.preventDefault();
    },
    { passive: false }
  );

  const endTouch = () => {
    if (!tracking && !pulling) return;
    tracking = false;
    if (pulling && armed && !reloading) {
      pulling = false;
      reloading = true;
      indicator.classList.add("is-visible", "is-ready", "is-reloading");
      const text = indicator.querySelector(".pull-reload-text");
      if (text) text.textContent = "再読み込み中…";
      window.setTimeout(() => {
        window.location.reload();
      }, 180);
      return;
    }
    pulling = false;
    armed = false;
    resetIndicator();
  };

  host.addEventListener("touchend", endTouch);
  host.addEventListener("touchcancel", endTouch);
}

shiftCalendar?.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-staff-edit]");
  if (!trigger) return;
  event.preventDefault();
  hideStaffGaugePopover();
  closeCellEditor();
  window.openStaffEditor?.(Number(trigger.dataset.staffEdit));
});

window.addEventListener("staff:updated", () => {
  window.location.reload();
});
