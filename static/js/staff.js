const API_BASE = "/api/staff";

const tbody = document.getElementById("staff-tbody");
const staffCount = document.getElementById("staff-count");
const alertBox = document.getElementById("alert");
const modal = document.getElementById("staff-modal");
const form = document.getElementById("staff-form");
const modalTitle = document.getElementById("modal-title");
const searchInput = document.getElementById("search-input");
const filterDepartment = document.getElementById("filter-department");
const filterJobType = document.getElementById("filter-job-type");
const sortStaffSelect = document.getElementById("sort-staff");
const nightIncompatibilityPicker = document.getElementById("field-night-incompatibilities");
const nightIncompatibilitySearch = document.getElementById("field-incompatibility-search");
const dayIncompatibilityPicker = document.getElementById("field-day-incompatibilities");
const dayIncompatibilitySearch = document.getElementById("field-day-incompatibility-search");
const floorPicker = document.getElementById("field-departments");
const staffingBasisPicker = document.getElementById("field-staffing-basis");
const staffingBasisBar = document.getElementById("staffing-basis-bar");
const staffingBasisTotal = document.getElementById("staffing-basis-total");
const staffingBasisTotalWrap = document.getElementById("staffing-basis-total-wrap");

const STAFFING_BASIS_LABELS = window.STAFFING_BASIS_LABELS ?? {};
const DEFAULT_STAFFING_BASIS = window.DEFAULT_STAFFING_BASIS ?? { early: 34, day: 33, night: 33 };
const STAFFING_PERIOD_DAYS = Number(window.STAFFING_PERIOD_DAYS) || 30;
const STAFFING_DEFAULT_OFF_DAYS = Number(window.STAFFING_DEFAULT_OFF_DAYS) || 0;
const STAFFING_DEFAULT_WORKING_DAYS = Number(window.STAFFING_DEFAULT_WORKING_DAYS) || STAFFING_PERIOD_DAYS;
const STAFFING_BASIS_COLORS = ["#2563eb", "#16a34a", "#f59e0b", "#7c3aed", "#dc2626", "#0891b2", "#db2777"];
const STAFFING_BASIS_HOURS = window.STAFFING_BASIS_HOURS ?? {};
const NIGHT_SHIFT_COUNTS_AS_TWO_DAYS = window.NIGHT_SHIFT_COUNTS_AS_TWO_DAYS !== false;
const REMOVED_STAFFING_BASIS_KEYS = new Set(["special", "leader"]);
const STAFFING_DAY_NIGHT_PAIRS = { day: "night", semi_day: "semi_night" };
const STAFF_SORT_STORAGE_KEY = "staff-list-sort";
const FLOOR_SORT_ORDER = window.STAFF_FLOOR_ORDER ?? [];
const JOB_SORT_ORDER = window.STAFF_JOB_ORDER ?? [];
const POSITION_SORT_ORDER = window.STAFF_POSITION_ORDER ?? [];
const DEFAULT_STAFF_SORT = window.DEFAULT_STAFF_SORT ?? "dept";

const TABLE_COLSPAN = 11;

const IS_STAFF_LIST_PAGE = Boolean(tbody);
const STAFF_EDITOR_OVERLAY = window.STAFF_EDITOR_OVERLAY === true;

let staffList = [];
let editingStaffId = null;
let bulkEditIds = null;
let selectedStaffIds = new Set();
let dragSelectActive = false;
let dragSelectAnchorId = null;
let dragSelectMode = true;
let dragPointerX = 0;
let dragPointerY = 0;
let dragAutoScrollFrame = null;
let selectedNightIncompatibilities = new Set();
let selectedDayIncompatibilities = new Set();
let nonNightRatioCeilings = {};

const staffTable = document.getElementById("staff-table");
const staffTableScroll = document.querySelector(".staff-table-scroll");
const DRAG_SCROLL_EDGE = 48;
const DRAG_SCROLL_MAX_STEP = 14;
const selectAllStaff = document.getElementById("select-all-staff");
const bulkActionBar = document.getElementById("bulk-action-bar");
const bulkActionButtons = document.getElementById("bulk-action-buttons");
const bulkSelectedCount = document.getElementById("bulk-selected-count");
const staffSelectionBadge = document.getElementById("staff-selection-badge");
const btnBulkEdit = document.getElementById("btn-bulk-edit");
const btnBulkInvert = document.getElementById("btn-bulk-invert");
const btnBulkClear = document.getElementById("btn-bulk-clear");
const bulkEditHeader = document.getElementById("bulk-edit-header");
const btnSave = document.getElementById("btn-save");
const fieldNameInput = document.getElementById("field-name");

function setModalMode(mode) {
  if (!modal) return;
  modal.classList.toggle("is-bulk-mode", mode === "bulk");
  modal.classList.toggle("is-single-mode", mode === "single");
  const jobTypeSelect = document.getElementById("field-job-type");
  if (jobTypeSelect) {
    jobTypeSelect.required = mode === "single";
  }
}

function syncEditorSurface() {
  if (!modal) return;
  modal.classList.toggle("is-overlay-mode", STAFF_EDITOR_OVERLAY);
  syncNightStaffingVisibility();
}

function canWorkNightFromForm() {
  return Boolean(document.getElementById("field-can-work-night")?.checked);
}

function syncNightStaffingVisibility() {
  if (!modal) return;
  modal.classList.toggle("is-night-eligible", canWorkNightFromForm());
}

function eligibleStaffingBasisKeys(canWorkNight = canWorkNightFromForm()) {
  if (!staffingBasisPicker) return [];
  return [...staffingBasisPicker.querySelectorAll(".staffing-basis-row")]
    .map((row) => row.dataset.key)
    .filter((key) => {
      if (!key) return false;
      if (!canWorkNight && (key === "night" || key === "semi_night")) {
        return false;
      }
      return true;
    });
}

function pruneStaffingBasisRatios(ratios, options = {}) {
  const canWorkNight = options.canWorkNight ?? canWorkNightFromForm();
  const allowed = new Set(eligibleStaffingBasisKeys(canWorkNight));
  if (!canWorkNight) {
    allowed.delete("night");
    allowed.delete("semi_night");
  }
  const cleaned = {};
  Object.entries(ratios).forEach(([key, value]) => {
    if (!allowed.has(key)) return;
    if (!canWorkNight && (key === "night" || key === "semi_night")) return;
    cleaned[key] = value;
  });
  return cleaned;
}

function clearNightStaffingBasis() {
  const current = getStaffingBasisRatiosFromForm();
  if (!("night" in current) && !("semi_night" in current)) return;
  const next = { ...current };
  delete next.night;
  delete next.semi_night;
  const keys = Object.keys(next);
  applyStaffingBasisRatios(
    keys.length ? fixStaffingBasisSum(distributeRemaining(100, keys, next), keys) : {}
  );
}

function resetBulkFieldGroup(group) {
  switch (group) {
    case "job_type":
      setSelectValue(document.getElementById("field-job-type"), "");
      break;
    case "position":
      setSelectValue(document.getElementById("field-position"), "");
      break;
    case "departments":
      setCheckboxGroup(floorPicker, "staff-floor", []);
      break;
    case "staffing": {
      clearNonNightRatioCeilings();
      applyStaffingBasisRatios({});
      const fixNightCountCheckbox = document.getElementById("field-fix-night-shift-count");
      const nightCountInput = document.getElementById("field-night-shift-count");
      if (fixNightCountCheckbox) fixNightCountCheckbox.checked = false;
      if (nightCountInput) nightCountInput.value = "";
      refreshStaffingBasisDisplay();
      break;
    }
    case "exclude_from_staffing":
      document.getElementById("field-exclude-from-staffing").checked = false;
      break;
    case "can_work_night":
      document.getElementById("field-can-work-night").checked = false;
      break;
    default:
      break;
  }
}

function resetBulkApplyFields() {
  document.querySelectorAll(".bulk-apply-checkbox").forEach((checkbox) => {
    checkbox.checked = false;
  });
  syncBulkFieldAvailability();
}

function syncBulkFieldAvailability() {
  const isBulk = Boolean(bulkEditIds?.length);
  document.querySelectorAll(".bulk-apply-checkbox").forEach((checkbox) => {
    const group = checkbox.dataset.bulkGroup;
    const active = !isBulk || checkbox.checked;
    document.querySelectorAll(`[data-bulk-field="${group}"]`).forEach((element) => {
      element.classList.toggle("is-bulk-active", active);
      if (!isBulk) return;
      element.querySelectorAll("select, input, textarea, button").forEach((control) => {
        if (control.classList.contains("bulk-apply-checkbox")) return;
        control.disabled = !active;
      });
    });
    if (group === "staffing" && isBulk && checkbox.checked) {
      refreshStaffingBasisDisplay();
    }
  });
  if (!isBulk) {
    updateNightShiftCountControls(getActiveStaffingBasisKeys().includes("night"));
  }
}

