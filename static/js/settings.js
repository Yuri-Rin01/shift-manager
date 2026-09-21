let loadedSettings = {};
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
const workTypeMinStaffPanel = document.getElementById("panel-work-type-min-staff");
const timeSlotStaffingPanel = document.getElementById("panel-time-slot-staffing");
const workTypeTemplateSelect = document.getElementById("work-type-template-select");
const applyWorkTypeTemplateButton = document.getElementById("btn-apply-work-type-template");
const WORK_TYPE_TEMPLATES = window.WORK_TYPE_TEMPLATES ?? [];
let FLOOR_LABELS = window.FLOOR_LABELS ?? ["1F", "2F", "3F", "4F"];
const floorsEditor = document.getElementById("floors-editor");
const addFloorButton = document.getElementById("btn-add-floor");
const jobFilterVisibilityInputs = [
  ...document.querySelectorAll(".job-filter-visibility-input"),
];
const FLICK_DIRECTION_PREFIX = "cell_flick_direction__";
const FLICK_DIRECTION_COUNT = 8;

function populateJobFilterVisibility(visibility = {}) {
  const values = visibility && typeof visibility === "object" ? visibility : {};
  jobFilterVisibilityInputs.forEach((input) => {
    input.checked = values[input.dataset.jobLabel] !== false;
  });
}

function collectJobFilterVisibility() {
  return Object.fromEntries(
    jobFilterVisibilityInputs.map((input) => [input.dataset.jobLabel, input.checked])
  );
}

function allocateFloorId(existingIds) {
  const used = new Set(existingIds);
  for (let index = 1; index < 1000; index += 1) {
    const candidate = `f${index}`;
    if (!used.has(candidate)) return candidate;
  }
  return `f_${Date.now().toString(36)}`;
}

function collectFloors() {
  if (!floorsEditor) {
    return (window.FLOOR_LABELS ?? FLOOR_LABELS).map((label, index) => ({
      id: ["1f", "2f", "3f", "4f"][index] || allocateFloorId([]),
      label,
    }));
  }
  return [...floorsEditor.querySelectorAll(".floor-editor-row")]
    .map((row) => ({
      id: row.querySelector(".floor-id")?.value.trim() || "",
      label: row.querySelector(".floor-label")?.value.trim() || "",
    }))
    .filter((item) => item.id && item.label);
}

function syncFloorLabelsFromEditor() {
  FLOOR_LABELS = collectFloors().map((item) => item.label);
  window.FLOOR_LABELS = FLOOR_LABELS;
  renderWorkTypeMinStaffRows(collectRegisteredWorkTypes(), collectMinStaffByFloor());
}

function renderFloorsEditor(floors = []) {
  if (!floorsEditor) return;
  const rows = Array.isArray(floors) && floors.length ? floors : [
    { id: "1f", label: "1F" },
    { id: "2f", label: "2F" },
    { id: "3f", label: "3F" },
    { id: "4f", label: "4F" },
  ];
  floorsEditor.innerHTML = rows
    .map(
      (item, index) => `<div class="floor-editor-row" data-floor-id="${escapeAttr(item.id)}">
      <input type="hidden" class="floor-id" value="${escapeAttr(item.id)}">
      <label class="form-field"><span class="form-label">表示名</span>
        <input type="text" class="floor-label input-text" maxlength="20" required value="${escapeAttr(item.label || "")}" aria-label="フロア${index + 1}の表示名">
      </label>
      <span class="field-hint floor-id-hint">ID: ${escapeAttr(item.id)}</span>
      <button type="button" class="btn btn-sm" data-remove-floor>削除</button>
    </div>`
    )
    .join("");
  FLOOR_LABELS = rows.map((item) => item.label);
  window.FLOOR_LABELS = FLOOR_LABELS;
}

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
  return { key: `work_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`, label: "", base_key: "day", start_time: "09:00", end_time: "18:00" };
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
  return collectStaffingBasisOptions().filter((item) => item.key).map((item) => ({...item, label: item.label || "新しい勤務"}));
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

function workTypesCoveringSlot(startTime, endTime, workTypes) {
  if (!startTime || !endTime) return [];
  const matched = new Set();
  for (const segmentInfo of slotSegmentsForDisplay(startTime, endTime)) {
    for (const workType of workTypes) {
      if (workTypeCoversSlotSegment(workType, segmentInfo)) {
        matched.add(workType.label);
      }
    }
  }
  return [...matched];
}

