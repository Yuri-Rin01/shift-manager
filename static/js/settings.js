const form = document.getElementById("settings-form");
const alertBox = document.getElementById("settings-alert");
const resetButton = document.getElementById("btn-reset-defaults");

const HASH_TO_PANEL = {
  "section-top": "top",
  "section-facility": "facility",
  "section-display": "display",
  "section-print": "print",
  "section-staffing": "staffing",
  "section-alert": "alert",
  "section-auto": "auto",
  "section-account-plan": "account",
  "section-security": "security",
  "section-notify": "notify",
};

function redirectLegacySettingsHash() {
  const hash = location.hash.replace("#", "");
  if (!hash) return;
  const panel = HASH_TO_PANEL[hash];
  if (!panel) return;
  const params = new URLSearchParams(location.search);
  if (params.has("panel")) return;
  const target = panel === "top" ? "/settings" : `/settings?panel=${panel}`;
  location.replace(target);
}

redirectLegacySettingsHash();

const panelSelect = document.getElementById("settings-panel-select");
if (panelSelect) {
  panelSelect.addEventListener("change", (event) => {
    const target = event.target.value;
    if (target && target !== location.pathname + location.search) {
      location.href = target;
    }
  });
}

const SHIFT_SYMBOL_PREFIX = "shift_symbol__";
const VISIBLE_WORK_TYPE_PREFIX = "visible_work_type__";
const FIXED_VISIBLE_WORK_TYPES = new Set(["morning_off"]);
const staffingBasisTbody = document.getElementById("staffing-basis-tbody");
const addStaffingBasisButton = document.getElementById("btn-add-staffing-basis");
const workTypeMinStaffTbody = document.getElementById("work-type-min-staff-tbody");
const workTypeMinStaffEmpty = document.getElementById("work-type-min-staff-empty");
const syncWorkTypeMinStaffButton = document.getElementById("btn-sync-work-type-min-staff");
const timeSlotStaffingTbody = document.getElementById("time-slot-staffing-tbody");
const addTimeSlotButton = document.getElementById("btn-add-time-slot");
const floorNightMinStaffTbody = document.getElementById("floor-night-min-staff-tbody");
const nightLeaderGroupsTbody = document.getElementById("night-leader-groups-tbody");
const addNightLeaderGroupButton = document.getElementById("btn-add-night-leader-group");
const nightLeaderGroupsPanel = document.getElementById("night-leader-groups-panel");
const requireLeaderOnNightInput = document.getElementById("require-leader-on-night");
const workTypeMinStaffPanel = document.getElementById("panel-work-type-min-staff");
const timeSlotStaffingPanel = document.getElementById("panel-time-slot-staffing");
const workTypeTemplateSelect = document.getElementById("work-type-template-select");
const applyWorkTypeTemplateButton = document.getElementById("btn-apply-work-type-template");
const WORK_TYPE_TEMPLATES = window.WORK_TYPE_TEMPLATES ?? [];
const NIGHT_WORK_KEYS = new Set(["night", "semi_night"]);
const FLOOR_LABELS = window.FLOOR_LABELS ?? ["1F", "2F", "3F", "4F"];
const DEFAULT_NIGHT_LEADER_GROUPS = [
  { label: "1・2階", floors: ["1F", "2F"], min_leaders: 1 },
  { label: "2・3階", floors: ["2F", "3F"], min_leaders: 1 },
];

const INT_FIELDS = new Set([
  "max_consecutive_days",
  "max_night_per_week",
  "leave_alert_threshold",
  "leave_fulfill_target",
  "log_retention_days",
  "session_timeout_minutes",
  "require_password_change_days",
  "deadline_day_of_month",
  "default_table_zoom",
  "calendar_start_day",
  "cell_long_press_ms",
]);