function isBulkApplyChecked(group) {
  if (!bulkEditIds?.length) return false;
  const checkbox = document.querySelector(`.bulk-apply-checkbox[data-bulk-group="${group}"]`);
  return Boolean(checkbox?.checked);
}

function getSelectedStaffRecords() {
  return staffList.filter((staff) => selectedStaffIds.has(staff.id));
}

function formatSelectionCount(count) {
  if (count === 0) return "選択: 0件";
  return `${count}件選択中`;
}

function updateBulkActionBar() {
  const count = selectedStaffIds.size;
  const hasSelection = count > 0;

  bulkActionBar?.classList.toggle("has-selection", hasSelection);
  bulkActionButtons?.classList.toggle("hidden", !hasSelection);

  if (bulkSelectedCount) {
    bulkSelectedCount.textContent = formatSelectionCount(count);
  }

  if (staffSelectionBadge) {
    staffSelectionBadge.textContent = String(count);
    staffSelectionBadge.classList.toggle("is-empty", !hasSelection);
    staffSelectionBadge.setAttribute("aria-hidden", hasSelection ? "false" : "true");
    staffSelectionBadge.setAttribute(
      "aria-label",
      hasSelection ? `${count}件選択中` : "選択なし"
    );
  }

  staffTable?.classList.toggle("has-selection", hasSelection);
  syncSelectAllCheckbox();
  updateStaffCountMeta();
}

function updateStaffCountMeta(visibleCount = filteredStaff().length) {
  if (!staffCount) return;
  const selectedCount = selectedStaffIds.size;
  const base = `表示 ${visibleCount} 件 / 全 ${staffList.length} 件`;
  staffCount.textContent =
    selectedCount > 0 ? `${base} · ${selectedCount}件選択中` : base;
}

function updateRowSelectionVisuals() {
  if (!tbody) return;
  tbody.querySelectorAll("tr[data-staff-id]").forEach((row) => {
    const staffId = Number(row.dataset.staffId);
    const selected = selectedStaffIds.has(staffId);
    row.classList.toggle("is-selected", selected);
    const checkbox = row.querySelector(".staff-row-select");
    if (checkbox) checkbox.checked = selected;
  });
}

function visibleStaffIds() {
  return filteredStaff().map((staff) => staff.id);
}

function getStaffIdFromPointer(clientX, clientY) {
  const element = document.elementFromPoint(clientX, clientY);
  const row = element?.closest("tr[data-staff-id]");
  if (!row || !tbody?.contains(row)) return null;
  return Number(row.dataset.staffId) || null;
}

function getVisibleRowStaffIds() {
  if (!staffTableScroll || !tbody) {
    return { first: null, last: null };
  }

  const scrollRect = staffTableScroll.getBoundingClientRect();
  const rows = [...tbody.querySelectorAll("tr[data-staff-id]")];
  let first = null;
  let last = null;

  rows.forEach((row) => {
    const rect = row.getBoundingClientRect();
    if (rect.bottom < scrollRect.top || rect.top > scrollRect.bottom) return;
    const staffId = Number(row.dataset.staffId);
    if (!staffId) return;
    if (first == null) first = staffId;
    last = staffId;
  });

  return { first, last };
}

function updateDragSelectionAtPointer(clientX, clientY) {
  if (!dragSelectActive) return;

  let staffId = getStaffIdFromPointer(clientX, clientY);
  if (!staffId && staffTableScroll) {
    const rect = staffTableScroll.getBoundingClientRect();
    const { first, last } = getVisibleRowStaffIds();
    if (clientY < rect.top + DRAG_SCROLL_EDGE && first != null) {
      staffId = first;
    } else if (clientY > rect.bottom - DRAG_SCROLL_EDGE && last != null) {
      staffId = last;
    }
  }

  if (staffId) applyDragSelectionRange(staffId);
}

function needsDragAutoScroll() {
  if (!staffTableScroll) return false;
  const rect = staffTableScroll.getBoundingClientRect();
  return (
    dragPointerY < rect.top + DRAG_SCROLL_EDGE ||
    dragPointerY > rect.bottom - DRAG_SCROLL_EDGE
  );
}

function stopDragAutoScroll() {
  if (dragAutoScrollFrame != null) {
    cancelAnimationFrame(dragAutoScrollFrame);
    dragAutoScrollFrame = null;
  }
}

function dragAutoScrollLoop() {
  dragAutoScrollFrame = null;
  if (!dragSelectActive || !staffTableScroll) return;

  const rect = staffTableScroll.getBoundingClientRect();
  let scrollDelta = 0;

  if (dragPointerY < rect.top + DRAG_SCROLL_EDGE) {
    const depth = rect.top + DRAG_SCROLL_EDGE - dragPointerY;
    const intensity = Math.min(1, depth / DRAG_SCROLL_EDGE);
    scrollDelta = -Math.max(1, Math.round(DRAG_SCROLL_MAX_STEP * intensity));
  } else if (dragPointerY > rect.bottom - DRAG_SCROLL_EDGE) {
    const depth = dragPointerY - (rect.bottom - DRAG_SCROLL_EDGE);
    const intensity = Math.min(1, depth / DRAG_SCROLL_EDGE);
    scrollDelta = Math.max(1, Math.round(DRAG_SCROLL_MAX_STEP * intensity));
  }

  if (scrollDelta !== 0) {
    const maxScroll = staffTableScroll.scrollHeight - staffTableScroll.clientHeight;
    const nextScrollTop = Math.max(
      0,
      Math.min(maxScroll, staffTableScroll.scrollTop + scrollDelta)
    );
    if (nextScrollTop !== staffTableScroll.scrollTop) {
      staffTableScroll.scrollTop = nextScrollTop;
      updateDragSelectionAtPointer(dragPointerX, dragPointerY);
    }
  }

  if (dragSelectActive && needsDragAutoScroll()) {
    dragAutoScrollFrame = requestAnimationFrame(dragAutoScrollLoop);
  }
}

function ensureDragAutoScroll() {
  if (!needsDragAutoScroll()) {
    stopDragAutoScroll();
    return;
  }
  if (dragAutoScrollFrame == null) {
    dragAutoScrollFrame = requestAnimationFrame(dragAutoScrollLoop);
  }
}

function onDragSelectPointerMove(event) {
  if (!dragSelectActive) return;
  dragPointerX = event.clientX;
  dragPointerY = event.clientY;
  updateDragSelectionAtPointer(event.clientX, event.clientY);
  ensureDragAutoScroll();
}

function applyDragSelectionRange(endStaffId) {
  const ids = visibleStaffIds();
  const anchorIndex = ids.indexOf(dragSelectAnchorId);
  const endIndex = ids.indexOf(endStaffId);
  if (anchorIndex === -1 || endIndex === -1) return;

  const start = Math.min(anchorIndex, endIndex);
  const end = Math.max(anchorIndex, endIndex);
  for (let index = start; index <= end; index += 1) {
    setStaffSelected(ids[index], dragSelectMode, { skipBarUpdate: true });
  }
  updateRowSelectionVisuals();
  updateBulkActionBar();
}

function startDragSelect(staffId, clientX, clientY) {
  dragSelectActive = true;
  dragSelectAnchorId = staffId;
  dragSelectMode = !selectedStaffIds.has(staffId);
  dragPointerX = clientX;
  dragPointerY = clientY;
  staffTable?.classList.add("is-drag-selecting");
  document.addEventListener("mousemove", onDragSelectPointerMove);
  applyDragSelectionRange(staffId);
  ensureDragAutoScroll();
}

function endDragSelect() {
  if (!dragSelectActive) return;
  dragSelectActive = false;
  dragSelectAnchorId = null;
  document.removeEventListener("mousemove", onDragSelectPointerMove);
  stopDragAutoScroll();
  staffTable?.classList.remove("is-drag-selecting");
  syncSelectAllCheckbox();
}

function syncSelectAllCheckbox() {
  if (!selectAllStaff) return;
  const rows = filteredStaff();
  const allSelected = rows.length > 0 && rows.every((staff) => selectedStaffIds.has(staff.id));
  const someSelected = rows.some((staff) => selectedStaffIds.has(staff.id));
  selectAllStaff.checked = allSelected;
  selectAllStaff.indeterminate = someSelected && !allSelected;
}