const BASE_LABELS = {early: "早番", day: "日勤", late: "遅出", night: "夜勤"};
const FIXED_WORK_KEYS = new Set(Object.keys(BASE_LABELS).flatMap((key) => [key, `semi_${key}`]));

function renderStaffingBasisRows(options = [], settings = null) {
  if (!staffingBasisTbody) return;
  const symbols = settings?.shift_symbols ?? getShiftSymbolMap();
  const visibility = settings?.visible_work_types ?? collectVisibleWorkTypes();
  staffingBasisTbody.innerHTML = options.map((item, index) => {
    const key = item.key;
    const base = item.base_key ?? key.replace("semi_", "");
    return `<details class="staffing-basis-table-row work-editor-card" data-key="${escapeAttr(key)}" ${item.label ? "" : "open"}><summary class="work-editor-summary"><span class="work-summary-symbol">${escapeAttr(symbols[key] ?? item.label?.slice(0,10) ?? "＋")}</span><span><strong class="work-summary-label">${escapeAttr(item.label || "新しい勤務")}</strong><span class="work-summary-hours">${escapeAttr(formatWorkHoursPreview(item.start_time, item.end_time))}</span></span><span>編集</span></summary>
      <div class="work-editor-card-head"><span>勤務 ${index + 1}</span>
        <button type="button" class="btn btn-sm" data-remove-staffing-basis aria-label="${escapeAttr(item.label || "この勤務")}を削除">削除</button></div>
      <input type="hidden" class="staffing-basis-key" value="${escapeAttr(key)}">
      <div class="work-editor-fields">
        <label class="form-field"><span class="form-label">勤務名</span><input class="input-text staffing-basis-label" maxlength="20" required placeholder="例：短時間日勤" value="${escapeAttr(item.label ?? "")}"></label>
        <label class="form-field"><span class="form-label">表示記号</span><input class="input-text staffing-basis-symbol" maxlength="10" required placeholder="例：短" value="${escapeAttr(symbols[key] ?? item.label?.slice(0,10) ?? "")}"></label>
        <label class="form-field"><span class="form-label">種類</span><select class="staffing-basis-base" ${FIXED_WORK_KEYS.has(key) ? "disabled" : ""}>${Object.entries(BASE_LABELS).map(([value,label]) => `<option value="${value}" ${base === value || (!BASE_LABELS[base] && value === "day") ? "selected" : ""}>${label}</option>`).join("")}</select></label>
        <label class="form-field"><span class="form-label">開始</span><input type="time" class="staffing-basis-start" required value="${escapeAttr(item.start_time ?? "09:00")}"></label>
        <label class="form-field"><span class="form-label">終了</span><input type="time" class="staffing-basis-end" required value="${escapeAttr(item.end_time ?? "18:00")}"></label>
        <label class="form-field"><span class="form-label">休憩（分）</span><input type="number" class="staffing-basis-break" min="0" max="720" step="1" placeholder="未設定" value="${item.break_minutes != null && item.break_minutes !== "" ? escapeAttr(String(item.break_minutes)) : ""}"><span class="field-hint">実働集計に必要。空欄のままでは確定値を出しません。</span></label>
      </div>
      <div class="work-editor-card-foot"><label class="check-row"><input type="checkbox" class="staffing-basis-visible" ${visibility[key] !== false ? "checked" : ""}> カレンダーに表示</label><span class="staffing-basis-hours-preview"></span></div>
    </details>`;
  }).join("");
  const registered = new Set(options.map((item) => item.key));
  form.querySelectorAll(".work-type-row[data-work-type-key]").forEach((row) => {
    row.hidden = registered.has(row.dataset.workTypeKey);
    row.querySelectorAll("input").forEach((input) => {
      if (row.hidden) input.required = false;
    });
  });
  form.querySelectorAll(".work-type-group").forEach((group) => {
    group.hidden = ![...group.querySelectorAll(".work-type-row[data-work-type-key]")].some((row) => !row.hidden);
  });
  syncWorkTypeSymbolFields();
  syncAllHoursPreviews();
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
  if (!workTypeMinStaffTbody) return;
  const picker = document.getElementById("settings-staffing-floor");
  const selected = picker?.value || FLOOR_LABELS[0];
  if (picker) picker.innerHTML = FLOOR_LABELS.map(floor => `<option ${floor === selected ? "selected" : ""}>${escapeAttr(floor)}</option>`).join("");
  const rows = workTypes.filter(item => item.key && item.label);
  workTypeMinStaffEmpty?.classList.toggle("hidden", rows.length > 0);
  workTypeMinStaffTbody.innerHTML = FLOOR_LABELS.map(floor => `<div class="floor-min-staff-row settings-floor-counts" data-floor="${escapeAttr(floor)}" ${floor !== selected ? "hidden" : ""}>
    ${rows.map(item => `<label class="form-field"><span class="form-label">${escapeAttr(item.label)}</span><span class="field-hint">${escapeAttr(formatWorkHoursPreview(item.start_time,item.end_time))}</span><input type="number" class="floor-min-staff input-number" data-floor="${escapeAttr(floor)}" data-key="${escapeAttr(item.key)}" min="0" max="99" required value="${minStaffByFloor[floor]?.[item.key] ?? defaultMinStaffForKey(item.key)}" aria-label="${escapeAttr(floor)} ${escapeAttr(item.label)}の必要人数"></label>`).join("")}
  </div>`).join("");
}
document.getElementById("settings-staffing-floor")?.addEventListener("change", event => {
  workTypeMinStaffTbody.querySelectorAll(".floor-min-staff-row").forEach(row => {row.hidden = row.dataset.floor !== event.target.value;});
});