function showAlert(message, type = "success") {
  if (!alertBox) return;
  alertBox.textContent = message;
  alertBox.className = `alert alert-${type}`;
  alertBox.classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function hideAlert() {
  alertBox?.classList.add("hidden");
}

function formatWorkHoursPreview(startTime, endTime) {
  const start = startTime?.trim() ?? "";
  const end = endTime?.trim() ?? "";
  if (!start && !end) return "—";
  if (!start || !end) return start || end;
  if (end < start) return `${start}〜翌${end}`;
  return `${start}〜${end}`;
}

function updateHoursPreview(row) {
  const preview = row.querySelector(".staffing-basis-hours-preview");
  if (!preview) return;
  const start = row.querySelector(".staffing-basis-start")?.value ?? "";
  const end = row.querySelector(".staffing-basis-end")?.value ?? "";
  preview.textContent = formatWorkHoursPreview(start, end);
}

function syncAllHoursPreviews() {
  staffingBasisTbody?.querySelectorAll(".staffing-basis-table-row").forEach(updateHoursPreview);
}

function defaultWorkTypeRow() {
  return { key: "", label: "", start_time: "09:00", end_time: "18:00" };
}

function defaultTimeSlotRow() {
  return { floor: FLOOR_LABELS[0] ?? "", label: "", start_time: "09:00", end_time: "18:00", min_staff: 1 };
}

function defaultMinStaffForKey(key) {
  const defaults = { early: 1, day: 2, night: 1 };
  return defaults[key] ?? 0;
}

function getShiftSymbolMap() {
  return collectShiftSymbols();
}

function collectRegisteredWorkTypes() {
  return collectStaffingBasisOptions().filter((item) => item.key && item.label);
}

function toMinutes(timeStr) {
  if (!timeStr || !timeStr.includes(":")) return 0;
  const [hour, minute] = timeStr.split(":").map((part) => Number.parseInt(part, 10));
  return hour * 60 + (minute || 0);
}

function segmentsOverlap(left, right) {
  return left[0] < right[1] && right[0] < left[1];
}

function workSegmentsForOffset(startTime, endTime, offset) {
  const start = toMinutes(startTime);
  const end = toMinutes(endTime);
  if (offset === 0) {
    if (end > start) return [[start, end]];
    return [[start, 1440]];
  }
  if (end < start) return [[0, end]];
  return [];
}

function slotSegmentsForDisplay(startTime, endTime) {
  const start = toMinutes(startTime);
  const end = toMinutes(endTime);
  if (end > start) return [{ segment: [start, end], offset: 0 }];
  return [
    { segment: [0, end], offset: -1, note: "翌朝" },
    { segment: [start, 1440], offset: 0, note: "当日夜" },
  ];
}

function workTypeCoversSlotSegment(workType, segmentInfo) {
  for (const workSegment of workSegmentsForOffset(
    workType.start_time,
    workType.end_time,
    segmentInfo.offset
  )) {
    if (segmentsOverlap(workSegment, segmentInfo.segment)) {
      return true;
    }
  }
  return false;
}

function isOvernightTimeRange(startTime, endTime) {
  return Boolean(startTime && endTime && endTime < startTime);
}

function isNightWorkKey(key) {
  return NIGHT_WORK_KEYS.has(String(key || "").trim());
}

function workTypesCoveringSlot(startTime, endTime, workTypes) {
  if (!startTime || !endTime) return [];
  // 夜勤は別枠のため、時間帯の対象区分プレビューから除外
  const dayTypes = workTypes.filter((item) => !isNightWorkKey(item.key));
  const matched = new Set();
  for (const segmentInfo of slotSegmentsForDisplay(startTime, endTime)) {
    for (const workType of dayTypes) {
      if (workTypeCoversSlotSegment(workType, segmentInfo)) {
        matched.add(workType.label);
      }
    }
  }
  return [...matched];
}

function renderStaffingBasisRows(options = []) {
  if (!staffingBasisTbody) return;
  const symbols = getShiftSymbolMap();
  const rows = options.length ? options : [defaultWorkTypeRow()];
  staffingBasisTbody.innerHTML = rows
    .map(
      (item, index) => `
      <tr class="staffing-basis-table-row" data-index="${index}" data-key="${escapeAttr(item.key ?? "")}">
        <td>
          <input
            type="text"
            class="input-text staffing-basis-label"
            maxlength="20"
            placeholder="例: 早番"
            value="${escapeAttr(item.label ?? "")}"
            aria-label="勤務区分 ${index + 1}"
          >
        </td>
        <td class="col-work-type-key">
          <input
            type="text"
            class="input-text staffing-basis-key input-text-muted"
            maxlength="20"
            pattern="[a-z][a-z0-9_]*"
            placeholder="early"
            value="${escapeAttr(item.key ?? "")}"
            aria-label="内部キー ${index + 1}"
          >
        </td>
        <td class="col-work-type-symbol">
          <span class="staffing-basis-symbol-preview" data-symbol-key="${escapeAttr(item.key ?? "")}">${escapeAttr(symbols[item.key] ?? "—")}</span>
        </td>
        <td class="staffing-basis-time-cell">
          <div class="staffing-basis-time-range">
            <input
              type="time"
              class="staffing-basis-start staffing-basis-time-input"
              value="${escapeAttr(item.start_time ?? "09:00")}"
              aria-label="勤務開始 ${index + 1}"
            >
            <span class="staffing-basis-time-sep" aria-hidden="true">〜</span>
            <input
              type="time"
              class="staffing-basis-end staffing-basis-time-input"
              value="${escapeAttr(item.end_time ?? "18:00")}"
              aria-label="勤務終了 ${index + 1}"
            >
          </div>
          <div class="staffing-basis-hours-preview" aria-live="polite">${escapeAttr(formatWorkHoursPreview(item.start_time ?? "09:00", item.end_time ?? "18:00"))}</div>
        </td>
        <td class="col-actions">
          <button type="button" class="btn btn-sm btn-danger" data-remove-staffing-basis>削除</button>
        </td>
      </tr>`
    )
    .join("");
  syncAllHoursPreviews();
  refreshStaffingBasisSymbolPreviews();
  refreshTimeSlotCoverageHints();
}

function refreshStaffingBasisSymbolPreviews() {
  if (!staffingBasisTbody) return;
  const symbols = getShiftSymbolMap();
  staffingBasisTbody.querySelectorAll(".staffing-basis-table-row").forEach((row) => {
    const key = row.querySelector(".staffing-basis-key")?.value.trim() ?? "";
    const preview = row.querySelector(".staffing-basis-symbol-preview");
    if (!preview) return;
    preview.dataset.symbolKey = key;
    preview.textContent = key && symbols[key] ? symbols[key] : "—";
  });
}

function refreshTimeSlotCoverageHints() {
  if (!timeSlotStaffingTbody) return;
  const workTypes = collectRegisteredWorkTypes();
  timeSlotStaffingTbody.querySelectorAll(".time-slot-table-row").forEach((row) => {
    const hint = row.querySelector(".time-slot-covered-types");
    if (!hint) return;
    const start = row.querySelector(".time-slot-start")?.value.trim() ?? "";
    const end = row.querySelector(".time-slot-end")?.value.trim() ?? "";
    const labels = workTypesCoveringSlot(start, end, workTypes);
    hint.textContent = labels.length ? labels.join("、") : "該当区分なし";
    hint.classList.toggle("is-empty", labels.length === 0);
  });
}

function syncWorkTypeSymbolBadges() {
  if (!form) return;
  form.querySelectorAll(".work-type-row[data-work-type-key]").forEach((row) => {
    const key = row.dataset.workTypeKey ?? "";
    const input = row.querySelector(".work-type-symbol-input");
    const badge = row.querySelector(".work-type-symbol-badge");
    if (!input || !badge) return;
    badge.textContent = input.value.trim() || "—";
  });
}

function renderWorkTypeMinStaffRows(workTypes = [], minStaffByFloor = {}) {
  const head = document.getElementById("floor-min-staff-head");
  if (!workTypeMinStaffTbody) return;
  const rows = workTypes.filter((item) => item.key && item.label);
  workTypeMinStaffEmpty?.classList.toggle("hidden", rows.length > 0);
  if (!rows.length) {
    workTypeMinStaffTbody.innerHTML = "";
    if (head) {
      head.innerHTML = "<tr><th>フロア</th></tr>";
    }
    return;
  }

  if (head) {
    head.innerHTML = `
      <tr>
        <th class="col-floor">フロア</th>
        ${rows
          .map(
            (item) => `
          <th class="col-min-staff" title="${escapeAttr(formatWorkHoursPreview(item.start_time, item.end_time))}">
            <span class="floor-min-staff-work-label">${escapeAttr(item.label)}</span>
            <span class="floor-min-staff-work-hours">${escapeAttr(formatWorkHoursPreview(item.start_time, item.end_time))}</span>
          </th>`
          )
          .join("")}
      </tr>`;
  }

  workTypeMinStaffTbody.innerHTML = FLOOR_LABELS.map((floor) => {
    const floorValues = minStaffByFloor[floor] ?? {};
    return `
      <tr class="floor-min-staff-row" data-floor="${escapeAttr(floor)}">
        <td class="col-floor">${escapeHtmlFloorBadge(floor)}</td>
        ${rows
          .map(
            (item) => `
          <td class="staffing-basis-min-staff-cell">
            <input
              type="number"
              class="floor-min-staff input-number"
              data-floor="${escapeAttr(floor)}"
              data-key="${escapeAttr(item.key)}"
              min="0"
              max="99"
              value="${escapeAttr(String(floorValues[item.key] ?? defaultMinStaffForKey(item.key)))}"
              aria-label="${escapeAttr(floor)} ${escapeAttr(item.label)}の必要人数"
            >
          </td>`
          )
          .join("")}
      </tr>`;
  }).join("");
}

function escapeHtmlFloorBadge(floor) {
  const slug = String(floor).toLowerCase();
  const klass = ["1f", "2f", "3f", "4f"].includes(slug) ? `floor-badge--${slug}` : "floor-badge--default";
  return `<span class="floor-badge ${klass}">${escapeAttr(floor)}</span>`;
}

function syncWorkTypeMinStaffFromBasis() {
  const workTypes = collectStaffingBasisOptions().filter((item) => item.key && item.label);
  const byFloor = collectMinStaffByFloor();
  renderWorkTypeMinStaffRows(workTypes, byFloor);
  renderFloorNightMinStaffRows(byFloor);
}

function collectMinStaffByFloor() {
  const result = {};
  if (workTypeMinStaffTbody) {
    for (const input of workTypeMinStaffTbody.querySelectorAll(".floor-min-staff")) {
      if (!(input instanceof HTMLInputElement)) continue;
      const floor = input.dataset.floor?.trim() ?? "";
      const key = input.dataset.key?.trim() ?? "";
      if (!floor || !key) continue;
      const count = Number.parseInt(input.value, 10);
      result[floor] ??= {};
      result[floor][key] = Number.isFinite(count) ? Math.max(0, Math.min(99, count)) : 0;
    }
  }
  // 時間帯モードの夜勤別枠を優先して上書き
  if (floorNightMinStaffTbody) {
    for (const input of floorNightMinStaffTbody.querySelectorAll(".floor-night-min-staff")) {
      if (!(input instanceof HTMLInputElement)) continue;
      const floor = input.dataset.floor?.trim() ?? "";
      if (!floor) continue;
      const count = Number.parseInt(input.value, 10);
      result[floor] ??= {};
      result[floor].night = Number.isFinite(count) ? Math.max(0, Math.min(99, count)) : 0;
    }
  }
  return result;
}

function renderFloorNightMinStaffRows(minStaffByFloor = {}) {
  if (!floorNightMinStaffTbody) return;
  floorNightMinStaffTbody.innerHTML = FLOOR_LABELS.map((floor) => {
    const floorValues = minStaffByFloor[floor] ?? {};
    const value = floorValues.night ?? defaultMinStaffForKey("night");
    return `
      <tr class="floor-night-min-staff-row" data-floor="${escapeAttr(floor)}">
        <td class="col-floor">${escapeHtmlFloorBadge(floor)}</td>
        <td class="staffing-basis-min-staff-cell">
          <input
            type="number"
            class="floor-night-min-staff input-number"
            data-floor="${escapeAttr(floor)}"
            data-key="night"
            min="0"
            max="99"
            value="${escapeAttr(String(value))}"
            aria-label="${escapeAttr(floor)} の夜勤必要人数"
          >
        </td>
      </tr>`;
  }).join("");
}

function defaultNightLeaderGroupRow() {
  return {
    label: "",
    floors: FLOOR_LABELS.slice(0, Math.min(2, FLOOR_LABELS.length)),
    min_leaders: 1,
  };
}

function syncNightLeaderGroupsPanelVisibility() {
  if (!nightLeaderGroupsPanel) return;
  const enabled = Boolean(requireLeaderOnNightInput?.checked);
  nightLeaderGroupsPanel.classList.toggle("is-collapsed", !enabled);
  nightLeaderGroupsPanel.setAttribute("aria-hidden", enabled ? "false" : "true");
}

function renderNightLeaderGroupRows(groups = []) {
  if (!nightLeaderGroupsTbody) return;
  const rows = Array.isArray(groups) ? groups : [];
  nightLeaderGroupsTbody.innerHTML = rows
    .map((item, index) => {
      const selected = new Set(item.floors ?? []);
      return `
      <tr class="night-leader-group-row" data-index="${index}">
        <td>
          <input
            type="text"
            class="input-text night-leader-group-label"
            maxlength="20"
            placeholder="例: 1・2階"
            value="${escapeAttr(item.label ?? "")}"
            aria-label="グループ名称 ${index + 1}"
          >
        </td>
        <td class="night-leader-floors-cell">
          <div class="night-leader-floor-checks" role="group" aria-label="対象フロア ${index + 1}">
            ${FLOOR_LABELS.map(
              (floor) => `
              <label class="check-row settings-check night-leader-floor-check">
                <input
                  type="checkbox"
                  class="night-leader-floor"
                  value="${escapeAttr(floor)}"
                  ${selected.has(floor) ? "checked" : ""}
                >
                <span>${escapeAttr(floor)}</span>
              </label>`
            ).join("")}
          </div>
        </td>
        <td class="staffing-basis-min-staff-cell">
          <input
            type="number"
            class="night-leader-min-leaders input-number"
            min="1"
            max="99"
            value="${escapeAttr(String(item.min_leaders ?? 1))}"
            aria-label="リーダー必要人数 ${index + 1}"
          >
        </td>
        <td class="col-actions">
          <button type="button" class="btn btn-sm btn-danger" data-remove-night-leader-group>削除</button>
        </td>
      </tr>`;
    })
    .join("");
}

function collectNightLeaderGroups() {
  if (!nightLeaderGroupsTbody) return [];
  return [...nightLeaderGroupsTbody.querySelectorAll(".night-leader-group-row")]
    .map((row) => ({
      label: row.querySelector(".night-leader-group-label")?.value.trim() ?? "",
      floors: [...row.querySelectorAll(".night-leader-floor:checked")].map((input) => input.value),
      min_leaders: Number.parseInt(row.querySelector(".night-leader-min-leaders")?.value ?? "1", 10) || 1,
    }))
    .filter((item) => item.floors.length > 0);
}

function resolveMinStaffByFloor(data) {
  const byFloor = data.min_staff_by_floor;
  if (byFloor && typeof byFloor === "object" && Object.keys(byFloor).length > 0) {
    return byFloor;
  }
  const legacy = data.min_staff_by_work_type;
  if (legacy && typeof legacy === "object" && Object.keys(legacy).length > 0) {
    return Object.fromEntries(FLOOR_LABELS.map((floor) => [floor, { ...legacy }]));
  }
  return {};
}

function collectMinStaffByWorkType() {
  const byFloor = collectMinStaffByFloor();
  const primaryFloor = FLOOR_LABELS[0];
  if (primaryFloor && byFloor[primaryFloor]) {
    return byFloor[primaryFloor];
  }
  if (!workTypeMinStaffTbody) return {};
  const result = {};
  for (const input of workTypeMinStaffTbody.querySelectorAll(".work-type-min-staff")) {
    if (!(input instanceof HTMLInputElement)) continue;
    const key = input.dataset.key?.trim() ?? "";
    if (!key) continue;
    const count = Number.parseInt(input.value, 10);
    result[key] = Number.isFinite(count) ? Math.max(0, Math.min(99, count)) : 0;
  }
  return result;
}

function renderTimeSlotRows(rules = []) {
  if (!timeSlotStaffingTbody) return;
  // 旧・夜勤帯（日跨ぎ）は別枠へ移行済み想定。画面には日中帯のみ出す。
  const daytime = (rules || []).filter(
    (item) => !isOvernightTimeRange(item.start_time ?? "", item.end_time ?? "")
  );
  const rows = daytime.length ? daytime : [defaultTimeSlotRow()];
  timeSlotStaffingTbody.innerHTML = rows
    .map(
      (item, index) => `
      <tr class="time-slot-table-row" data-index="${index}">
        <td class="col-floor">
          <select class="time-slot-floor input-select" aria-label="フロア ${index + 1}">
            <option value=""${!(item.floor ?? "").trim() ? " selected" : ""}>施設全体</option>
            ${FLOOR_LABELS.map(
              (floor) =>
                `<option value="${escapeAttr(floor)}"${floor === (item.floor ?? "").trim() ? " selected" : ""}>${escapeAttr(floor)}</option>`
            ).join("")}
          </select>
        </td>
        <td>
          <input
            type="text"
            class="input-text time-slot-label"
            maxlength="20"
            placeholder="例: 日勤帯"
            value="${escapeAttr(item.label ?? "")}"
            aria-label="時間帯名称 ${index + 1}"
          >
        </td>
        <td class="staffing-basis-time-cell">
          <div class="staffing-basis-time-range">
            <input
              type="time"
              class="time-slot-start staffing-basis-time-input"
              value="${escapeAttr(item.start_time ?? "09:00")}"
              aria-label="時間帯開始 ${index + 1}"
            >
            <span class="staffing-basis-time-sep" aria-hidden="true">〜</span>
            <input
              type="time"
              class="time-slot-end staffing-basis-time-input"
              value="${escapeAttr(item.end_time ?? "18:00")}"
              aria-label="時間帯終了 ${index + 1}"
            >
          </div>
          <div class="staffing-basis-hours-preview" aria-live="polite">${escapeAttr(formatWorkHoursPreview(item.start_time ?? "09:00", item.end_time ?? "18:00"))}</div>
        </td>
        <td class="col-covered-types">
          <span class="time-slot-covered-types" aria-live="polite">—</span>
        </td>
        <td class="staffing-basis-min-staff-cell">
          <input
            type="number"
            class="time-slot-min-staff input-number"
            min="0"
            max="99"
            value="${escapeAttr(String(item.min_staff ?? 1))}"
            aria-label="必要人数 ${index + 1}"
          >
        </td>
        <td class="col-actions">
          <button type="button" class="btn btn-sm btn-danger" data-remove-time-slot>削除</button>
        </td>
      </tr>`
    )
    .join("");
  timeSlotStaffingTbody.querySelectorAll(".time-slot-table-row").forEach(updateTimeSlotPreview);
  refreshTimeSlotCoverageHints();
}

function updateTimeSlotPreview(row) {
  const preview = row.querySelector(".staffing-basis-hours-preview");
  if (!preview) return;
  const start = row.querySelector(".time-slot-start")?.value ?? "";
  const end = row.querySelector(".time-slot-end")?.value ?? "";
  preview.textContent = formatWorkHoursPreview(start, end);
}

function collectTimeSlotStaffingRules() {
  if (!timeSlotStaffingTbody) return [];
  return [...timeSlotStaffingTbody.querySelectorAll(".time-slot-table-row")]
    .map((row) => ({
      floor: row.querySelector(".time-slot-floor")?.value.trim() ?? "",
      label: row.querySelector(".time-slot-label")?.value.trim() ?? "",
      start_time: row.querySelector(".time-slot-start")?.value.trim() ?? "",
      end_time: row.querySelector(".time-slot-end")?.value.trim() ?? "",
      min_staff: Number.parseInt(row.querySelector(".time-slot-min-staff")?.value ?? "0", 10) || 0,
    }))
    .filter((item) => item.start_time || item.end_time || item.label)
    .filter((item) => !isOvernightTimeRange(item.start_time, item.end_time));
}

function getStaffingRequirementMode() {
  const selected = form?.querySelector('input[name="staffing_requirement_mode"]:checked');
  return selected?.value === "time_slot" ? "time_slot" : "work_type";
}

function setStaffingRequirementMode(mode) {
  const value = mode === "time_slot" ? "time_slot" : "work_type";
  form?.querySelectorAll('input[name="staffing_requirement_mode"]').forEach((input) => {
    if (input instanceof HTMLInputElement) {
      input.checked = input.value === value;
    }
  });
}

function syncStaffingRequirementMode() {
  const mode = getStaffingRequirementMode();
  for (const panel of document.querySelectorAll(".requirement-panel")) {
    const panelMode = panel.dataset.requirementMode;
    const isActive = panelMode === mode;
    panel.classList.toggle("is-active", isActive);
    panel.classList.toggle("is-collapsed", !isActive);
    panel.setAttribute("aria-hidden", isActive ? "false" : "true");
  }
  document.querySelectorAll(".staffing-requirement-tab").forEach((tab) => {
    const input = tab.querySelector('input[name="staffing_requirement_mode"]');
    if (!(input instanceof HTMLInputElement)) return;
    tab.classList.toggle("is-selected", input.checked);
    tab.setAttribute("aria-selected", input.checked ? "true" : "false");
  });
}

function escapeAttr(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;");
}

function collectStaffingBasisOptions() {
  if (!staffingBasisTbody) return [];
  return [...staffingBasisTbody.querySelectorAll(".staffing-basis-table-row")]
    .map((row) => ({
      key: row.querySelector(".staffing-basis-key")?.value.trim() ?? "",
      label: row.querySelector(".staffing-basis-label")?.value.trim() ?? "",
      start_time: row.querySelector(".staffing-basis-start")?.value.trim() ?? "",
      end_time: row.querySelector(".staffing-basis-end")?.value.trim() ?? "",
    }))
    .filter((item) => item.key || item.label);
}

function applyWorkTypeTemplate() {
  const templateId = workTypeTemplateSelect?.value ?? "";
  if (!templateId) {
    showAlert("テンプレートを選択してください。", "error");
    return;
  }
  const template = WORK_TYPE_TEMPLATES.find((item) => item.id === templateId);
  if (!template?.options?.length) {
    showAlert("テンプレートの内容を読み込めませんでした。", "error");
    return;
  }
  const current = collectStaffingBasisOptions().filter((item) => item.key || item.label);
  if (current.length && !window.confirm("現在の勤務区分一覧をテンプレートで置き換えます。よろしいですか？")) {
    return;
  }
  renderStaffingBasisRows(template.options.map((item) => ({ ...item })));
  syncWorkTypeMinStaffFromBasis();
  showAlert(`「${template.label}」を反映しました。必要人数の勤務区分一覧も更新しました。適用ボタンで確定してください。`, "info");
}

function syncWorkTypeSymbolFields() {
  if (!form) return;
  form.querySelectorAll(".work-type-row[data-work-type-key]").forEach((row) => {
    const visibleInput = row.querySelector(".work-type-visible-input");
    const symbolInput = row.querySelector(".work-type-symbol-input");
    if (!visibleInput || !symbolInput) return;
    const key = row.dataset.workTypeKey ?? "";
    const enabled = FIXED_VISIBLE_WORK_TYPES.has(key) || visibleInput.checked;
    symbolInput.disabled = !enabled;
    symbolInput.required = enabled;
  });
}

function applyFixedVisibleWorkTypes() {
  if (!form) return;
  for (const element of form.elements) {
    if (!(element instanceof HTMLInputElement)) continue;
    if (!element.name.startsWith(VISIBLE_WORK_TYPE_PREFIX)) continue;
    const key = element.name.slice(VISIBLE_WORK_TYPE_PREFIX.length);
    if (!FIXED_VISIBLE_WORK_TYPES.has(key)) continue;
    element.checked = true;
    element.disabled = true;
    element.closest(".work-type-row")?.classList.add("work-type-row-fixed");
  }
}

function populateVisibleWorkTypes(visibility = {}) {
  if (!form) return;
  for (const element of form.elements) {
    if (!(element instanceof HTMLInputElement)) continue;
    if (!element.name.startsWith(VISIBLE_WORK_TYPE_PREFIX)) continue;
    const key = element.name.slice(VISIBLE_WORK_TYPE_PREFIX.length);
    if (FIXED_VISIBLE_WORK_TYPES.has(key)) {
      element.checked = true;
      continue;
    }
    element.checked = visibility[key] !== false;
  }
  applyFixedVisibleWorkTypes();
  syncWorkTypeSymbolFields();
}

function populateShiftSymbols(symbols = {}) {
  if (!form) return;
  for (const element of form.elements) {
    if (!(element instanceof HTMLInputElement)) continue;
    if (!element.name.startsWith(SHIFT_SYMBOL_PREFIX)) continue;
    const key = element.name.slice(SHIFT_SYMBOL_PREFIX.length);
    element.value = symbols[key] ?? "";
  }
}

function populateForm(data) {
  if (!form) return;
  for (const [key, value] of Object.entries(data)) {
    if (key === "shift_symbols") {
      populateShiftSymbols(value);
      continue;
    }
    if (key === "visible_work_types") {
      populateVisibleWorkTypes(value);
      continue;
    }
    if (key === "staffing_basis_options") {
      renderStaffingBasisRows(Array.isArray(value) ? value : []);
      const byFloor = resolveMinStaffByFloor(data);
      renderWorkTypeMinStaffRows(
        Array.isArray(value) ? value.filter((item) => item.key && item.label) : [],
        byFloor
      );
      renderFloorNightMinStaffRows(byFloor);
      continue;
    }
    if (key === "min_staff_by_floor") {
      const byFloor = value && typeof value === "object" ? value : {};
      renderWorkTypeMinStaffRows(collectRegisteredWorkTypes(), byFloor);
      renderFloorNightMinStaffRows(byFloor);
      continue;
    }
    if (key === "min_staff_by_work_type") {
      continue;
    }
    if (key === "time_slot_staffing_rules") {
      renderTimeSlotRows(Array.isArray(value) ? value : []);
      continue;
    }
    if (key === "night_leader_groups") {
      renderNightLeaderGroupRows(Array.isArray(value) ? value : DEFAULT_NIGHT_LEADER_GROUPS);
      continue;
    }
    if (key === "staffing_requirement_mode") {
      setStaffingRequirementMode(value);
      continue;
    }
    if (key === "off_days_per_period") {
      const field = form.elements.namedItem(key);
      if (field && "value" in field) {
        field.value = value == null ? "" : String(value);
      }
      continue;
    }
    const field = form.elements.namedItem(key);
    if (!field || field instanceof RadioNodeList) continue;
    if (field.type === "checkbox") {
      field.checked = Boolean(value);
    } else {
      field.value = value ?? "";
    }
  }
  syncWorkTypeSymbolFields();
  syncStaffingRequirementMode();
  syncNightLeaderGroupsPanelVisibility();
  if (nightLeaderGroupsTbody && !nightLeaderGroupsTbody.querySelector(".night-leader-group-row")) {
    renderNightLeaderGroupRows(DEFAULT_NIGHT_LEADER_GROUPS);
  }
  refreshStaffingBasisSymbolPreviews();
  refreshTimeSlotCoverageHints();
  syncWorkTypeSymbolBadges();
}

function collectVisibleWorkTypes() {
  const visibility = {};
  if (!form) return visibility;

  for (const element of form.elements) {
    if (!(element instanceof HTMLInputElement)) continue;
    if (!element.name.startsWith(VISIBLE_WORK_TYPE_PREFIX)) continue;
    const key = element.name.slice(VISIBLE_WORK_TYPE_PREFIX.length);
    visibility[key] = FIXED_VISIBLE_WORK_TYPES.has(key) ? true : element.checked;
  }
  return visibility;
}

function collectShiftSymbols() {
  const symbols = {};
  if (!form) return symbols;

  for (const element of form.elements) {
    if (!(element instanceof HTMLInputElement)) continue;
    if (!element.name.startsWith(SHIFT_SYMBOL_PREFIX)) continue;
    const key = element.name.slice(SHIFT_SYMBOL_PREFIX.length);
    symbols[key] = element.value.trim();
  }
  return symbols;
}

function collectFormData() {
  const data = {};
  if (!form) return data;

  for (const element of form.elements) {
    if (!(element instanceof HTMLInputElement || element instanceof HTMLSelectElement)) continue;
    if (!element.name || element.name.startsWith(SHIFT_SYMBOL_PREFIX)) continue;
    if (element.name.startsWith(VISIBLE_WORK_TYPE_PREFIX)) continue;
    if (element.id === "work-type-template-select") continue;

    if (element.type === "radio") {
      if (element.checked) {
        data[element.name] = element.value;
      }
      continue;
    }

    if (element.type === "checkbox") {
      data[element.name] = element.checked;
    } else if (element.name === "off_days_per_period") {
      const raw = element.value.trim();
      data[element.name] = raw === "" ? null : Number.parseInt(raw, 10);
    } else if (INT_FIELDS.has(element.name)) {
      data[element.name] = Number.parseInt(element.value, 10);
    } else {
      data[element.name] = element.value;
    }
  }

  data.shift_symbols = collectShiftSymbols();
  data.visible_work_types = collectVisibleWorkTypes();
  data.staffing_basis_options = collectStaffingBasisOptions();
  data.min_staff_by_floor = collectMinStaffByFloor();
  data.min_staff_by_work_type = collectMinStaffByWorkType();
  data.time_slot_staffing_rules = collectTimeSlotStaffingRules();
  data.night_leader_groups = collectNightLeaderGroups();
  if (!data.staffing_requirement_mode) {
    data.staffing_requirement_mode = getStaffingRequirementMode();
  }
  return data;
}

async function loadSettings() {
  hideAlert();
  const response = await fetch("/api/settings");
  if (!response.ok) {
    showAlert("設定の読み込みに失敗しました。", "error");
    return;
  }
  populateForm(await response.json());
}

async function saveSettings(event) {
  event.preventDefault();
  hideAlert();

  const response = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectFormData()),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = error.detail;
    const message = typeof detail === "string" ? detail : "設定の保存に失敗しました。入力内容を確認してください。";
    showAlert(message, "error");
    return;
  }

  populateForm(await response.json());
  showAlert("設定を適用しました。カレンダー・職員管理画面を再読み込みすると反映されます。");
}