function setStaffSelected(staffId, selected, options = {}) {
  if (selected) selectedStaffIds.add(staffId);
  else selectedStaffIds.delete(staffId);
  if (!options.skipBarUpdate) updateBulkActionBar();
}

function clearStaffSelection() {
  selectedStaffIds.clear();
  updateBulkActionBar();
  renderTable();
}

function invertStaffSelection() {
  const rows = filteredStaff();
  if (!rows.length) return;
  rows.forEach((staff) => {
    setStaffSelected(staff.id, !selectedStaffIds.has(staff.id), { skipBarUpdate: true });
  });
  updateRowSelectionVisuals();
  updateBulkActionBar();
  syncSelectAllCheckbox();
}

function showAlert(message, type = "success") {
  if (!alertBox) return;
  alertBox.textContent = message;
  alertBox.className = `alert alert-${type}`;
  alertBox.classList.remove("hidden");
  window.setTimeout(() => alertBox.classList.add("hidden"), 4000);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function staffNameMap() {
  return Object.fromEntries(staffList.map((staff) => [staff.id, staff.name]));
}

function floorBadgeClass(floor) {
  const slug = String(floor).toLowerCase();
  return ["1f", "2f", "3f", "4f"].includes(slug) ? `floor-badge--${slug}` : "floor-badge--default";
}

function formatDepartments(staff) {
  const floors = staffFloors(staff);
  if (!floors.length) return '<span class="text-muted">-</span>';
  return `<span class="floor-badges">${floors
    .map(
      (floor) =>
        `<span class="floor-badge ${floorBadgeClass(floor)}" title="${escapeHtml(floor)}">${escapeHtml(floor)}</span>`
    )
    .join("")}</span>`;
}

function normalizeStaffingBasisRatios(raw) {
  if (Array.isArray(raw)) {
    return equalSplitStaffingBasis(raw.filter((key) => !REMOVED_STAFFING_BASIS_KEYS.has(key)));
  }
  if (raw && typeof raw === "object") {
    const ratios = {};
    Object.entries(raw).forEach(([key, value]) => {
      if (REMOVED_STAFFING_BASIS_KEYS.has(key)) return;
      const ratio = Number(value);
      if (key && Number.isFinite(ratio) && ratio > 0) {
        ratios[key] = Math.min(100, Math.max(1, Math.round(ratio)));
      }
    });
    return ratios;
  }
  return { ...DEFAULT_STAFFING_BASIS };
}

function equalSplitStaffingBasis(keys) {
  const cleaned = [...new Set(keys.filter(Boolean))];
  if (!cleaned.length) return {};
  const base = Math.floor(100 / cleaned.length);
  const remainder = 100 - base * cleaned.length;
  const ratios = {};
  cleaned.forEach((key, index) => {
    ratios[key] = base + (index < remainder ? 1 : 0);
  });
  return ratios;
}

function getStaffingOffDays() {
  return STAFFING_DEFAULT_OFF_DAYS;
}

function staffingBasisDayWeight(basisKey) {
  if (basisKey === "night" && NIGHT_SHIFT_COUNTS_AS_TWO_DAYS) return 2;
  return 1;
}

function nightShiftDayWeightNote() {
  return NIGHT_SHIFT_COUNTS_AS_TWO_DAYS ? "2日換算" : "1日換算";
}

function getNightShiftCount(overrideValue) {
  if (overrideValue != null && Number.isFinite(Number(overrideValue))) {
    return Math.max(0, Math.min(STAFFING_PERIOD_DAYS, Math.round(Number(overrideValue))));
  }
  const input = document.getElementById("field-night-shift-count");
  if (!input || input.value === "") return null;
  const value = Number(input.value);
  if (!Number.isFinite(value) || value < 0) return null;
  return Math.max(0, Math.min(STAFFING_PERIOD_DAYS, Math.round(value)));
}

function isNightShiftCountFixed(overrideValue) {
  if (overrideValue != null) return Boolean(overrideValue);
  const checkbox = document.getElementById("field-fix-night-shift-count");
  return Boolean(checkbox?.checked);
}

function getEffectiveNightShiftCount(overrideFixed, overrideCount) {
  const fixed = overrideFixed !== undefined ? overrideFixed : isNightShiftCountFixed();
  if (!fixed) return null;
  return overrideCount !== undefined ? overrideCount : getNightShiftCount();
}

function clearNonNightRatioCeilings() {
  nonNightRatioCeilings = {};
}

function captureNonNightRatioCeilings(ratios) {
  nonNightRatioCeilings = {};
  Object.entries(ratios).forEach(([key, ratio]) => {
    if (key !== "night" && Number.isFinite(ratio) && ratio > 0) {
      nonNightRatioCeilings[key] = Math.round(ratio);
    }
  });
}

function getNonNightRatioCeiling(key) {
  return nonNightRatioCeilings[key];
}

function syncNonNightRatioCeilings(ratios) {
  if (!isNightShiftCountFixed() || getNightShiftCount() == null) {
    clearNonNightRatioCeilings();
    return;
  }
  if (Object.keys(nonNightRatioCeilings).length === 0) {
    captureNonNightRatioCeilings(ratios ?? getStaffingBasisRatiosFromForm());
  }
}

function isNightShiftCountLocked() {
  return (
    getActiveStaffingBasisKeys().includes("night") &&
    isNightShiftCountFixed() &&
    getEffectiveNightShiftCount() != null
  );
}

function updateNightShiftCountControls(nightActive) {
  const fixCheckbox = document.getElementById("field-fix-night-shift-count");
  const countInput = document.getElementById("field-night-shift-count");
  if (fixCheckbox) {
    fixCheckbox.disabled = !nightActive;
  }
  if (countInput) {
    countInput.disabled = !nightActive || !isNightShiftCountFixed();
  }
}

function approximateNightDaysFromCount(count) {
  if (count == null) return null;
  return count * staffingBasisDayWeight("night");
}

function getDistributionPool(overrideOffDays) {
  return Math.max(0, STAFFING_PERIOD_DAYS - getStaffingOffDays(overrideOffDays));
}

function isDayStaffingBasisKey(key) {
  return key === "early" || key === "day" || key === "late" || key === "semi_early" || key === "semi_day" || key === "semi_late";
}

function resolveNightShiftCount(ratios, overrideOffDays, overrideNightCount, overrideNightFixed) {
  const fixedCount =
    overrideNightCount !== undefined
      ? overrideNightCount
      : getEffectiveNightShiftCount(overrideNightFixed);
  if (fixedCount != null) return fixedCount;
  const pool = getDistributionPool(overrideOffDays);
  const nightRatio = (ratios.night ?? 0) + (ratios.semi_night ?? 0);
  if (!nightRatio) return 0;
  return Math.round((pool * nightRatio) / 100);
}

function nonNightDayRatioTotal(ratios) {
  return Object.entries(ratios).reduce((sum, [key, ratio]) => {
    if (key === "night" || key === "semi_night") return sum;
    return isDayStaffingBasisKey(key) ? sum + ratio : sum;
  }, 0);
}

function getDayCapacityForRatios(ratios, overrideOffDays, overrideNightCount, overrideNightFixed) {
  const pool = getDistributionPool(overrideOffDays);
  const nightCount = resolveNightShiftCount(ratios, overrideOffDays, overrideNightCount, overrideNightFixed);
  return Math.max(0, pool - nightCount - nightCount);
}

function getStaffingWorkingDays(overrideOffDays) {
  return Math.max(1, getDistributionPool(overrideOffDays));
}

function approximateStaffingDays(ratio, overrideOffDays, basisKey, options = {}) {
  if (!ratio) return 0;
  const ratios = options.ratios ?? {};
  if (basisKey === "night" || basisKey === "semi_night") {
    const count = resolveNightShiftCount(
      Object.keys(ratios).length ? ratios : { [basisKey]: ratio },
      overrideOffDays,
      options.overrideNightCount,
      options.overrideNightFixed
    );
    return approximateNightDaysFromCount(count) ?? 0;
  }
  const activeRatios = Object.keys(ratios).length ? ratios : { [basisKey]: ratio };
  const dayCapacity = getDayCapacityForRatios(
    activeRatios,
    overrideOffDays,
    options.overrideNightCount,
    options.overrideNightFixed
  );
  const nonNightTotal = nonNightDayRatioTotal(activeRatios);
  if (!nonNightTotal) return 0;
  return Math.round((dayCapacity * ratio) / nonNightTotal);
}

function sumApproximateStaffingDays(ratios, overrideOffDays, overrideNightCount, overrideNightFixed) {
  const nightCount =
    overrideNightCount !== undefined
      ? overrideNightCount
      : getEffectiveNightShiftCount(overrideNightFixed);
  return Object.entries(ratios).reduce((sum, [key, ratio]) => {
    if (key === "night" && nightCount != null) {
      return sum + approximateNightDaysFromCount(nightCount);
    }
    return (
      sum +
      approximateStaffingDays(ratio, overrideOffDays, key, {
        ratios,
        overrideNightCount,
        overrideNightFixed,
      })
    );
  }, 0);
}

function refreshStaffingBasisDisplay() {
  const ratios = getStaffingBasisRatiosFromForm();
  if (Object.keys(ratios).length) {
    applyStaffingBasisRatios(ratios);
  } else {
    renderStaffingBasisBar();
    updateStaffingBasisTotal();
  }
}

function formatStaffingBasisValue(ratio, overrideOffDays, basisKey, overrideNightCount, overrideNightFixed) {
  if (!ratio) return "—";
  if (basisKey === "night") {
    const count =
      overrideNightCount !== undefined
        ? overrideNightCount
        : getEffectiveNightShiftCount(overrideNightFixed);
    if (count != null) {
      const days = approximateNightDaysFromCount(count);
      return `<span class="staffing-basis-percent">${ratio}%</span><span class="staffing-basis-days">${count}回（約${days}日）</span><span class="staffing-basis-days-note">固定・${nightShiftDayWeightNote()}</span>`;
    }
  }
  const days = approximateStaffingDays(ratio, overrideOffDays, basisKey, {
    ratios: getStaffingBasisRatiosFromForm(),
    overrideNightCount,
    overrideNightFixed,
  });
  const note = basisKey === "night" ? `<span class="staffing-basis-days-note">${nightShiftDayWeightNote()}</span>` : "";
  return `<span class="staffing-basis-percent">${ratio}%</span><span class="staffing-basis-days">約${days}日</span>${note}`;
}

function staffingBasisColor(key) {
  const row = staffingBasisPicker?.querySelector(`.staffing-basis-row[data-key="${key}"]`);
  const index = Number(row?.dataset.colorIndex ?? 0);
  return STAFFING_BASIS_COLORS[index % STAFFING_BASIS_COLORS.length];
}

function getActiveStaffingBasisKeys() {
  if (!staffingBasisPicker) return [];
  return [...staffingBasisPicker.querySelectorAll(".staffing-basis-row.is-active")]
    .map((row) => row.dataset.key)
    .filter(Boolean);
}

function getStaffingBasisRatiosFromForm() {
  const ratios = {};
  getActiveStaffingBasisKeys().forEach((key) => {
    const slider = staffingBasisPicker?.querySelector(`.staffing-basis-slider[data-key="${key}"]`);
    const ratio = Number(slider?.value);
    if (Number.isFinite(ratio) && ratio > 0) {
      ratios[key] = Math.min(100, Math.max(1, Math.round(ratio)));
    }
  });
  return ratios;
}

function fixStaffingBasisSum(ratios, keys) {
  const fixed = { ...ratios };
  const ordered = keys.filter((key) => fixed[key] != null);
  if (!ordered.length) return fixed;

  let total = ordered.reduce((sum, key) => sum + fixed[key], 0);
  if (total === 100) return fixed;

  const lastKey = ordered[ordered.length - 1];
  fixed[lastKey] = Math.max(1, fixed[lastKey] + (100 - total));
  total = ordered.reduce((sum, key) => sum + fixed[key], 0);
  if (total !== 100) {
    fixed[lastKey] = Math.max(1, fixed[lastKey] - (total - 100));
  }
  return fixed;
}

function distributeRemaining(total, keys, weights = {}) {
  if (!keys.length) return {};
  if (keys.length === 1) return { [keys[0]]: total };

  const weightSum = keys.reduce((sum, key) => sum + Math.max(weights[key] ?? 1, 1), 0);
  const result = {};
  let allocated = 0;

  keys.forEach((key, index) => {
    if (index === keys.length - 1) {
      result[key] = Math.max(1, total - allocated);
      return;
    }
    const weight = Math.max(weights[key] ?? 1, 1);
    const value = Math.max(1, Math.round((total * weight) / weightSum));
    result[key] = value;
    allocated += value;
  });

  return fixStaffingBasisSum(result, keys);
}

function balanceStaffingBasisFromSlider(changedKey, newValue) {
  const keys = getActiveStaffingBasisKeys();
  if (!keys.includes(changedKey)) return;

  const current = getStaffingBasisRatiosFromForm();
  const locked = isNightShiftCountLocked();

  if (keys.length === 1) {
    applyStaffingBasisRatios({ [changedKey]: 100 });
    return;
  }

  const maxValue = 100 - (keys.length - 1);
  const clamped = Math.min(maxValue, Math.max(1, Math.round(Number(newValue) || 1)));

  if (locked && changedKey !== "night") {
    const currentValue = current[changedKey] ?? 1;
    const ceiling = getNonNightRatioCeiling(changedKey);
    let nextValue = clamped;
    if (ceiling != null) {
      nextValue = Math.min(nextValue, ceiling);
    }

    if (nextValue > currentValue) {
      const delta = nextValue - currentValue;
      const nightRatio = current.night ?? 1;
      const transferable = Math.min(delta, Math.max(0, nightRatio - 1));
      nextValue = currentValue + transferable;
      if (transferable === 0) {
        applyStaffingBasisRatios(current);
        return;
      }
      applyStaffingBasisRatios(
        fixStaffingBasisSum(
          {
            ...current,
            [changedKey]: nextValue,
            night: nightRatio - transferable,
          },
          keys
        )
      );
      return;
    }

    if (nextValue < currentValue) {
      const delta = currentValue - nextValue;
      const nightRatio = current.night ?? 1;
      applyStaffingBasisRatios(
        fixStaffingBasisSum(
          {
            ...current,
            [changedKey]: nextValue,
            night: Math.min(maxValue, nightRatio + delta),
          },
          keys
        )
      );
      return;
    }

    applyStaffingBasisRatios(current);
    return;
  }

  const others = keys.filter((key) => key !== changedKey);
  const remaining = 100 - clamped;
  const distributed = distributeRemaining(remaining, others, current);
  applyStaffingBasisRatios(fixStaffingBasisSum({ [changedKey]: clamped, ...distributed }, keys));
}

function toggleStaffingBasisKey(key, active) {
  if (active && !canWorkNightFromForm() && (key === "night" || key === "semi_night")) {
    return;
  }
  const current = getStaffingBasisRatiosFromForm();
  const locked = isNightShiftCountLocked();

  if (active) {
    const pairedNight = STAFFING_DAY_NIGHT_PAIRS[key];
    if (pairedNight && !(pairedNight in current) && !locked) {
      const keys = [...new Set([...Object.keys(current), key, pairedNight])];
      applyStaffingBasisRatios(equalSplitStaffingBasis(keys));
      return;
    }

    if (locked) {
      if (key in current) {
        return;
      }
      if (key === "night") {
        applyStaffingBasisRatios({ ...current, night: current.night ?? 1 });
        return;
      }
      const keys = [...Object.keys(current), key];
      const nightRatio = current.night ?? 1;
      if (nightRatio <= 1) {
        showAlert("夜勤固定中は夜勤の割合をこれ以上減らせません。", "error");
        return;
      }
      applyStaffingBasisRatios(
        fixStaffingBasisSum({ ...current, [key]: 1, night: nightRatio - 1 }, keys)
      );
      nonNightRatioCeilings[key] = 1;
      return;
    }

    const keys = [...new Set([...Object.keys(current), key])];
    applyStaffingBasisRatios(equalSplitStaffingBasis(keys));
    return;
  }

  const keys = Object.keys(current).filter((item) => item !== key);
  if (!keys.length) {
    applyStaffingBasisRatios({});
    return;
  }
  if (locked && keys.includes("night")) {
    const freed = current[key] ?? 0;
    const newRatios = { ...current };
    delete newRatios[key];
    newRatios.night = (newRatios.night ?? 1) + freed;
    applyStaffingBasisRatios(fixStaffingBasisSum(newRatios, keys));
    return;
  }
  applyStaffingBasisRatios(distributeRemaining(100, keys, current));
}

function applyStaffingBasisRatios(ratios) {
  if (!staffingBasisPicker) return;

  const activeKeys = Object.keys(ratios);
  const maxForOne = Math.max(1, 100 - (activeKeys.length - 1));
  const locked = isNightShiftCountLocked();

  staffingBasisPicker.querySelectorAll(".staffing-basis-row").forEach((row) => {
    const key = row.dataset.key;
    const ratio = ratios[key];
    const active = ratio != null;
    const chip = row.querySelector(".staffing-basis-chip");
    const slider = row.querySelector(".staffing-basis-slider");
    const valueEl = row.querySelector(".staffing-basis-value");

    row.classList.toggle("is-active", active);
    const ceiling = getNonNightRatioCeiling(key);
    row.classList.toggle(
      "is-ratio-capped",
      locked && active && key !== "night" && ceiling != null && ratio >= ceiling
    );
    if (chip) {
      chip.setAttribute("aria-pressed", active ? "true" : "false");
      chip.style.background = active ? staffingBasisColor(key) : "";
      const label = STAFFING_BASIS_LABELS[key] ?? key;
      const hours = STAFFING_BASIS_HOURS[key];
      chip.title = hours ? `${label} ${hours}` : label;
      const hoursEl = chip.querySelector(".staffing-basis-chip-hours");
      if (hoursEl) {
        hoursEl.textContent = hours ?? "";
        hoursEl.hidden = !hours;
      }
    }
    if (slider) {
      slider.disabled = !active;
      let sliderMax = active ? maxForOne : 100;
      if (locked && active && key !== "night" && ceiling != null) {
        sliderMax = Math.min(sliderMax, ceiling);
      }
      slider.max = String(sliderMax);
      slider.value = active ? String(ratio) : "1";
      slider.title =
        locked && active && key !== "night" && ceiling != null
          ? `上限${ceiling}%（固定時の割合まで調整できます）`
          : "";
    }
    if (valueEl) {
      valueEl.innerHTML = active ? formatStaffingBasisValue(ratio, undefined, key) : "—";
    }
    if (key === "night") {
      updateNightShiftCountControls(active);
    }
  });

  renderStaffingBasisBar();
  updateStaffingBasisTotal();
}

function renderStaffingBasisBar() {
  if (!staffingBasisBar) return;
  const ratios = getStaffingBasisRatiosFromForm();
  const entries = Object.entries(ratios);

  if (!entries.length) {
    staffingBasisBar.innerHTML = '<div class="staffing-basis-bar-empty"></div>';
    return;
  }

  staffingBasisBar.innerHTML = entries
    .map(([key, ratio]) => {
      const label = STAFFING_BASIS_LABELS[key] ?? key;
      const nightCount = key === "night" ? getEffectiveNightShiftCount() : null;
      const days =
        nightCount != null
          ? approximateNightDaysFromCount(nightCount)
          : approximateStaffingDays(ratio, undefined, key, { ratios });
      const weightNote =
        key === "night" && nightCount != null
          ? "・固定"
          : key === "night" && staffingBasisDayWeight(key) > 1
            ? `・${nightShiftDayWeightNote()}`
            : "";
      return `<div class="staffing-basis-bar-segment" style="width:${ratio}%;background:${staffingBasisColor(key)}" title="${escapeHtml(label)} ${ratio}%（約${days}日${weightNote}）"></div>`;
    })
    .join("");
}

function setStaffingBasisRatios(ratios) {
  applyStaffingBasisRatios(normalizeStaffingBasisRatios(ratios));
}

function redistributeStaffingBasisRatios() {
  if (isNightShiftCountLocked()) {
    showAlert("夜勤回数固定中は均等配分できません。", "error");
    return;
  }
  applyStaffingBasisRatios(equalSplitStaffingBasis(getActiveStaffingBasisKeys()));
}

function updateStaffingBasisTotal() {
  if (!staffingBasisTotal || !staffingBasisTotalWrap) return;
  const ratios = getStaffingBasisRatiosFromForm();
  const total = Object.values(ratios).reduce((sum, value) => sum + value, 0);
  const hasSelection = Object.keys(ratios).length > 0;
  const approxDays = hasSelection ? sumApproximateStaffingDays(ratios) : 0;
  staffingBasisTotal.textContent = hasSelection ? `${total}%（約${approxDays}日）` : "0%";
  staffingBasisTotalWrap.classList.toggle("is-valid", total === 100 && hasSelection);
  staffingBasisTotalWrap.classList.toggle("is-invalid", total !== 100 && hasSelection);
}

function formatStaffingBasis(staff) {
  const ratios = normalizeStaffingBasisRatios(staff.staffing_basis ?? {});
  const entries = Object.entries(ratios);
  if (!entries.length) return '<span class="text-muted">-</span>';
  const offDays = STAFFING_DEFAULT_OFF_DAYS;
  const labels = entries.map(([key, ratio]) => {
    const label = STAFFING_BASIS_LABELS[key] ?? key;
    if (key === "night" && staff.fix_night_shift_count && staff.night_shift_count != null) {
      const days = staff.night_shift_count * staffingBasisDayWeight("night");
      return `${label}${ratio}%（固定${staff.night_shift_count}回・約${days}日）`;
    }
    return `${label}${ratio}%（約${approximateStaffingDays(ratio, offDays, key, { ratios })}日）`;
  });
  return escapeHtml(labels.join("、"));
}

function formatStaffingCount(staff) {
  if (staff.exclude_from_staffing) {
    return '<span class="badge badge-muted">含めない</span>';
  }
  return '<span class="badge badge-ok">含める</span>';
}

function formatIncompatibilities(ids) {
  const names = (ids ?? []).map((id) => staffNameMap()[id]).filter(Boolean);
  if (!names.length) return '<span class="text-muted">なし</span>';
  const label = names.join("、");
  return `<span class="incompatibility-tags" title="${escapeHtml(label)}">${escapeHtml(label)}</span>`;
}

function staffFloors(staff) {
  return staff.departments?.length ? staff.departments : [staff.department].filter(Boolean);
}

function staffSortMode() {
  return sortStaffSelect?.value || DEFAULT_STAFF_SORT;
}

function initStaffSortSelect() {
  if (!sortStaffSelect) return;
  const stored = localStorage.getItem(STAFF_SORT_STORAGE_KEY);
  const allowed = [...sortStaffSelect.options].map((option) => option.value);
  if (stored && allowed.includes(stored)) {
    sortStaffSelect.value = stored;
  } else if (stored) {
    localStorage.removeItem(STAFF_SORT_STORAGE_KEY);
  }
}

function compareStaffRows(a, b) {
  const mode = staffSortMode();
  const floorOrder = Object.fromEntries(FLOOR_SORT_ORDER.map((label, index) => [label, index]));
  const jobOrder = Object.fromEntries(JOB_SORT_ORDER.map((label, index) => [label, index]));
  const positionOrder = Object.fromEntries(POSITION_SORT_ORDER.map((label, index) => [label, index]));
  const byName = () => a.name.localeCompare(b.name, "ja");

  if (mode === "name") {
    return byName();
  }
  if (mode === "job") {
    const jobDiff = (jobOrder[a.job_type] ?? 999) - (jobOrder[b.job_type] ?? 999);
    return jobDiff || byName();
  }
  if (mode === "position") {
    const posA = a.position || "";
    const posB = b.position || "";
    const rank = (value) => {
      if (!value) return 999;
      return positionOrder[value] ?? 998;
    };
    return rank(posA) - rank(posB) || byName();
  }

  const floorA = staffFloors(a)[0] ?? "";
  const floorB = staffFloors(b)[0] ?? "";
  const floorDiff = (floorOrder[floorA] ?? 999) - (floorOrder[floorB] ?? 999);
  return floorDiff || byName();
}

function filteredStaff() {
  const query = searchInput.value.trim().toLowerCase();
  const dept = filterDepartment.value;
  const job = filterJobType.value;

  return staffList
    .filter((staff) => {
      const floors = staffFloors(staff).join(" ");
      const haystack = `${staff.name} ${floors} ${staff.job_type} ${staff.position}`.toLowerCase();
      if (query && !haystack.includes(query)) return false;
      if (dept && !staffFloors(staff).includes(dept)) return false;
      if (job && staff.job_type !== job) return false;
      return true;
    })
    .sort(compareStaffRows);
}

function renderTable() {
  if (!tbody) return;
  const rows = filteredStaff();

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${TABLE_COLSPAN}" class="empty-cell">職員が登録されていません</td></tr>`;
  } else {
    tbody.innerHTML = rows
      .map(
        (staff) => `
      <tr data-staff-id="${staff.id}" class="staff-list-row ${selectedStaffIds.has(staff.id) ? "is-selected" : ""}" title="ダブルクリックで編集">
        <td class="col-check staff-select-cell">
          <input
            type="checkbox"
            class="staff-row-select"
            data-select="${staff.id}"
            aria-label="${escapeHtml(staff.name)}を選択"
            ${selectedStaffIds.has(staff.id) ? "checked" : ""}
          >
        </td>
        <td>${escapeHtml(staff.name)}</td>
        <td class="col-floor">${formatDepartments(staff)}</td>
        <td>${escapeHtml(staff.job_type)}</td>
        <td>${escapeHtml(staff.position || "-")}</td>
        <td>${formatStaffingBasis(staff)}</td>
        <td>${formatStaffingCount(staff)}</td>
        <td>
          <span class="badge ${staff.can_work_night ? "badge-ok" : "badge-muted"}">
            ${staff.can_work_night ? "可" : "不可"}
          </span>
        </td>
        <td>${formatIncompatibilities(staff.day_incompatible_ids)}</td>
        <td>${formatIncompatibilities(staff.night_incompatible_ids)}</td>
        <td class="col-actions">
          <button type="button" class="btn btn-sm btn-danger" data-delete="${staff.id}">削除</button>
        </td>
      </tr>`
      )
      .join("");
  }

  updateStaffCountMeta(rows.length);
  syncSelectAllCheckbox();
}

