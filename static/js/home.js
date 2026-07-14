const STORAGE_KEY = "shift-display-prefs";
const serverDefaults = window.APP_SETTINGS ?? {};

function defaultPrefs() {
  return {
    showJob: serverDefaults.default_show_job_column ?? true,
    showDept: serverDefaults.default_show_dept_column ?? true,
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
const homeShowDept = document.getElementById("home-show-dept");
const homeShowSummary = document.getElementById("home-show-summary");

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2;
const ZOOM_STEP = 0.1;
const SUPPORTS_CSS_ZOOM = typeof CSS !== "undefined" && CSS.supports?.("zoom", "1");

let tableZoom = defaultPrefs().tableZoom;
const previewBox = document.getElementById("print-preview-box");
const printColJob = document.getElementById("print-col-job");
const printColDept = document.getElementById("print-col-dept");
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
    showDept: document.getElementById("home-show-dept"),
    showSummary: document.getElementById("home-show-summary"),
  };
}

function getPrefs() {
  const defaults = defaultPrefs();
  const homeInputs = getHomeDisplayInputs();
  return {
    showJob: homeInputs.showJob?.checked ?? printColJob?.checked ?? defaults.showJob,
    showDept: homeInputs.showDept?.checked ?? printColDept?.checked ?? defaults.showDept,
    colorCells: homeInputs.colorCells?.checked ?? printColorMode?.checked ?? defaults.colorCells,
    showSummary: homeInputs.showSummary?.checked ?? defaults.showSummary,
  };
}

function applyDisplayPrefs(prefs = getPrefs()) {
  if (shiftCalendar) {
    shiftCalendar.classList.toggle("hide-col-job", !prefs.showJob);
    shiftCalendar.classList.toggle("hide-col-dept", !prefs.showDept);
    shiftCalendar.classList.toggle("hide-summary", !prefs.showSummary);
    shiftCalendar.classList.toggle("color-cells", prefs.colorCells);
    shiftCalendar.classList.toggle("mono-cells", !prefs.colorCells);
  }
  if (previewBox?.querySelector(".shift-table")) {
    previewBox.classList.toggle("hide-col-job", !prefs.showJob);
    previewBox.classList.toggle("hide-col-dept", !prefs.showDept);
    previewBox.classList.toggle("hide-summary", !prefs.showSummary);
    previewBox.classList.toggle("color-cells", prefs.colorCells);
    previewBox.classList.toggle("mono-cells", !prefs.colorCells);
  }
}

function syncControlsFromPrefs(prefs) {
  const homeInputs = getHomeDisplayInputs();
  if (homeInputs.showJob) homeInputs.showJob.checked = prefs.showJob;
  if (homeInputs.showDept) homeInputs.showDept.checked = prefs.showDept;
  if (homeInputs.colorCells) homeInputs.colorCells.checked = prefs.colorCells;
  if (homeInputs.showSummary) homeInputs.showSummary.checked = prefs.showSummary;
  if (printColJob) printColJob.checked = prefs.showJob;
  if (printColDept) printColDept.checked = prefs.showDept;
  if (printColorMode) printColorMode.checked = prefs.colorCells;
}