function escapeHtmlFloorBadge(floor) {
  const slug = String(floor).toLowerCase();
  const klass = ["1f", "2f", "3f", "4f"].includes(slug) ? `floor-badge--${slug}` : "floor-badge--default";
  return `<span class="floor-badge ${klass}">${escapeAttr(floor)}</span>`;
}

function syncWorkTypeMinStaffFromBasis() {
  const workTypes = collectRegisteredWorkTypes();
  renderWorkTypeMinStaffRows(workTypes, collectMinStaffByFloor());
}

function collectMinStaffByFloor() {
  if (!workTypeMinStaffTbody) return {};
  const result = {};
  for (const input of workTypeMinStaffTbody.querySelectorAll(".floor-min-staff")) {
    if (!(input instanceof HTMLInputElement)) continue;
    const floor = input.dataset.floor?.trim() ?? "";
    const key = input.dataset.key?.trim() ?? "";
    if (!floor || !key) continue;
    const count = Number.parseInt(input.value, 10);
    result[floor] ??= {};
    result[floor][key] = Number.isFinite(count) ? Math.max(0, Math.min(99, count)) : 0;
  }
  return result;
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
  const rows = rules.length ? rules : [defaultTimeSlotRow()];
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
    .filter((item) => item.start_time || item.end_time || item.label);
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
    .map((row) => {
      const breakRaw = row.querySelector(".staffing-basis-break")?.value.trim() ?? "";
      const breakMinutes = breakRaw === "" ? null : Number(breakRaw);
      return {
        key: row.querySelector(".staffing-basis-key")?.value.trim() ?? "",
        label: row.querySelector(".staffing-basis-label")?.value.trim() ?? "",
        start_time: row.querySelector(".staffing-basis-start")?.value.trim() ?? "",
        end_time: row.querySelector(".staffing-basis-end")?.value.trim() ?? "",
        ...(Number.isFinite(breakMinutes) ? { break_minutes: breakMinutes } : {}),
        ...(!FIXED_WORK_KEYS.has(row.dataset.key) ? {base_key: row.querySelector(".staffing-basis-base")?.value ?? "day"} : {}),
      };
    })
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
  markDirty();
  syncWorkTypeMinStaffFromBasis();
  rebuildFlickDirectionOptions(collectFlickDirections());
  showAlert(`「${template.label}」を反映しました。必要人数の勤務区分一覧も更新しました。適用ボタンで確定してください。`, "info");
}