function incompatibilityCandidates(searchInputEl) {
  const query = searchInputEl?.value.trim().toLowerCase() ?? "";
  return staffList
    .filter((staff) => staff.id !== editingStaffId)
    .filter((staff) => {
      if (!query) return true;
      const floors = staffFloors(staff).join(" ");
      const haystack = `${staff.name} ${floors} ${staff.job_type}`.toLowerCase();
      return haystack.includes(query);
    })
    .sort((a, b) => a.name.localeCompare(b.name, "ja"));
}

function renderIncompatibilityPicker(pickerEl, searchInputEl, selectedSet, inputName) {
  if (!pickerEl) return;

  const candidates = incompatibilityCandidates(searchInputEl);

  if (!candidates.length) {
    pickerEl.innerHTML = '<p class="empty-cell">選択できる職員がいません</p>';
    return;
  }

  pickerEl.innerHTML = candidates
    .map(
      (staff) => `
      <label class="check-row incompatibility-option">
        <input
          type="checkbox"
          name="${inputName}"
          value="${staff.id}"
          ${selectedSet.has(staff.id) ? "checked" : ""}
        >
        <span>${escapeHtml(staff.name)}（${escapeHtml(staffFloors(staff).join("、"))} / ${escapeHtml(staff.job_type)}）</span>
      </label>`
    )
    .join("");
}