function updatePreviewNote() {
  if (!previewNote || !printModal) return;
  const paper = document.getElementById("print-paper")?.value ?? "A4 横";
  const scale = document.getElementById("print-scale")?.value ?? "100%";
  const prefs = getPrefs();
  const cols = ["職員名"];
  if (prefs.showJob) cols.push("職種");
  if (prefs.showDept) cols.push("フロア");
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
    if (SUPPORTS_CSS_ZOOM) {
      tableWrap.style.zoom = String(tableZoom);
      tableWrap.style.transform = "";
    } else {
      tableWrap.style.zoom = "";
      tableWrap.style.transform = `scale(${tableZoom})`;
      tableWrap.style.transformOrigin = "top left";
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
    document.querySelector(".home-toolbar-inline-tools .home-segment") ??
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

function applyRowFilters() {
  const selectedDepts = getSelectedFilterValues("dept");
  const selectedJobs = getSelectedFilterValues("job");
  const selectedPositions = getSelectedFilterValues("position");
  const tbody = shiftCalendar?.querySelector("tbody");
  if (!tbody) return;

  tbody.querySelectorAll("tr").forEach((row) => {
    const floors = (row.dataset.floors ?? row.dataset.dept ?? "").split(",").filter(Boolean);
    const matchDept =
      selectedDepts.length === 0 || floors.some((floor) => selectedDepts.includes(floor));
    const matchJob = selectedJobs.length === 0 || selectedJobs.includes(row.dataset.job ?? "");
    const rowPosition = row.dataset.position ?? "";
    const matchPosition =
      selectedPositions.length === 0 || selectedPositions.includes(rowPosition);
    row.hidden = !(matchDept && matchJob && matchPosition);
  });
  refreshSummaryCounts();
  saveFilterPrefs();
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
  homeToolbarTools?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-sort-mode]");
    if (!button || !homeToolbarTools.contains(button)) return;
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
  homeToolbarTools?.addEventListener("change", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    if (!["home-color-cells", "home-show-job", "home-show-dept", "home-show-summary"].includes(input.id)) {
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
  scheduleSortSegmentIndicatorUpdate();
  window.addEventListener("resize", scheduleSortSegmentIndicatorUpdate);
  const sortSegment =
    document.querySelector(".home-toolbar-inline-tools .home-segment") ??
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
    showDept: saved.showDept ?? defaultPrefs().showDept,
    colorCells: saved.colorCells ?? defaultPrefs().colorCells,
    showSummary: saved.showSummary ?? defaultPrefs().showSummary,
  };
  syncControlsFromPrefs(prefs);
  applyDisplayPrefs(prefs);
  updatePreviewNote();
}

function initTableZoom() {
  const saved = loadPrefs();
  const baseZoom = saved.tableZoom ?? defaultPrefs().tableZoom;
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

[printColJob, printColDept, printColorMode].forEach((input) => {
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
  if (!activeEditCell) return;
  activeEditCell.classList.remove("is-editing");
  activeEditCell = null;
  hideShiftPicker();
  hideFlickPad();
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

let flickPad = null;
let flickBackdrop = null;

function getFlickOptions() {
  return shiftOptions.slice(0, FLICK_MAX_OPTIONS);
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
    if (directionIndex >= 0 && directionIndex < options.length) {
      center.textContent = options[directionIndex].symbol;
      center.className = `shift-flick-center-symbol ${options[directionIndex].class}`;
    } else {
      const currentSymbol = activeEditCell?.dataset.symbol ?? "";
      const currentOption = shiftOptions.find((item) => item.symbol === currentSymbol);
      center.textContent = currentSymbol || "·";
      center.className = `shift-flick-center-symbol ${currentOption?.class ?? "shift-off"}`;
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
    const angle = (-90 + index * 45) * (Math.PI / 180);
    const left = centerX + radius * Math.cos(angle) - 28;
    const top = centerY + radius * Math.sin(angle) - 28;

    const button = document.createElement("div");
    button.className = `shift-flick-dir ${option.class}`;
    button.dataset.dirIndex = String(index);
    button.style.left = `${left}px`;
    button.style.top = `${top}px`;

    const symbolSpan = document.createElement("span");
    symbolSpan.className = "shift-flick-dir-symbol";
    symbolSpan.textContent = option.symbol;

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

function shiftClassList(symbol) {
  if (!symbol) return "shift-off";
  return symbolClassMap[symbol] ?? "shift-off";
}

function applyCellSymbol(td, symbol, options = {}) {
  const shiftClass = shiftClassList(symbol);
  const source = options.source ?? (options.manual ? "manual" : td.dataset.source ?? "");

  td.dataset.symbol = symbol;
  if (source) {
    td.dataset.source = source;
  } else {
    delete td.dataset.source;
  }

  let className = `day-col shift-td shift-td-editable ${shiftClass}`;
  if (source === "manual") className += " is-manual";
  if (source === "leave") className += " is-leave-request";
  td.className = className;

  const span = document.createElement("span");
  span.className = `shift-cell ${shiftClass}${source === "leave" ? " is-leave-request" : ""}`;
  span.textContent = symbol;
  td.replaceChildren(span);
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

  activeEditCell = td;
  td.classList.add("is-editing");

  const picker = ensureShiftPicker();
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
    symbolSpan.className = "shift-picker-symbol";
    symbolSpan.textContent = option.symbol;

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
  window.requestAnimationFrame(() => positionShiftPicker(picker, td));
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
  cellPointer = null;
}

function initShiftCellEditor() {
  shiftCalendar?.addEventListener("pointerdown", (event) => {
    const td = event.target.closest(".shift-td-editable");
    if (!td || !shiftCalendar.contains(td)) return;
    if (event.button !== 0) return;

    if (cellClickTimer) {
      clearTimeout(cellClickTimer);
      cellClickTimer = null;
    }
    resetCellPointer();

    const rect = td.getBoundingClientRect();
    cellPointer = {
      td,
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

    td.setPointerCapture?.(event.pointerId);

    if (flickInputEnabled()) {
      cellPointer.longPressTimer = window.setTimeout(() => {
        if (!cellPointer || cellPointer.cancelled || cellPointer.td !== td) return;
        closeCellEditor();
        cellPointer.flickActive = true;
        cellPointer.directionIndex = -1;
        openFlickPad(td);
        window.requestAnimationFrame(() => {
          if (!cellPointer?.flickActive || !flickPad) return;
          const padRect = flickPad.getBoundingClientRect();
          cellPointer.originX = padRect.left + padRect.width / 2;
          cellPointer.originY = padRect.top + padRect.height / 2;
        });
        navigator.vibrate?.(12);
      }, longPressMs());
    }
  });

  shiftCalendar?.addEventListener("pointermove", (event) => {
    if (!cellPointer || event.pointerId !== cellPointer.pointerId) return;

    const dx = event.clientX - cellPointer.startX;
    const dy = event.clientY - cellPointer.startY;

    if (!cellPointer.flickActive && cellPointer.longPressTimer) {
      if (Math.hypot(dx, dy) > POINTER_MOVE_CANCEL_PX) {
        clearTimeout(cellPointer.longPressTimer);
        cellPointer.longPressTimer = null;
        cellPointer.cancelled = true;
      }
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

    const { td, longPressTimer, flickActive, directionIndex, cancelled, startX, startY } = cellPointer;

    if (longPressTimer) {
      clearTimeout(longPressTimer);
    }

    cellPointer.td.releasePointerCapture?.(event.pointerId);

    if (flickActive) {
      const options = getFlickOptions();
      if (directionIndex >= 0 && directionIndex < options.length) {
        saveCellSymbol(td, options[directionIndex].symbol);
      } else {
        closeFlickPad();
      }
      resetCellPointer();
      return;
    }

    if (
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
    resetCellPointer();
  });

  shiftCalendar?.addEventListener("contextmenu", (event) => {
    if (!flickInputEnabled()) return;
    const td = event.target.closest(".shift-td-editable");
    if (!td || !shiftCalendar.contains(td)) return;
    event.preventDefault();
  });

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
    if (!activeEditCell) return;
    const pickerOpen = shiftPicker && !shiftPicker.classList.contains("hidden");
    const flickOpen = flickPad && !flickPad.classList.contains("hidden");
    if (!pickerOpen && !flickOpen) return;
    if (
      shiftPicker?.contains(event.target) ||
      flickPad?.contains(event.target) ||
      activeEditCell.contains(event.target)
    ) {
      return;
    }
    closeCellEditor();
  });

  tableWrap?.addEventListener(
    "scroll",
    () => {
      if (activeEditCell) closeCellEditor();
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

const autoGenerateButton = document.getElementById("btn-auto-generate");
const autoGenerateModal = document.getElementById("auto-generate-modal");
const autoGenerateModalTitle = document.getElementById("auto-generate-modal-title");
const autoGenerateModalSubtitle = document.getElementById("auto-generate-modal-subtitle");
const autoGenerateSummary = document.getElementById("auto-generate-summary");
const autoGenerateMessagesWrap = document.getElementById("auto-generate-messages-wrap");
const autoGenerateMessages = document.getElementById("auto-generate-messages");
const autoGenerateCloseBtn = document.getElementById("auto-generate-close-btn");

let autoGenerateShouldReload = false;

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
    const text = document.createElement("span");
    text.textContent = item.message || item.code || "詳細不明";
    li.append(label, text);
    autoGenerateMessages.appendChild(li);
  });
}

function showAutoGenerateResult({ success, title, subtitle, summary, messages = [], reload = false }) {
  autoGenerateShouldReload = reload;
  if (!autoGenerateModal) {
    window.alert([summary, ...messages.map((item) => item.message)].filter(Boolean).join("\n"));
    if (reload) window.location.reload();
    return;
  }
  if (autoGenerateModalTitle) autoGenerateModalTitle.textContent = title;
  if (autoGenerateModalSubtitle) autoGenerateModalSubtitle.textContent = subtitle || "";
  if (autoGenerateSummary) autoGenerateSummary.textContent = summary || "";
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

autoGenerateCloseBtn?.addEventListener("click", closeAutoGenerateModal);
document.querySelectorAll("[data-close-auto-generate-modal]").forEach((element) => {
  element.addEventListener("click", closeAutoGenerateModal);
});

async function runAutoGenerate() {
  const year = window.CALENDAR_YEAR;
  const month = window.CALENDAR_MONTH;
  if (!year || !month) return;

  const preview = window.confirm(
    `表示中のカレンダー区間（${window.PERIOD_LABEL || `${year}年${month}月`}）のシフトを自動生成します。\n\n` +
      "優先順位:\n" +
      "1. 手動選択分（手動入力済みセル）\n" +
      "2. 希望休\n" +
      "3. 担当フロア\n" +
      "4. 夜勤必要人員\n" +
      "5. 夜勤回数\n" +
      "6. 必要人員数・勤務割合\n" +
      "7. 日勤各割合\n\n" +
      "画面上に表示されている日付すべてが対象です（翌月にまたがる日も含みます）。\n" +
      "手動で入力済みのセル（赤枠）は上書きしません。実行しますか？"
  );
  if (!preview) return;

  autoGenerateButton.disabled = true;
  autoGenerateButton.textContent = "生成中…";
  try {
    const response = await fetch("/api/shifts/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year, month, preview: false }),
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
      });
      return;
    }

    showAutoGenerateResult({
      success,
      title: success
        ? warnCount > 0
          ? "自動生成が完了しました（警告あり）"
          : "自動生成が完了しました"
        : "自動生成は保存しました（エラーあり）",
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

autoGenerateButton?.addEventListener("click", runAutoGenerate);

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

shiftCalendar?.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-staff-edit]");
  if (!trigger) return;
  event.preventDefault();
  closeCellEditor();
  window.openStaffEditor?.(Number(trigger.dataset.staffEdit));
});

window.addEventListener("staff:updated", () => {
  window.location.reload();
});
