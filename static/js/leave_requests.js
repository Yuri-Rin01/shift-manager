const PAGE = window.LEAVE_PAGE ?? {};
const alertBox = document.getElementById("leave-alert");
const settingsPanel = document.getElementById("leave-settings-panel");
const btnToggleSettings = document.getElementById("btn-toggle-settings");
const settingsForm = document.getElementById("leave-settings-form");
const filterStatus = document.getElementById("filter-status");
const filterStaff = document.getElementById("filter-staff");
const selectAll = document.getElementById("select-all-requests");
const btnBulkApprove = document.getElementById("btn-bulk-approve");
const btnBulkReject = document.getElementById("btn-bulk-reject");
const tableBody = document.getElementById("leave-requests-body");

function showAlert(message, type = "info") {
  if (!alertBox) return;
  alertBox.textContent = message;
  alertBox.className = `alert alert-${type}`;
  alertBox.classList.remove("hidden");
  window.setTimeout(() => alertBox.classList.add("hidden"), 4500);
}

function selectedPendingIds() {
  return Array.from(document.querySelectorAll(".request-check:checked"))
    .map((input) => input.closest("tr")?.dataset.id)
    .filter(Boolean)
    .map((id) => Number.parseInt(id, 10));
}

function updateBulkButtons() {
  const count = selectedPendingIds().length;
  const disabled = count === 0;
  if (btnBulkApprove) btnBulkApprove.disabled = disabled;
  if (btnBulkReject) btnBulkReject.disabled = disabled;
}

function applyFilters() {
  const status = filterStatus?.value ?? "";
  const keyword = (filterStaff?.value ?? "").trim().toLowerCase();
  tableBody?.querySelectorAll("tr[data-id]").forEach((row) => {
    const rowStatus = row.dataset.status ?? "";
    const staffName = (row.dataset.staff ?? "").toLowerCase();
    const statusOk = !status || rowStatus === status;
    const staffOk = !keyword || staffName.includes(keyword);
    row.classList.toggle("is-hidden", !(statusOk && staffOk));
  });
}

async function reloadPage() {
  const params = new URLSearchParams();
  if (PAGE.year) params.set("year", String(PAGE.year));
  if (PAGE.month) params.set("month", String(PAGE.month));
  window.location.href = `/leave-requests?${params.toString()}`;
}

async function postAction(url) {
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail ?? "操作に失敗しました");
  }
  return response.json();
}

async function bulkAction(action) {
  const ids = selectedPendingIds();
  if (!ids.length) return;
  const response = await fetch("/api/leave-requests/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, action }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.detail ?? "一括操作に失敗しました");
  }
  if (result.errors?.length) {
    const detail = result.errors.map((item) => `#${item.id}: ${item.detail}`).join(" / ");
    showAlert(`一部失敗: ${detail}`, "warn");
  } else {
    showAlert(action === "approve" ? "承認しました" : "却下しました", "success");
  }
  await reloadPage();
}

btnToggleSettings?.addEventListener("click", () => {
  settingsPanel?.classList.toggle("hidden");
  if (btnToggleSettings) {
    btnToggleSettings.textContent = settingsPanel?.classList.contains("hidden")
      ? "設定を開く"
      : "設定を閉じる";
  }
});

settingsForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const visibleTypes = {};
  ["off", "paid_leave", "half_leave"].forEach((key) => {
    const input = settingsForm.querySelector(`[name="visible_type_${key}"]`);
    visibleTypes[key] = Boolean(input?.checked);
  });
  const maxByType = {};
  settingsForm.querySelectorAll(".leave-max-by-type").forEach((input) => {
    const type = input.dataset.type;
    if (!type) return;
    maxByType[type] = Number.parseInt(input.value || "0", 10) || 0;
  });
  const maxTotalRaw = document.getElementById("leave-max-total")?.value ?? "";
  const payload = {
    leave_request_visible_types: visibleTypes,
    leave_request_max_by_type: maxByType,
    leave_request_over_limit_message:
      document.getElementById("leave-over-limit-message")?.value?.trim() ?? "",
    leave_request_max_total: maxTotalRaw === "" ? null : Number.parseInt(maxTotalRaw, 10),
  };
  const response = await fetch("/api/leave-requests/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    showAlert(error.detail ?? "設定の保存に失敗しました", "error");
    return;
  }
  const saved = await response.json();
  const resolved = document.getElementById("resolved-max-total");
  if (resolved && saved.leave_request_max_total_resolved != null) {
    resolved.textContent = String(saved.leave_request_max_total_resolved);
  }
  showAlert("ポータル連携設定を保存しました", "success");
});

filterStatus?.addEventListener("change", applyFilters);
filterStaff?.addEventListener("input", applyFilters);

selectAll?.addEventListener("change", () => {
  const checked = Boolean(selectAll.checked);
  tableBody?.querySelectorAll("tr:not(.is-hidden) .request-check:not(:disabled)").forEach((input) => {
    input.checked = checked;
  });
  updateBulkButtons();
});

tableBody?.addEventListener("change", (event) => {
  if (event.target.matches(".request-check")) updateBulkButtons();
});

tableBody?.addEventListener("click", async (event) => {
  const approveBtn = event.target.closest(".btn-approve-one");
  const rejectBtn = event.target.closest(".btn-reject-one");
  if (!approveBtn && !rejectBtn) return;
  const id = approveBtn?.dataset.id ?? rejectBtn?.dataset.id;
  if (!id) return;
  try {
    if (approveBtn) {
      await postAction(`/api/leave-requests/${id}/approve`);
      showAlert("承認しました", "success");
    } else {
      await postAction(`/api/leave-requests/${id}/reject`);
      showAlert("却下しました", "success");
    }
    await reloadPage();
  } catch (error) {
    showAlert(error.message ?? "操作に失敗しました", "error");
  }
});

btnBulkApprove?.addEventListener("click", async () => {
  try {
    await bulkAction("approve");
  } catch (error) {
    showAlert(error.message ?? "一括承認に失敗しました", "error");
  }
});

btnBulkReject?.addEventListener("click", async () => {
  try {
    await bulkAction("reject");
  } catch (error) {
    showAlert(error.message ?? "一括却下に失敗しました", "error");
  }
});

applyFilters();
updateBulkButtons();