function renderNightIncompatibilityPicker() {
  renderIncompatibilityPicker(
    nightIncompatibilityPicker,
    nightIncompatibilitySearch,
    selectedNightIncompatibilities,
    "night-incompatible"
  );
}

function renderDayIncompatibilityPicker() {
  renderIncompatibilityPicker(
    dayIncompatibilityPicker,
    dayIncompatibilitySearch,
    selectedDayIncompatibilities,
    "day-incompatible"
  );
}

function setCheckboxGroup(container, name, selectedValues) {
  if (!container) return;
  const selected = new Set(selectedValues);
  container.querySelectorAll(`input[name="${name}"]`).forEach((input) => {
    input.checked = selected.has(input.value);
  });
}

function getCheckboxGroupValues(container, name) {
  if (!container) return [];
  return [...container.querySelectorAll(`input[name="${name}"]:checked`)].map((input) => input.value);
}

function mergeNightIncompatibilities() {
  return [...new Set([...selectedNightIncompatibilities, ...selectedDayIncompatibilities])];
}

function addDayIncompatibility(staffId) {
  selectedDayIncompatibilities.add(staffId);
  selectedNightIncompatibilities.add(staffId);
  renderNightIncompatibilityPicker();
}

function addDayIncompatibilities(staffIds) {
  staffIds.forEach((staffId) => {
    selectedDayIncompatibilities.add(staffId);
    selectedNightIncompatibilities.add(staffId);
  });
  renderNightIncompatibilityPicker();
}