async function resetDefaults() {
  if (!window.confirm("すべての設定を初期値に戻します。よろしいですか？")) return;
  hideAlert();

  const response = await fetch("/api/settings/defaults");
  if (!response.ok) {
    showAlert("デフォルト設定の取得に失敗しました。", "error");
    return;
  }
  populateForm(await response.json());
  showAlert("デフォルト値をフォームに反映しました。適用ボタンで確定してください。", "info");
}

form?.addEventListener("submit", saveSettings);
form?.addEventListener("change", (event) => {
  if (event.target instanceof HTMLInputElement && event.target.classList.contains("work-type-visible-input")) {
    syncWorkTypeSymbolFields();
  }
  if (event.target instanceof HTMLInputElement && event.target.name === "staffing_requirement_mode") {
    syncStaffingRequirementMode();
  }
  if (event.target instanceof HTMLInputElement && event.target.name === "require_leader_on_night") {
    syncNightLeaderGroupsPanelVisibility();
  }
});
form?.addEventListener("input", (event) => {
  if (!(event.target instanceof HTMLInputElement)) return;
  if (event.target.name.startsWith(SHIFT_SYMBOL_PREFIX)) {
    syncWorkTypeSymbolBadges();
    refreshStaffingBasisSymbolPreviews();
  }
});
resetButton?.addEventListener("click", resetDefaults);
applyWorkTypeTemplateButton?.addEventListener("click", applyWorkTypeTemplate);
syncWorkTypeMinStaffButton?.addEventListener("click", () => {
  syncWorkTypeMinStaffFromBasis();
  showAlert("勤務区分ごとの必要人数一覧を更新しました。", "info");
});
addTimeSlotButton?.addEventListener("click", () => {
  renderTimeSlotRows([...collectTimeSlotStaffingRules(), defaultTimeSlotRow()]);
});
addNightLeaderGroupButton?.addEventListener("click", () => {
  renderNightLeaderGroupRows([...collectNightLeaderGroups(), defaultNightLeaderGroupRow()]);
});
nightLeaderGroupsTbody?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-night-leader-group]");
  if (!button || !nightLeaderGroupsTbody) return;
  const row = button.closest(".night-leader-group-row");
  if (!row) return;
  const index = [...nightLeaderGroupsTbody.querySelectorAll(".night-leader-group-row")].indexOf(row);
  const rows = collectNightLeaderGroups();
  if (index >= 0) rows.splice(index, 1);
  renderNightLeaderGroupRows(rows);
});
addStaffingBasisButton?.addEventListener("click", () => {
  renderStaffingBasisRows([...collectStaffingBasisOptions(), defaultWorkTypeRow()]);
});
staffingBasisTbody?.addEventListener("input", (event) => {
  if (!(event.target instanceof HTMLInputElement)) return;
  const row = event.target.closest(".staffing-basis-table-row");
  if (event.target.classList.contains("staffing-basis-start") || event.target.classList.contains("staffing-basis-end")) {
    if (row) updateHoursPreview(row);
    refreshTimeSlotCoverageHints();
    return;
  }
  if (event.target.classList.contains("staffing-basis-key") || event.target.classList.contains("staffing-basis-label")) {
    refreshStaffingBasisSymbolPreviews();
    refreshTimeSlotCoverageHints();
  }
});
timeSlotStaffingTbody?.addEventListener("input", (event) => {
  if (!(event.target instanceof HTMLInputElement)) return;
  if (!event.target.classList.contains("time-slot-start") && !event.target.classList.contains("time-slot-end")) {
    return;
  }
  const row = event.target.closest(".time-slot-table-row");
  if (row) updateTimeSlotPreview(row);
  refreshTimeSlotCoverageHints();
});
timeSlotStaffingTbody?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-time-slot]");
  if (!button) return;
  const row = button.closest(".time-slot-table-row");
  if (!row || !timeSlotStaffingTbody) return;
  const rows = collectTimeSlotStaffingRules();
  const index = [...timeSlotStaffingTbody.querySelectorAll(".time-slot-table-row")].indexOf(row);
  if (index >= 0) {
    rows.splice(index, 1);
  }
  renderTimeSlotRows(rows.length ? rows : [defaultTimeSlotRow()]);
});
staffingBasisTbody?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-staffing-basis]");
  if (!button) return;
  const row = button.closest(".staffing-basis-table-row");
  if (!row) return;
  const rows = collectStaffingBasisOptions();
  const index = [...staffingBasisTbody.querySelectorAll(".staffing-basis-table-row")].indexOf(row);
  if (index >= 0) {
    rows.splice(index, 1);
  }
  renderStaffingBasisRows(rows.length ? rows : [defaultWorkTypeRow()]);
  syncWorkTypeMinStaffFromBasis();
});
loadSettings();