function syncWorkTypeSymbolFields() {
  if (!form) return;
  form.querySelectorAll(".work-type-row[data-work-type-key]").forEach((row) => {
    const visibleInput = row.querySelector(".work-type-visible-input");
    const symbolInput = row.querySelector(".work-type-symbol-input");
    if (!visibleInput || !symbolInput) return;
    const key = row.dataset.workTypeKey ?? "";
    const enabled = !row.hidden && (FIXED_VISIBLE_WORK_TYPES.has(key) || visibleInput.checked);
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
  loadedSettings = structuredClone(data);
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
    if (key === "floors") {
      renderFloorsEditor(Array.isArray(value) ? value : []);
      continue;
    }
    if (key === "job_filter_visibility") {
      populateJobFilterVisibility(value);
      continue;
    }
    if (key === "staffing_basis_options") {
      renderStaffingBasisRows(Array.isArray(value) ? value : [], data);
      renderWorkTypeMinStaffRows(
        Array.isArray(value) ? value.filter((item) => item.key && item.label) : [],
        resolveMinStaffByFloor(data)
      );
      continue;
    }
    if (key === "min_staff_by_floor") {
      renderWorkTypeMinStaffRows(
        collectRegisteredWorkTypes(),
        value && typeof value === "object" ? value : {}
      );
      continue;
    }
    if (key === "min_staff_by_work_type") {
      continue;
    }
    if (key === "time_slot_staffing_rules") {
      renderTimeSlotRows(Array.isArray(value) ? value : []);
      continue;
    }
    if (key === "cell_flick_directions") {
      continue;
    }
    if (key === "staffing_requirement_mode") {
      setStaffingRequirementMode(value);
      continue;
    }
    if (key === "off_days_per_period" || key === "default_weekly_hour_limit" || key === "default_monthly_hour_limit") {
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
  refreshStaffingBasisSymbolPreviews();
  refreshTimeSlotCoverageHints();
  syncWorkTypeSymbolBadges();
  populateFlickDirections(data.cell_flick_directions);
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
  staffingBasisTbody?.querySelectorAll(".staffing-basis-table-row").forEach((row) => {
    visibility[row.dataset.key] = row.querySelector(".staffing-basis-visible").checked;
  });
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
  staffingBasisTbody?.querySelectorAll(".staffing-basis-table-row").forEach((row) => {
    symbols[row.dataset.key] = row.querySelector(".staffing-basis-symbol").value.trim();
  });
  return symbols;
}

function getFlickSymbolChoices() {
  const symbols = collectShiftSymbols();
  const visibility = collectVisibleWorkTypes();
  const choices = [];
  const seen = new Set();

  function addChoice(key, label) {
    if (!key) return;
    if (!(FIXED_VISIBLE_WORK_TYPES.has(key) || visibility[key])) return;
    const symbol = (symbols[key] ?? "").trim();
    if (!symbol || seen.has(symbol)) return;
    seen.add(symbol);
    choices.push({ symbol, label: `${symbol}（${label}）` });
  }

  document.querySelectorAll(".work-type-row[data-work-type-key]").forEach((row) => {
    if (row.hidden) return;
    const key = row.dataset.workTypeKey ?? "";
    const label = row.querySelector(".work-type-name")?.textContent?.trim() || key;
    addChoice(key, label);
  });

  staffingBasisTbody?.querySelectorAll(".staffing-basis-table-row").forEach((row) => {
    const key = row.querySelector(".staffing-basis-key")?.value.trim() ?? row.dataset.key ?? "";
    const label = row.querySelector(".staffing-basis-label")?.value.trim() || key;
    addChoice(key, label);
  });

  return choices;
}

function rebuildFlickDirectionOptions(selected = []) {
  const choices = getFlickSymbolChoices();
  const values = Array.isArray(selected) ? selected : [];
  document.querySelectorAll(".flick-assign-select").forEach((select) => {
    if (!(select instanceof HTMLSelectElement)) return;
    const index = Number(select.dataset.flickIndex);
    const current = Number.isFinite(index) ? (values[index] ?? select.value ?? "") : "";
    select.innerHTML = '<option value="">（なし）</option>';
    choices.forEach((choice) => {
      const option = document.createElement("option");
      option.value = choice.symbol;
      option.textContent = choice.label;
      select.appendChild(option);
    });
    if (current && ![...select.options].some((opt) => opt.value === current)) {
      const orphan = document.createElement("option");
      orphan.value = current;
      orphan.textContent = `${current}（未表示）`;
      select.appendChild(orphan);
    }
    select.value = current || "";
  });
}

function populateFlickDirections(directions = []) {
  rebuildFlickDirectionOptions(Array.isArray(directions) ? directions : []);
}

function collectFlickDirections() {
  const values = Array.from({ length: FLICK_DIRECTION_COUNT }, () => "");
  document.querySelectorAll(".flick-assign-select").forEach((select) => {
    if (!(select instanceof HTMLSelectElement)) return;
    const index = Number(select.dataset.flickIndex);
    if (!Number.isFinite(index) || index < 0 || index >= FLICK_DIRECTION_COUNT) return;
    values[index] = select.value.trim();
  });
  return values.every((item) => !item) ? [] : values;
}

function autoFillFlickDirections() {
  const choices = getFlickSymbolChoices().slice(0, FLICK_DIRECTION_COUNT);
  const values = Array.from({ length: FLICK_DIRECTION_COUNT }, () => "");
  const order = [0, 2, 4, 6, 1, 3, 5, 7];
  choices.forEach((choice, i) => {
    const dir = order[i];
    if (dir != null) values[dir] = choice.symbol;
  });
  rebuildFlickDirectionOptions(values);
}

function clearFlickDirections() {
  rebuildFlickDirectionOptions([]);
}

function collectFormData() {
  const data = structuredClone(loadedSettings);
  if (!form) return data;

  for (const element of form.elements) {
    if (!(element instanceof HTMLInputElement || element instanceof HTMLSelectElement)) continue;
    if (!element.name || element.name.startsWith(SHIFT_SYMBOL_PREFIX)) continue;
    if (element.name.startsWith(VISIBLE_WORK_TYPE_PREFIX)) continue;
    if (element.name.startsWith(FLICK_DIRECTION_PREFIX)) continue;
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
    } else if (element.name === "default_weekly_hour_limit" || element.name === "default_monthly_hour_limit") {
      const raw = element.value.trim();
      data[element.name] = raw === "" ? null : Number.parseFloat(raw);
    } else if (INT_FIELDS.has(element.name)) {
      data[element.name] = Number.parseInt(element.value, 10);
    } else {
      data[element.name] = element.value;
    }
  }

  data.shift_symbols = collectShiftSymbols();
  data.visible_work_types = collectVisibleWorkTypes();
  data.cell_flick_directions = collectFlickDirections();
  data.staffing_basis_options = collectStaffingBasisOptions();
  data.floors = collectFloors();
  data.job_filter_visibility = collectJobFilterVisibility();
  data.min_staff_by_floor = collectMinStaffByFloor();
  data.min_staff_by_work_type = collectMinStaffByWorkType();
  data.time_slot_staffing_rules = collectTimeSlotStaffingRules();
  if (!data.staffing_requirement_mode) {
    data.staffing_requirement_mode = getStaffingRequirementMode();
  }
  return data;
}

let settingsReady = false;
let dirty = false;
const saveButton = document.getElementById("btn-save-settings");
const saveStatus = document.getElementById("settings-save-status");
function markDirty() {
  if (!settingsReady) return;
  dirty = true;
  saveStatus.textContent = "未保存の変更があります";
}
function markSaved() {
  dirty = false;
  saveStatus.textContent = "保存済み";
}
form?.addEventListener("input", markDirty);
form?.addEventListener("change", markDirty);
window.addEventListener("beforeunload", (event) => {
  if (!dirty) return;
  event.preventDefault();
  event.returnValue = "";
});

async function loadSettings() {
  saveButton.disabled = true;
  try {
  hideAlert();
  const response = await fetch("/api/settings");
  if (!response.ok) {
    saveStatus.textContent = "読み込み失敗";
    showAlert("設定の読み込みに失敗しました。ページを再読み込みしてください。", "error");
    return;
  }
  populateForm(await response.json());
  settingsReady = true;
  saveButton.disabled = false;
  markSaved();
  } catch { saveStatus.textContent = "読み込み失敗"; showAlert("設定を読み込めませんでした。ページを再読み込みしてください。", "error"); }
}

async function saveSettings(event) {
  event.preventDefault();
  if (!settingsReady || saveButton.disabled) return;
  if (!validateSettingsForm()) return;
  saveButton.disabled = true;
  saveStatus.textContent = "保存中…";
  try {
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
  markSaved();
  showAlert("設定を保存しました。カレンダー・職員管理画面を再読み込みすると反映されます。");
  } catch { showAlert("通信に失敗しました。変更は画面に残っています。もう一度保存してください。", "error"); }
  finally { saveButton.disabled = false; if (dirty) saveStatus.textContent = "未保存の変更があります"; }
}

async function resetDefaults() {
  if (!settingsReady) return;
  try {
  if (!window.confirm("すべての設定を初期値に戻します。よろしいですか？")) return;
  hideAlert();

  const response = await fetch("/api/settings/defaults");
  if (!response.ok) {
    showAlert("デフォルト設定の取得に失敗しました。", "error");
    return;
  }
  populateForm(await response.json());
  markDirty();
  showAlert("デフォルト値をフォームに反映しました。「変更を保存」で確定してください。", "info");
  } catch { showAlert("デフォルト設定を取得できませんでした。もう一度お試しください。", "error"); }
}

form?.addEventListener("submit", saveSettings);
form?.addEventListener("change", (event) => {
  if (event.target instanceof HTMLInputElement && event.target.classList.contains("work-type-visible-input")) {
    syncWorkTypeSymbolFields();
    rebuildFlickDirectionOptions(collectFlickDirections());
  }
  if (event.target instanceof HTMLInputElement && event.target.classList.contains("staffing-basis-visible")) {
    rebuildFlickDirectionOptions(collectFlickDirections());
  }
  if (event.target instanceof HTMLSelectElement && event.target.classList.contains("flick-assign-select")) {
    markDirty();
  }
  if (event.target instanceof HTMLInputElement && event.target.name === "staffing_requirement_mode") {
    syncStaffingRequirementMode();
  }
});
form?.addEventListener("input", (event) => {
  if (!(event.target instanceof HTMLInputElement)) return;
  const work = event.target.closest(".work-editor-card");
  if (work) {
    work.querySelector(".work-summary-label").textContent = work.querySelector(".staffing-basis-label").value || "新しい勤務";
    work.querySelector(".work-summary-symbol").textContent = work.querySelector(".staffing-basis-symbol").value || "＋";
    work.querySelector(".work-summary-hours").textContent = formatWorkHoursPreview(work.querySelector(".staffing-basis-start").value, work.querySelector(".staffing-basis-end").value);
  }
  if (event.target.name.startsWith(SHIFT_SYMBOL_PREFIX) || event.target.classList.contains("staffing-basis-symbol")) {
    syncWorkTypeSymbolBadges();
    refreshStaffingBasisSymbolPreviews();
    rebuildFlickDirectionOptions(collectFlickDirections());
  }
});
document.getElementById("btn-flick-auto-fill")?.addEventListener("click", () => {
  autoFillFlickDirections();
  markDirty();
});
document.getElementById("btn-flick-clear")?.addEventListener("click", () => {
  clearFlickDirections();
  markDirty();
});
resetButton?.addEventListener("click", resetDefaults);
applyWorkTypeTemplateButton?.addEventListener("click", applyWorkTypeTemplate);
syncWorkTypeMinStaffButton?.addEventListener("click", () => {
  syncWorkTypeMinStaffFromBasis();
  showAlert("勤務区分ごとの必要人数一覧を更新しました。", "info");
});
addTimeSlotButton?.addEventListener("click", () => {
  renderTimeSlotRows([...collectTimeSlotStaffingRules(), defaultTimeSlotRow()]);
  markDirty();
});
addStaffingBasisButton?.addEventListener("click", () => {
  renderStaffingBasisRows([...collectStaffingBasisOptions(), defaultWorkTypeRow()]);
  syncWorkTypeMinStaffFromBasis();
  rebuildFlickDirectionOptions(collectFlickDirections());
  staffingBasisTbody.lastElementChild?.querySelector(".staffing-basis-label")?.focus();
  markDirty();
});
addFloorButton?.addEventListener("click", () => {
  const current = collectFloors();
  const id = allocateFloorId(current.map((item) => item.id));
  renderFloorsEditor([...current, { id, label: "" }]);
  syncFloorLabelsFromEditor();
  floorsEditor?.querySelector(".floor-editor-row:last-child .floor-label")?.focus();
  markDirty();
});
floorsEditor?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-floor]");
  if (!button) return;
  const row = button.closest(".floor-editor-row");
  row?.remove();
  syncFloorLabelsFromEditor();
  markDirty();
});
floorsEditor?.addEventListener("input", (event) => {
  if (event.target.classList?.contains("floor-label")) {
    syncFloorLabelsFromEditor();
  }
});
staffingBasisTbody?.addEventListener("input", (event) => {
  if (!(event.target instanceof HTMLInputElement)) return;
  const row = event.target.closest(".staffing-basis-table-row");
  if (event.target.classList.contains("staffing-basis-start") || event.target.classList.contains("staffing-basis-end")) {
    if (row) updateHoursPreview(row);
    syncWorkTypeMinStaffFromBasis();
    refreshTimeSlotCoverageHints();
    return;
  }
  if (event.target.classList.contains("staffing-basis-key") || event.target.classList.contains("staffing-basis-label")) {
    syncWorkTypeMinStaffFromBasis();
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
  markDirty();
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
  if (!rows.length) { showAlert("勤務を1件以上残してください。", "error"); return; }
  if (!window.confirm("この勤務を一覧から削除します。保存するまで確定されません。続けますか？")) return;
  renderStaffingBasisRows(rows);
  markDirty();
  syncWorkTypeMinStaffFromBasis();
  rebuildFlickDirectionOptions(collectFlickDirections());
});
function validateSettingsForm() {
  const labels = new Set();
  for (const row of staffingBasisTbody.querySelectorAll(".staffing-basis-table-row")) {
    const label = row.querySelector(".staffing-basis-label");
    label.setCustomValidity(labels.has(label.value.trim()) ? "勤務名が重複しています。" : "");
    labels.add(label.value.trim());
    const end = row.querySelector(".staffing-basis-end");
    end.setCustomValidity(end.value === row.querySelector(".staffing-basis-start").value ? "開始と終了を異なる時刻にしてください。" : "");
  }
  const invalid = [...form.elements].find((field) => field.willValidate && !field.validity.valid);
  if (!invalid) return true;
  const requirementPanel = invalid.closest("[data-requirement-mode]");
  if (requirementPanel) setStaffingRequirementMode(requirementPanel.dataset.requirementMode);
  const floorRow = invalid.closest(".floor-min-staff-row");
  if (floorRow?.hidden) { const picker=document.getElementById("settings-staffing-floor");picker.value=floorRow.dataset.floor;picker.dispatchEvent(new Event("change")); }
  const section = invalid.closest(".settings-section");
  if (section?.classList.contains("is-hidden-panel")) {
    document.querySelectorAll(".settings-section").forEach((item) => item.classList.toggle("is-hidden-panel", item !== section));
  }
  for (let parent = invalid.parentElement; parent; parent = parent.parentElement) {
    if (parent instanceof HTMLDetailsElement) parent.open = true;
  }
  invalid.reportValidity();
  invalid.focus();
  return false;
}
form.noValidate = true;
loadSettings();

/* ---- バックアップ / 復元 ---- */
const backupListEl = document.getElementById("backup-list");
const backupNoteEl = document.getElementById("backup-note");
const backupFileEl = document.getElementById("backup-file");
const backupValidateResult = document.getElementById("backup-validate-result");
const btnBackupCreate = document.getElementById("btn-backup-create");
const btnBackupValidate = document.getElementById("btn-backup-validate");
const btnBackupRestore = document.getElementById("btn-backup-restore");

let pendingRestoreFilename = null;

function formatBackupWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { hour12: false });
}