function setAllCheckboxes(name, checked) {
  if (name === "staff-floor") {
    floorPicker?.querySelectorAll(`input[name="${name}"]`).forEach((input) => {
      input.checked = checked;
    });
    return;
  }
  if (name === "staffing-basis") {
    if (checked) {
      if (isNightShiftCountLocked()) {
        showAlert("夜勤回数固定中はすべて選択・均等配分できません。", "error");
        return;
      }
      const keys = eligibleStaffingBasisKeys();
      applyStaffingBasisRatios(equalSplitStaffingBasis(keys));
    } else {
      applyStaffingBasisRatios({});
    }
    return;
  }
  if (name === "night-incompatible") {
    if (checked) {
      incompatibilityCandidates(nightIncompatibilitySearch).forEach((staff) => {
        selectedNightIncompatibilities.add(staff.id);
      });
    } else {
      selectedNightIncompatibilities.clear();
    }
    renderNightIncompatibilityPicker();
    return;
  }
  if (name === "day-incompatible") {
    if (checked) {
      addDayIncompatibilities(
        incompatibilityCandidates(dayIncompatibilitySearch).map((staff) => staff.id)
      );
    } else {
      selectedDayIncompatibilities.clear();
    }
    renderDayIncompatibilityPicker();
  }
}

function invertAllCheckboxes(name) {
  if (name === "staff-floor") {
    floorPicker?.querySelectorAll(`input[name="${name}"]`).forEach((input) => {
      input.checked = !input.checked;
    });
    return;
  }
  if (name === "staffing-basis") {
    if (isNightShiftCountLocked()) {
      showAlert("夜勤回数固定中は反転できません。", "error");
      return;
    }
    const eligible = eligibleStaffingBasisKeys();
    const active = new Set(getActiveStaffingBasisKeys());
    const inverted = eligible.filter((key) => !active.has(key));
    applyStaffingBasisRatios(inverted.length ? equalSplitStaffingBasis(inverted) : {});
    return;
  }
  if (name === "night-incompatible") {
    incompatibilityCandidates(nightIncompatibilitySearch).forEach((staff) => {
      if (selectedNightIncompatibilities.has(staff.id)) {
        selectedNightIncompatibilities.delete(staff.id);
      } else {
        selectedNightIncompatibilities.add(staff.id);
      }
    });
    renderNightIncompatibilityPicker();
    return;
  }
  if (name === "day-incompatible") {
    incompatibilityCandidates(dayIncompatibilitySearch).forEach((staff) => {
      if (selectedDayIncompatibilities.has(staff.id)) {
        selectedDayIncompatibilities.delete(staff.id);
        selectedNightIncompatibilities.delete(staff.id);
      } else {
        addDayIncompatibility(staff.id);
      }
    });
    renderDayIncompatibilityPicker();
    renderNightIncompatibilityPicker();
  }
}

async function ensureStaffList() {
  if (staffList.length) return staffList;
  const response = await fetch(API_BASE);
  if (!response.ok) {
    throw new Error("職員一覧の取得に失敗しました");
  }
  staffList = await response.json();
  return staffList;
}

async function loadStaff() {
  await ensureStaffList();
  if (tbody) renderTable();
  if (IS_STAFF_LIST_PAGE) openStaffFromQuery();
}

async function openStaffEditor(staffId) {
  if (!modal) return;
  try {
    await ensureStaffList();
  } catch {
    showAlert("データの読み込みに失敗しました", "error");
    return;
  }
  const numericId = Number(staffId);
  let staff = staffList.find((item) => item.id === numericId);
  if (!staff) {
    const response = await fetch(`${API_BASE}/${numericId}`);
    if (!response.ok) {
      showAlert("職員情報の取得に失敗しました", "error");
      return;
    }
    staff = await response.json();
    staffList.push(staff);
  }
  openModal("edit", staff);
}

window.openStaffEditor = openStaffEditor;

function openStaffFromQuery() {
  const editId = new URLSearchParams(location.search).get("edit");
  if (!editId) return;
  const staff = staffList.find((item) => item.id === Number(editId));
  if (!staff) return;
  openModal("edit", staff);
  const url = new URL(location.href);
  url.searchParams.delete("edit");
  history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

function ensureSelectOption(select, value, suffix = "（未登録）") {
  if (!select || !value) return;
  const exists = [...select.options].some((option) => option.value === value);
  if (exists) return;
  const option = document.createElement("option");
  option.value = value;
  option.textContent = `${value}${suffix}`;
  select.appendChild(option);
}

function setSelectValue(select, value) {
  if (!select) return;
  ensureSelectOption(select, value);
  select.value = value ?? "";
}

function openBulkModal() {
  const ids = [...selectedStaffIds];
  if (!ids.length) {
    showAlert("一括編集する職員を選択してください。", "error");
    return;
  }

  bulkEditIds = ids;
  editingStaffId = null;
  setModalMode("bulk");
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.getElementById("staff-id").value = "";
  if (fieldNameInput) {
    fieldNameInput.required = false;
    fieldNameInput.value = "";
  }

  const targets = getSelectedStaffRecords();
  document.getElementById("bulk-target-count").textContent = String(ids.length);
  document.getElementById("bulk-target-names").textContent = targets.map((staff) => staff.name).join("、");
  bulkEditHeader?.classList.remove("hidden");

  resetBulkApplyFields();
  setSelectValue(document.getElementById("field-job-type"), "");
  setSelectValue(document.getElementById("field-position"), "");
  document.getElementById("field-can-work-night").checked = false;
  document.getElementById("field-exclude-from-staffing").checked = false;
  const fixNightCountCheckbox = document.getElementById("field-fix-night-shift-count");
  const nightCountInput = document.getElementById("field-night-shift-count");
  if (fixNightCountCheckbox) fixNightCountCheckbox.checked = false;
  if (nightCountInput) nightCountInput.value = "";
  setCheckboxGroup(floorPicker, "staff-floor", []);
  clearNonNightRatioCeilings();
  applyStaffingBasisRatios({});
  refreshStaffingBasisDisplay();
  syncBulkFieldAvailability();
  modalTitle.textContent = "職員一括編集";
  if (btnSave) btnSave.textContent = "一括保存";
}

function openModal(mode, staff = null) {
  bulkEditIds = null;
  setModalMode("single");
  syncEditorSurface();
  bulkEditHeader?.classList.add("hidden");
  if (fieldNameInput) fieldNameInput.required = true;
  if (btnSave) btnSave.textContent = "保存";
  editingStaffId = staff?.id ?? null;
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.getElementById("staff-id").value = staff?.id ?? "";
  document.getElementById("field-name").value = staff?.name ?? "";
  setSelectValue(document.getElementById("field-job-type"), staff?.job_type ?? "");
  setSelectValue(document.getElementById("field-position"), staff?.position ?? "");
  document.getElementById("field-can-work-night").checked = staff?.can_work_night ?? false;
  document.getElementById("field-exclude-from-staffing").checked = staff?.exclude_from_staffing ?? false;
  const fixNightCountCheckbox = document.getElementById("field-fix-night-shift-count");
  const nightCountInput = document.getElementById("field-night-shift-count");
  if (fixNightCountCheckbox) {
    fixNightCountCheckbox.checked = Boolean(
      staff?.fix_night_shift_count ?? staff?.night_shift_count != null
    );
  }
  if (nightCountInput) {
    nightCountInput.value =
      staff?.night_shift_count != null ? String(staff.night_shift_count) : "";
  }
  setCheckboxGroup(floorPicker, "staff-floor", staff?.departments ?? []);
  clearNonNightRatioCeilings();
  let staffingRatios = pruneStaffingBasisRatios(
    normalizeStaffingBasisRatios(staff?.staffing_basis ?? DEFAULT_STAFFING_BASIS),
    { canWorkNight: staff?.can_work_night ?? false }
  );
  if (!Object.keys(staffingRatios).length) {
    staffingRatios = pruneStaffingBasisRatios(DEFAULT_STAFFING_BASIS, {
      canWorkNight: staff?.can_work_night ?? false,
    });
  }
  setStaffingBasisRatios(staffingRatios);
  if (
    (staff?.fix_night_shift_count || staff?.night_shift_count != null) &&
    staff?.night_shift_count != null
  ) {
    captureNonNightRatioCeilings(staffingRatios);
  }
  refreshStaffingBasisDisplay();
  if (nightIncompatibilitySearch) nightIncompatibilitySearch.value = "";
  if (dayIncompatibilitySearch) dayIncompatibilitySearch.value = "";
  selectedNightIncompatibilities = new Set(staff?.night_incompatible_ids ?? []);
  selectedDayIncompatibilities = new Set(staff?.day_incompatible_ids ?? []);
  renderNightIncompatibilityPicker();
  renderDayIncompatibilityPicker();
  syncBulkFieldAvailability();
  modalTitle.textContent = mode === "edit" ? "職員編集" : "職員登録";
}

function closeModal() {
  editingStaffId = null;
  bulkEditIds = null;
  setModalMode("single");
  bulkEditHeader?.classList.add("hidden");
  if (fieldNameInput) fieldNameInput.required = true;
  if (btnSave) btnSave.textContent = "保存";
  resetBulkApplyFields();
  syncBulkFieldAvailability();
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  form.reset();
  clearNonNightRatioCeilings();
  if (nightIncompatibilityPicker) nightIncompatibilityPicker.innerHTML = "";
  if (dayIncompatibilityPicker) dayIncompatibilityPicker.innerHTML = "";
  if (nightIncompatibilitySearch) nightIncompatibilitySearch.value = "";
  if (dayIncompatibilitySearch) dayIncompatibilitySearch.value = "";
  selectedNightIncompatibilities = new Set();
  selectedDayIncompatibilities = new Set();
}

async function saveBulkStaff() {
  const ids = bulkEditIds ?? [];
  if (!ids.length) return;

  const payload = { ids };
  const applyJobType = isBulkApplyChecked("job_type");
  const applyPosition = isBulkApplyChecked("position");
  const applyDepartments = isBulkApplyChecked("departments");
  const applyStaffing = isBulkApplyChecked("staffing");
  const applyExclude = isBulkApplyChecked("exclude_from_staffing");
  const applyNight = isBulkApplyChecked("can_work_night");

  if (!applyJobType && !applyPosition && !applyDepartments && !applyStaffing && !applyExclude && !applyNight) {
    showAlert("変更する項目を1つ以上選択してください。", "error");
    return;
  }

  if (applyJobType) {
    const jobType = document.getElementById("field-job-type").value.trim();
    if (!jobType) {
      showAlert("職種を選択してください。", "error");
      return;
    }
    payload.job_type = jobType;
  }

  if (applyPosition) {
    payload.position = document.getElementById("field-position").value.trim();
  }

  if (applyDepartments) {
    const departments = getCheckboxGroupValues(floorPicker, "staff-floor");
    if (!departments.length) {
      showAlert("担当フロアを1つ以上選択してください。", "error");
      return;
    }
    payload.departments = departments;
  }

  if (applyStaffing) {
    const staffingBasis = getStaffingBasisRatiosFromForm();
    if (!Object.keys(staffingBasis).length) {
      showAlert("勤務割合を1つ以上選択してください。", "error");
      return;
    }
    const staffingTotal = Object.values(staffingBasis).reduce((sum, value) => sum + value, 0);
    if (staffingTotal !== 100) {
      showAlert(`勤務割合の合計は100%にしてください（現在${staffingTotal}%）。`, "error");
      return;
    }
    payload.staffing_basis = staffingBasis;

    const nightActive = getActiveStaffingBasisKeys().includes("night");
    const fixNightCount = nightActive && isNightShiftCountFixed();
    const nightCount = fixNightCount ? getNightShiftCount() : null;
    if (fixNightCount && nightCount == null) {
      showAlert("夜勤回数を固定する場合は回数を入力してください。", "error");
      return;
    }
    payload.fix_night_shift_count = fixNightCount;
    payload.night_shift_count = fixNightCount ? nightCount : null;
  }

  if (applyExclude) {
    payload.exclude_from_staffing = document.getElementById("field-exclude-from-staffing").checked;
  }

  if (applyNight) {
    payload.can_work_night = document.getElementById("field-can-work-night").checked;
  }

  const response = await fetch(`${API_BASE}/bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = error.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail[0]?.msg
          : undefined;
    showAlert(message ?? "一括保存に失敗しました", "error");
    return;
  }

  const result = await response.json();
  closeModal();
  await loadStaff();
  const skipped = result.not_found?.length ?? 0;
  const message =
    skipped > 0
      ? `${result.updated}件を更新しました（${skipped}件は見つかりませんでした）`
      : `${result.updated}件の職員情報を更新しました`;
  showAlert(message);
}

async function saveStaff(event) {
  event.preventDefault();

  if (bulkEditIds?.length) {
    await saveBulkStaff();
    return;
  }

  const departments = getCheckboxGroupValues(floorPicker, "staff-floor");
  const staffingBasis = getStaffingBasisRatiosFromForm();

  if (!departments.length) {
    showAlert("担当フロアを1つ以上選択してください。", "error");
    return;
  }
  if (!Object.keys(staffingBasis).length) {
    showAlert("勤務割合を1つ以上選択してください。", "error");
    return;
  }
  const staffingTotal = Object.values(staffingBasis).reduce((sum, value) => sum + value, 0);
  if (staffingTotal !== 100) {
    showAlert(`勤務割合の合計は100%にしてください（現在${staffingTotal}%）。`, "error");
    return;
  }

  const jobType = document.getElementById("field-job-type").value.trim();
  if (!jobType) {
    showAlert("職種を選択してください。", "error");
    return;
  }

  const id = document.getElementById("staff-id").value;
  const nightActive = getActiveStaffingBasisKeys().includes("night");
  const fixNightCount = nightActive && isNightShiftCountFixed();
  const nightCount = fixNightCount ? getNightShiftCount() : null;
  if (fixNightCount && nightCount == null) {
    showAlert("夜勤回数を固定する場合は回数を入力してください。", "error");
    return;
  }

  const payload = {
    name: document.getElementById("field-name").value.trim(),
    departments,
    job_type: jobType,
    position: document.getElementById("field-position").value.trim(),
    can_work_night: document.getElementById("field-can-work-night").checked,
    staffing_basis: staffingBasis,
    exclude_from_staffing: document.getElementById("field-exclude-from-staffing").checked,
    fix_night_shift_count: fixNightCount,
    night_shift_count: fixNightCount ? nightCount : null,
    day_incompatible_ids: [...selectedDayIncompatibilities],
    night_incompatible_ids: mergeNightIncompatibilities(),
  };

  const isEdit = Boolean(id);
  const response = await fetch(isEdit ? `${API_BASE}/${id}` : API_BASE, {
    method: isEdit ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = error.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail[0]?.msg
          : undefined;
    showAlert(message ?? "保存に失敗しました", "error");
    return;
  }

  closeModal();
  staffList = [];
  if (tbody) {
    await loadStaff();
  }
  showAlert(isEdit ? "職員情報を更新しました" : "職員を登録しました");
  if (STAFF_EDITOR_OVERLAY) {
    window.dispatchEvent(new CustomEvent("staff:updated"));
  }
}

async function deleteStaff(id) {
  const staff = staffList.find((item) => item.id === id);
  const floors = staff ? staffFloors(staff).join("、") : "";
  const label = staff ? `${staff.name}（${floors}）` : `ID ${id}`;
  if (!window.confirm(`${label} を削除しますか？`)) return;

  const response = await fetch(`${API_BASE}/${id}`, { method: "DELETE" });
  if (!response.ok) {
    showAlert("削除に失敗しました", "error");
    return;
  }

  await loadStaff();
  showAlert("職員を削除しました");
}

document.getElementById("btn-add")?.addEventListener("click", () => openModal("create"));
document.getElementById("btn-add-footer")?.addEventListener("click", () => openModal("create"));
btnBulkEdit?.addEventListener("click", openBulkModal);
btnBulkInvert?.addEventListener("click", invertStaffSelection);
btnBulkClear?.addEventListener("click", clearStaffSelection);

selectAllStaff?.addEventListener("change", (event) => {
  const checked = event.target.checked;
  filteredStaff().forEach((staff) => {
    if (checked) selectedStaffIds.add(staff.id);
    else selectedStaffIds.delete(staff.id);
  });
  updateBulkActionBar();
  renderTable();
});

document.querySelectorAll(".bulk-apply-checkbox").forEach((checkbox) => {
  checkbox.addEventListener("change", () => {
    if (checkbox.checked && bulkEditIds?.length) {
      resetBulkFieldGroup(checkbox.dataset.bulkGroup);
    }
    syncBulkFieldAvailability();
  });
});

staffingBasisPicker?.addEventListener("click", (event) => {
  const chip = event.target.closest(".staffing-basis-chip");
  if (!chip) return;
  event.preventDefault();
  const key = chip.dataset.key;
  const active = chip.getAttribute("aria-pressed") === "true";
  toggleStaffingBasisKey(key, !active);
});

staffingBasisPicker?.addEventListener("input", (event) => {
  if (!event.target.classList.contains("staffing-basis-slider")) return;
  balanceStaffingBasisFromSlider(event.target.dataset.key, event.target.value);
});

document.getElementById("field-can-work-night")?.addEventListener("change", (event) => {
  syncNightStaffingVisibility();
  if (!event.target.checked) {
    clearNightStaffingBasis();
  }
});

document.getElementById("field-fix-night-shift-count")?.addEventListener("change", () => {
  if (isNightShiftCountFixed()) {
    syncNonNightRatioCeilings();
  } else {
    clearNonNightRatioCeilings();
  }
  updateNightShiftCountControls(getActiveStaffingBasisKeys().includes("night"));
  refreshStaffingBasisDisplay();
});
document.getElementById("field-night-shift-count")?.addEventListener("input", () => {
  if (isNightShiftCountFixed()) {
    syncNonNightRatioCeilings();
  }
  refreshStaffingBasisDisplay();
});

form?.addEventListener("submit", saveStaff);
searchInput?.addEventListener("input", renderTable);
filterDepartment?.addEventListener("change", renderTable);
filterJobType?.addEventListener("change", renderTable);
sortStaffSelect?.addEventListener("change", () => {
  localStorage.setItem(STAFF_SORT_STORAGE_KEY, staffSortMode());
  renderTable();
});
nightIncompatibilitySearch?.addEventListener("input", renderNightIncompatibilityPicker);
dayIncompatibilitySearch?.addEventListener("input", renderDayIncompatibilityPicker);

nightIncompatibilityPicker?.addEventListener("change", (event) => {
  const input = event.target;
  if (input.name !== "night-incompatible") return;
  const staffId = Number(input.value);
  if (input.checked) {
    selectedNightIncompatibilities.add(staffId);
  } else {
    selectedNightIncompatibilities.delete(staffId);
  }
});

dayIncompatibilityPicker?.addEventListener("change", (event) => {
  const input = event.target;
  if (input.name !== "day-incompatible") return;
  const staffId = Number(input.value);
  if (input.checked) {
    addDayIncompatibility(staffId);
  } else {
    selectedDayIncompatibilities.delete(staffId);
  }
});

form?.addEventListener("click", (event) => {
  const selectAll = event.target.closest("[data-select-all]");
  if (selectAll) {
    event.preventDefault();
    setAllCheckboxes(selectAll.dataset.selectAll, true);
    return;
  }
  const clearAll = event.target.closest("[data-clear-all]");
  if (clearAll) {
    event.preventDefault();
    setAllCheckboxes(clearAll.dataset.clearAll, false);
    return;
  }
  const invertAll = event.target.closest("[data-invert-all]");
  if (invertAll) {
    event.preventDefault();
    invertAllCheckboxes(invertAll.dataset.invertAll);
    return;
  }
  const staffingAction = event.target.closest("[data-staffing-basis-action]");
  if (staffingAction) {
    event.preventDefault();
    if (staffingAction.dataset.staffingBasisAction === "equal") {
      redistributeStaffingBasisRatios();
    }
  }
});

document.querySelectorAll("[data-close-modal]").forEach((element) => {
  element.addEventListener("click", closeModal);
});

tbody?.addEventListener("mousedown", (event) => {
  if (event.button !== 0) return;
  const selectCell = event.target.closest(".staff-select-cell");
  if (!selectCell) return;

  const row = selectCell.closest("tr[data-staff-id]");
  const staffId = Number(row?.dataset.staffId);
  if (!staffId) return;

  event.preventDefault();
  startDragSelect(staffId, event.clientX, event.clientY);
});

document.addEventListener("mouseup", endDragSelect);

tbody?.addEventListener("keydown", (event) => {
  if (event.key !== " " && event.key !== "Enter") return;
  const checkbox = event.target.closest(".staff-row-select");
  if (!checkbox) return;
  event.preventDefault();
  const staffId = Number(checkbox.dataset.select);
  setStaffSelected(staffId, !selectedStaffIds.has(staffId));
  updateRowSelectionVisuals();
});

tbody?.addEventListener("click", (event) => {
  if (event.target.closest(".staff-select-cell")) {
    event.preventDefault();
    return;
  }

  const deleteId = event.target.dataset.delete;
  if (deleteId) {
    deleteStaff(Number(deleteId));
  }
});

tbody?.addEventListener("dblclick", (event) => {
  if (event.target.closest(".staff-select-cell, .col-actions, button, a, input, label")) return;
  const row = event.target.closest("tr[data-staff-id]");
  if (!row) return;
  const staff = staffList.find((item) => item.id === Number(row.dataset.staffId));
  if (staff) openModal("edit", staff);
});

if (IS_STAFF_LIST_PAGE) {
  initStaffSortSelect();
  loadStaff().catch(() => {
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="${TABLE_COLSPAN}" class="empty-cell">データの読み込みに失敗しました</td></tr>`;
    showAlert("データの読み込みに失敗しました", "error");
  });
  updateBulkActionBar();
} else if (modal) {
  syncEditorSurface();
  ensureStaffList().catch(() => {});
}