function renderBackupList(items) {
  if (!backupListEl) return;
  if (!items.length) {
    backupListEl.innerHTML = "<p class=\"field-hint\">まだバックアップはありません。</p>";
    return;
  }
  const rows = items
    .map((item) => {
      const note = item.note ? `<span class="backup-note">${escapeHtml(item.note)}</span>` : "";
      const invalid = item.invalid ? "<span class=\"backup-invalid\">破損の可能性</span>" : "";
      return `<div class="backup-list-item">
        <div class="backup-list-main">
          <strong>${escapeHtml(item.filename)}</strong>
          <span class="backup-list-meta">${escapeHtml(formatBackupWhen(item.created_at || item.modified_at))}${note ? " · " : ""}${note}${invalid}</span>
        </div>
        <div class="backup-list-actions">
          <a class="btn btn-sm" href="/api/backup/download/${encodeURIComponent(item.filename)}">ダウンロード</a>
          <button type="button" class="btn btn-sm" data-backup-inspect="${escapeAttr(item.filename)}">内容確認</button>
        </div>
      </div>`;
    })
    .join("");
  backupListEl.innerHTML = rows;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("'", "&#39;");
}

async function refreshBackupList() {
  if (!backupListEl) return;
  try {
    const response = await fetch("/api/backup");
    if (!response.ok) throw new Error("list failed");
    const data = await response.json();
    renderBackupList(data.items || []);
  } catch (error) {
    backupListEl.innerHTML = "<p class=\"field-hint\">一覧を読み込めませんでした。</p>";
  }
}

function renderValidateSummary(summary) {
  if (!backupValidateResult) return;
  const rows = Object.entries(summary.overwrite_summary || {})
    .map(([key, value]) => {
      const labels = {
        staff: "職員",
        shift_assignments: "勤務セル",
        shift_placements: "配置先",
        leave_requests: "希望休",
        app_settings: "設定",
      };
      return `<tr><th>${labels[key] || key}</th><td>いま ${value.current} → バックアップ ${value.backup}</td></tr>`;
    })
    .join("");
  backupValidateResult.classList.remove("hidden");
  backupValidateResult.innerHTML = `
    <div class="backup-summary-card">
      <p><strong>復元内容の確認</strong></p>
      <p>作成日時: ${escapeHtml(formatBackupWhen(summary.created_at))}</p>
      <p>${escapeHtml(summary.warning || "")}</p>
      <table class="backup-summary-table">${rows}</table>
    </div>`;
  pendingRestoreFilename = summary.pending_filename || summary.filename || null;
  if (btnBackupRestore) {
    btnBackupRestore.classList.remove("hidden");
    btnBackupRestore.disabled = !pendingRestoreFilename;
  }
}

btnBackupCreate?.addEventListener("click", async () => {
  btnBackupCreate.disabled = true;
  try {
    const body = new FormData();
    body.set("note", backupNoteEl?.value?.trim() || "");
    const response = await fetch("/api/backup/create", { method: "POST", body });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "作成に失敗しました");
    showAlert(`バックアップを作成しました: ${data.filename}`, "info");
    if (backupNoteEl) backupNoteEl.value = "";
    await refreshBackupList();
  } catch (error) {
    showAlert(error.message || "バックアップに失敗しました", "error");
  } finally {
    btnBackupCreate.disabled = false;
  }
});

btnBackupValidate?.addEventListener("click", async () => {
  const file = backupFileEl?.files?.[0];
  if (!file) {
    showAlert("復元するZIPファイルを選んでください。", "error");
    return;
  }
  btnBackupValidate.disabled = true;
  try {
    const body = new FormData();
    body.set("file", file);
    const response = await fetch("/api/backup/validate", { method: "POST", body });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "検証に失敗しました");
    renderValidateSummary(data);
    showAlert("内容を確認しました。問題なければ「確認して復元する」を押してください。", "info");
  } catch (error) {
    pendingRestoreFilename = null;
    btnBackupRestore?.classList.add("hidden");
    if (backupValidateResult) {
      backupValidateResult.classList.add("hidden");
      backupValidateResult.innerHTML = "";
    }
    showAlert(error.message || "検証に失敗しました", "error");
  } finally {
    btnBackupValidate.disabled = false;
  }
});

btnBackupRestore?.addEventListener("click", async () => {
  if (!pendingRestoreFilename) return;
  const ok = window.confirm(
    "いまの職員・勤務表・設定などをバックアップの内容で置き換えます。\n" +
      "復元直前の状態は自動バックアップされます。実行しますか？"
  );
  if (!ok) return;
  btnBackupRestore.disabled = true;
  try {
    const body = new FormData();
    body.set("filename", pendingRestoreFilename);
    body.set("confirm", "true");
    const response = await fetch("/api/backup/restore", { method: "POST", body });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "復元に失敗しました");
    showAlert(data.message || "復元が完了しました。ページを再読み込みします。", "info");
    window.setTimeout(() => window.location.reload(), 1200);
  } catch (error) {
    showAlert(error.message || "復元に失敗しました", "error");
    btnBackupRestore.disabled = false;
  }
});

backupListEl?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-backup-inspect]");
  if (!button) return;
  const filename = button.getAttribute("data-backup-inspect");
  try {
    const response = await fetch(`/api/backup/download/${encodeURIComponent(filename)}`);
    if (!response.ok) throw new Error("取得に失敗しました");
    const blob = await response.blob();
    const file = new File([blob], filename, { type: "application/zip" });
    const body = new FormData();
    body.set("file", file);
    const validate = await fetch("/api/backup/validate", { method: "POST", body });
    const data = await validate.json().catch(() => ({}));
    if (!validate.ok) throw new Error(data.detail || "検証に失敗しました");
    renderValidateSummary(data);
  } catch (error) {
    showAlert(error.message || "内容確認に失敗しました", "error");
  }
});

refreshBackupList();
