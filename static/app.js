const state = {
  user: null,
  csrf: "",
  users: [],
  machines: [],
  accounts: [],
  settings: {},
  selectedOwnerId: null,
  selectedMachineId: "ALL",
  selectedAccounts: new Set(),
  statusFilter: "ALL",
  companyMode: false,
  currentRun: null,
  socket: null,
  refreshTimer: null,
  speechEnabled: localStorage.getItem("tiktokSpeechEnabled") === "1",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];


// Xóa username/password hoặc query cũ khỏi thanh địa chỉ
if (window.location.search) {
  window.history.replaceState(
    {},
    document.title,
    window.location.pathname
  );
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeUrl(value) {
  try {
    const url = new URL(String(value || ""), location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function formatNumber(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("vi-VN").format(value);
}

function formatTime(value) {
  if (!value) return "Chưa check";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("vi-VN", { hour12: false });
}

function initials(name) {
  return String(name || "?").trim().split(/\s+/).slice(-2).map((part) => part[0]).join("").toUpperCase();
}

function toast(message, type = "info", timeout = 4200) {
  const item = document.createElement("div");
  item.className = `toast ${type}`;
  item.textContent = message;
  $("#toast-container").appendChild(item);
  setTimeout(() => item.remove(), timeout);
}

async function api(path, options = {}, quiet = false) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(method) && state.csrf) headers.set("X-CSRF-Token", state.csrf);
  const response = await fetch(path, { ...options, method, headers, credentials: "same-origin" });
  let data = {};
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") showLogin();
    const message = data.detail || `Lỗi HTTP ${response.status}`;
    if (!quiet) toast(message, "error");
    throw new Error(message);
  }
  return data;
}

function showLogin() {
  state.user = null;
  state.csrf = "";
  $("#app-view").classList.add("hidden");
  $("#login-view").classList.remove("hidden");
}

function showApp() {
  $("#login-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
  $("#current-user-name").textContent = state.user.full_name;
  $("#current-user-role").textContent = state.user.role;
  $$(".boss-only").forEach((element) => element.classList.toggle("hidden", state.user.role !== "BOSS"));
  updateVoiceButton();
}

async function init() {
  try {
    const health = await api("/api/health", {}, true);
    if (health.status !== "ok") {
      const banner = $("#setup-banner");
      banner.textContent = `Chưa kết nối database: ${health.detail || "hãy chạy scripts/setup_local.py"}`;
      banner.classList.remove("hidden");
    }
  } catch {
    // Server error will be shown by login when the user tries to continue.
  }

  try {
    const response = await api("/api/auth/me", {}, true);
    state.user = response.user;
    state.csrf = response.csrf_token;
    showApp();
    await loadEverything();
  } catch {
    showLogin();
  }
}

async function loadEverything() {
  const [usersResponse, dashboardResponse, settingsResponse, runsResponse] = await Promise.all([
    api("/api/users"),
    api("/api/dashboard"),
    api("/api/settings"),
    api("/api/check-runs/current"),
  ]);
  state.users = usersResponse.users;
  state.settings = settingsResponse.settings;
  renderPeople();
  renderDashboard(dashboardResponse);
  renderChanges(dashboardResponse.recent_changes || []);
  if (!state.selectedOwnerId) state.selectedOwnerId = state.user.id;
  await selectUser(state.selectedOwnerId);
  if (runsResponse.runs?.length) renderJob(runsResponse.runs[0]);
  connectWebSocket();
}

async function refreshUsers() {
  const response = await api("/api/users");
  state.users = response.users;
  renderPeople();
}

async function refreshDashboard() {
  const response = await api("/api/dashboard");
  renderDashboard(response);
  renderChanges(response.recent_changes || []);
}

function renderDashboard(data) {
  $("#dashboard-title").textContent = state.user.role === "BOSS"
    ? "Toàn công ty"
    : state.user.role === "LEADER" ? "Cá nhân và Member trực thuộc" : "Danh sách của tôi";
  $("#metric-total").textContent = formatNumber(data.total);
  $("#metric-live").textContent = formatNumber(data.live);
  $("#metric-die").textContent = formatNumber(data.die);
  $("#metric-error").textContent = formatNumber(data.error);
  $("#metric-problem").textContent = formatNumber(data.new_problem);
  $("#last-check-at").textContent = formatTime(data.last_checked_at);
}

function renderChanges(items) {
  const container = $("#changes-list");
  if (!items.length) {
    container.innerHTML = '<div class="muted">Chưa có hai mốc check tự động để so sánh.</div>';
    return;
  }
  container.innerHTML = items.map((item) => {
    const sign = item.delta > 0 ? "+" : "";
    return `<button class="change-item" data-owner-id="${escapeHtml(item.owner_id || "")}" data-account-id="${escapeHtml(item.account_id)}">
      <strong>@${escapeHtml(item.username)} · ${sign}${formatNumber(item.delta)} follow</strong>
      <span>${escapeHtml(item.owner_name)} · Máy ${item.machine_number}, kênh ${item.slot_number}</span>
      <span>${formatNumber(item.before)} → ${formatNumber(item.after)} · ${formatTime(item.checked_at)}</span>
    </button>`;
  }).join("");
}

function renderPeople() {
  const container = $("#people-list");
  const activeClass = (id) => !state.companyMode && state.selectedOwnerId === id ? "active" : "";
  const personButton = (user, indent = false) => `
    <div class="${indent ? "member-indent" : ""}">
      <button class="person-btn ${activeClass(user.id)}" data-person-id="${user.id}">
        <span class="person-avatar">${escapeHtml(initials(user.full_name))}</span>
        <span class="person-copy"><strong>${escapeHtml(user.full_name)}</strong><span>${user.role} · @${escapeHtml(user.username)}${user.is_active ? "" : " · Đã khóa"}</span></span>
        <span class="person-count">${user.account_count}</span>
      </button>
      ${state.user.role === "BOSS" && user.role !== "BOSS" ? `<div class="person-tools"><button data-edit-user="${user.id}">Sửa</button>${user.role === "LEADER" ? `<button data-check-group="${user.id}">Check nhóm</button>` : ""}</div>` : ""}
    </div>`;

  if (state.user.role === "BOSS") {
    const bosses = state.users.filter((user) => user.role === "BOSS");
    const leaders = state.users.filter((user) => user.role === "LEADER");
    container.innerHTML = `
      <div class="person-group"><div class="group-label">BOSS</div>${bosses.map((user) => personButton(user)).join("")}</div>
      <div class="person-group"><div class="group-label">LEADER VÀ MEMBER</div>${leaders.map((leader) => `
        ${personButton(leader)}
        ${state.users.filter((member) => member.leader_id === leader.id).map((member) => personButton(member, true)).join("")}
      `).join("") || '<div class="muted">Chưa có Leader.</div>'}</div>`;
  } else if (state.user.role === "LEADER") {
    const self = state.users.find((user) => user.id === state.user.id);
    const members = state.users.filter((user) => user.leader_id === state.user.id);
    container.innerHTML = `<div class="group-label">CỦA TÔI</div>${self ? personButton(self) : ""}<div class="group-label">MEMBER TRỰC THUỘC</div>${members.map((user) => personButton(user)).join("") || '<div class="muted">Chưa có Member.</div>'}`;
  } else {
    container.innerHTML = state.users.map((user) => personButton(user)).join("");
  }
}

async function selectUser(userId) {
  const user = state.users.find((item) => item.id === userId);
  if (!user) return;
  state.companyMode = false;
  state.selectedOwnerId = userId;
  state.selectedMachineId = "ALL";
  state.selectedAccounts.clear();
  renderPeople();
  $("#selected-owner-name").textContent = user.full_name;
  $("#selected-owner-meta").textContent = `${user.role} · ${user.machine_count} máy · ${user.account_count} kênh`;
  $("#owner-path").textContent = user.leader_id
    ? `MEMBER CỦA ${state.users.find((item) => item.id === user.leader_id)?.full_name || "LEADER"}`
    : "DANH SÁCH KÊNH";
  updateOwnerActions(user);
  await Promise.all([loadMachines(), loadAccounts()]);
}

async function showAllScope(filter = "ALL") {
  state.companyMode = true;
  state.selectedOwnerId = null;
  state.selectedMachineId = "ALL";
  state.selectedAccounts.clear();
  state.statusFilter = filter;
  $("#selected-owner-name").textContent = state.user.role === "BOSS" ? "Toàn công ty" : "Toàn bộ phạm vi của tôi";
  $("#selected-owner-meta").textContent = "Dữ liệu tổng hợp theo quyền đăng nhập";
  $("#owner-path").textContent = "DASHBOARD FILTER";
  renderPeople();
  renderMachineTabs();
  updateOwnerActions(null);
  await loadAccounts();
  updateFilterChips();
}

function canAddForSelected() {
  return !state.companyMode && (state.user.role === "BOSS" || (state.selectedOwnerId === state.user.id && state.user.can_add_accounts));
}

function canDeleteForSelected() {
  return !state.companyMode && (state.user.role === "BOSS" || (state.selectedOwnerId === state.user.id && state.user.can_delete_accounts));
}

function updateOwnerActions(user) {
  const canAdd = canAddForSelected();
  $("#add-machine-btn").classList.toggle("hidden", !canAdd);
  $("#add-account-btn").classList.toggle("hidden", !canAdd);
  const canCheck = state.user.role === "BOSS" || state.user.can_run_checks;
  $("#check-owner-btn").disabled = !canCheck || (!user && state.user.role !== "BOSS");
  $("#check-owner-btn").textContent = state.companyMode ? "Check toàn công ty" : "Check người này";
  $("#check-selected-btn").disabled = !canCheck || state.selectedAccounts.size === 0;
}

async function loadMachines() {
  if (state.companyMode || !state.selectedOwnerId) {
    state.machines = [];
    renderMachineTabs();
    return;
  }
  const response = await api(`/api/machines?owner_id=${encodeURIComponent(state.selectedOwnerId)}`);
  state.machines = response.machines;
  renderMachineTabs();
}

function renderMachineTabs() {
  const container = $("#machine-tabs");
  const total = state.accounts.length;
  let html = `<button class="machine-tab ${state.selectedMachineId === "ALL" ? "active" : ""}" data-machine-id="ALL">Tất cả <small>${total}</small></button>`;
  if (!state.companyMode) {
    html += state.machines.map((machine) => `
      <button class="machine-tab ${state.selectedMachineId === machine.id ? "active" : ""}" data-machine-id="${machine.id}">Máy #${machine.machine_number} <small>${machine.account_count}/10</small></button>
      ${canDeleteForSelected() ? `<button class="machine-tab" data-delete-machine="${machine.id}" title="Xóa máy #${machine.machine_number}">×</button>` : ""}
    `).join("");
  }
  container.innerHTML = html;
}

async function loadAccounts() {
  const owner = state.companyMode ? "ALL" : state.selectedOwnerId;
  if (!owner) return;
  const response = await api(`/api/accounts?owner_id=${encodeURIComponent(owner)}`);
  state.accounts = response.accounts;
  state.selectedAccounts = new Set([...state.selectedAccounts].filter((id) => state.accounts.some((account) => account.id === id)));
  renderMachineTabs();
  renderAccounts();
}

function filteredAccounts() {
  const search = $("#account-search").value.trim().toLowerCase();
  return state.accounts.filter((account) => {
    if (state.selectedMachineId !== "ALL" && account.machine_id !== state.selectedMachineId) return false;
    if (state.statusFilter === "PROBLEM" && !(account.previous_status === "LIVE" && ["DIE", "ERROR"].includes(account.status))) return false;
    if (!["ALL", "PROBLEM"].includes(state.statusFilter) && account.status !== state.statusFilter) return false;
    return !search || account.username.toLowerCase().includes(search) || String(account.nickname || "").toLowerCase().includes(search);
  });
}

function statusBadge(account) {
  const css = account.status.toLowerCase();
  const privateText = account.is_private ? '<span class="private-note">Riêng tư</span>' : "";
  return `<span class="status-badge ${css}">${escapeHtml(account.status)}</span> ${privateText}`;
}

function renderAccounts() {
  const rows = filteredAccounts();
  $("#accounts-empty").classList.toggle("hidden", rows.length > 0);
  $("#accounts-body").innerHTML = rows.map((account) => {
    const avatar = safeUrl(account.avatar_url);
    const delta = account.follower_delta;
    const deltaHtml = delta === null || delta === 0 ? "" : `<span class="delta ${delta > 0 ? "up" : "down"}">${delta > 0 ? "+" : ""}${formatNumber(delta)}</span>`;
    return `<tr>
      <td><input class="account-checkbox" type="checkbox" data-account-id="${account.id}" ${state.selectedAccounts.has(account.id) ? "checked" : ""}></td>
      <td><strong>M${account.machine_number}–K${account.slot_number}</strong><br><span class="muted">${escapeHtml(account.owner_name)}</span></td>
      <td><div class="account-cell">${avatar ? `<img class="account-avatar" src="${escapeHtml(avatar)}" alt="">` : '<span class="account-avatar"></span>'}<span class="account-copy"><strong>@${escapeHtml(account.username)}</strong><span>${escapeHtml(account.nickname || "Chưa có nickname")}</span></span></div></td>
      <td>${statusBadge(account)}${account.last_error_message ? `<br><span class="muted" title="${escapeHtml(account.last_error_message)}">${escapeHtml(account.last_error_code || "Lỗi")}</span>` : ""}</td>
      <td><strong>${formatNumber(account.followers)}</strong>${deltaHtml}</td>
      <td>${formatNumber(account.total_sample_views)}</td>
      <td>${formatTime(account.last_checked_at)}</td>
      <td><div class="row-actions"><button data-view-account="${account.id}">Chi tiết</button>${canDeleteForSelected() ? `<button data-delete-account="${account.id}">Xóa</button>` : ""}</div></td>
    </tr>`;
  }).join("");
  $("#select-all-accounts").checked = rows.length > 0 && rows.every((account) => state.selectedAccounts.has(account.id));
  updateOwnerActions(state.users.find((user) => user.id === state.selectedOwnerId) || null);
}

function updateFilterChips() {
  $$(".filter-chip").forEach((chip) => chip.classList.toggle("active", chip.dataset.status === state.statusFilter));
}

function openModal(title, html) {
  $("#modal-title").textContent = title;
  $("#modal-content").innerHTML = html;
  $("#modal-backdrop").classList.remove("hidden");
  $("#modal-backdrop").setAttribute("aria-hidden", "false");
}

function closeModal() {
  $("#modal-backdrop").classList.add("hidden");
  $("#modal-backdrop").setAttribute("aria-hidden", "true");
  $("#modal-content").innerHTML = "";
}

async function addMachine() {
  const input = prompt("Nhập số được ghi trên máy, ví dụ: 47");
  if (input === null) return;

  const cleanedInput = input.trim().replace(/^#/, "");
  const machineNumber = Number(cleanedInput);

  if (
    !Number.isInteger(machineNumber) ||
    machineNumber < 1 ||
    machineNumber > 32767
  ) {
    toast("Số máy không hợp lệ", "error");
    return;
  }

  await api("/api/machines", {
    method: "POST",
    body: JSON.stringify({
      owner_id: state.selectedOwnerId,
      machine_number: machineNumber
    })
  });

  toast(`Đã thêm máy #${machineNumber}`, "success");
  await Promise.all([loadMachines(), refreshUsers()]);
}

async function deleteMachine(machineId) {
  const machine = state.machines.find((item) => item.id === machineId);
  if (!confirm(`Xóa máy ${machine?.machine_number || ""} và toàn bộ kênh trong máy? Dữ liệu không thể khôi phục.`)) return;
  await api(`/api/machines/${machineId}`, { method: "DELETE" });
  state.selectedMachineId = "ALL";
  toast("Đã xóa máy", "success");
  await Promise.all([loadMachines(), loadAccounts(), refreshUsers(), refreshDashboard()]);
}

function openAddAccounts() {
  if (!state.machines.length) {
    toast("Hãy thêm máy trước khi thêm kênh", "error");
    return;
  }
  openModal("Thêm kênh TikTok", `
    <form id="add-accounts-form" class="stack-form">
      <label>Chọn máy<select id="bulk-machine" required>${state.machines.map((machine) => `<option value="${machine.id}" ${state.selectedMachineId === machine.id ? "selected" : ""}>Máy #${machine.machine_number} · còn ${10 - machine.account_count} vị trí</option>`).join("")}</select></label>
      <label>Username, mỗi dòng một kênh<textarea id="bulk-items" placeholder="@username\nhttps://www.tiktok.com/@username\nusername|password|email" required></textarea></label>
      <p class="muted">Hệ thống chỉ lấy username, không lưu password, email hoặc 2FA.</p>
      <div class="modal-actions"><button type="button" class="btn subtle" data-close-modal>Hủy</button><button class="btn primary" type="submit">Thêm danh sách</button></div>
    </form>`);
  $("#add-accounts-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const items = $("#bulk-items").value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    try {
      const response = await api("/api/accounts/bulk", { method: "POST", body: JSON.stringify({ machine_id: $("#bulk-machine").value, items }) });
      closeModal();
      toast(`Đã thêm ${response.added.length} kênh${response.rejected.length ? `, bỏ qua ${response.rejected.length}` : ""}`, response.added.length ? "success" : "error", 6000);
      if (response.rejected.length) {
        openModal("Các dòng bị bỏ qua", `<div class="stack-form">${response.rejected.map((item) => `<div class="search-result"><span>${escapeHtml(item.input)}</span><small>${escapeHtml(item.reason)}</small></div>`).join("")}<div class="modal-actions"><button class="btn primary" data-close-modal>Đã hiểu</button></div></div>`);
      }
      await Promise.all([loadMachines(), loadAccounts(), refreshUsers(), refreshDashboard()]);
    } catch {}
  });
}

async function deleteAccount(accountId) {
  const account = state.accounts.find((item) => item.id === accountId);
  if (!confirm(`Xóa @${account?.username || ""} và toàn bộ dữ liệu hiện tại của kênh?`)) return;
  await api(`/api/accounts/${accountId}`, { method: "DELETE" });
  toast("Đã xóa kênh", "success");
  await Promise.all([loadMachines(), loadAccounts(), refreshUsers(), refreshDashboard()]);
}

function showAccountDetail(accountId) {
  const account = state.accounts.find((item) => item.id === accountId);
  if (!account) return;
  const avatar = safeUrl(account.avatar_url);
  const videos = (account.recent_videos || []).map((video) => {
    const cover = safeUrl(video.cover_url);
    const url = safeUrl(video.video_url);
    return `<article class="video-card">${cover ? `<img src="${escapeHtml(cover)}" alt="">` : ""}<div><strong>${formatNumber(video.play_count)} views</strong><p class="muted">${escapeHtml(video.desc || "Không có mô tả")}</p>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Mở TikTok ↗</a>` : ""}</div></article>`;
  }).join("");
  openModal(`Chi tiết @${account.username}`, `
    <div class="video-profile">${avatar ? `<img src="${escapeHtml(avatar)}" alt="">` : ""}<div><h3>${escapeHtml(account.nickname || `@${account.username}`)}</h3><p class="muted">${escapeHtml(account.bio || "Chưa có bio")}</p></div></div>
    <div class="form-grid"><div><span class="muted">Followers</span><h3>${formatNumber(account.followers)}</h3></div><div><span class="muted">Following</span><h3>${formatNumber(account.following)}</h3></div><div><span class="muted">Tổng likes</span><h3>${formatNumber(account.total_likes)}</h3></div><div><span class="muted">Tổng view mẫu</span><h3>${formatNumber(account.total_sample_views)}</h3></div></div>
    <h3 style="margin-top:22px">Video công khai gần đây</h3><div class="video-grid">${videos || '<p class="muted">Không có video công khai hoặc tài khoản riêng tư.</p>'}</div>
    ${state.user.role === "BOSS" ? `<div class="modal-actions"><button class="btn subtle" data-transfer-account="${account.id}">Chuyển máy/người sở hữu</button></div>` : ""}`);
}

async function openTransferAccount(accountId) {
  const account = state.accounts.find((item) => item.id === accountId);
  if (!account) return;
  openModal(`Chuyển @${account.username}`, `<form id="transfer-form" class="stack-form"><label>Người nhận<select id="transfer-owner">${state.users.filter((user) => user.is_active).map((user) => `<option value="${user.id}" ${user.id === account.owner_id ? "selected" : ""}>${escapeHtml(user.full_name)} · ${user.role}</option>`).join("")}</select></label><label>Máy đích<select id="transfer-machine"></select></label><label>Vị trí kênh<input id="transfer-slot" type="number" min="1" max="10" value="${account.slot_number}" required></label><div class="modal-actions"><button type="button" class="btn subtle" data-close-modal>Hủy</button><button class="btn primary">Chuyển kênh</button></div></form>`);
  async function loadTargetMachines() {
    try {
      const response = await api(`/api/machines?owner_id=${encodeURIComponent($("#transfer-owner").value)}`);
      $("#transfer-machine").innerHTML = response.machines.map((machine) => `<option value="${machine.id}" ${machine.id === account.machine_id ? "selected" : ""}>Máy #${machine.machine_number} · ${machine.account_count}/10 kênh</option>`).join("");
      if (!response.machines.length) $("#transfer-machine").innerHTML = '<option value="">Người này chưa có máy</option>';
    } catch {}
  }
  $("#transfer-owner").addEventListener("change", loadTargetMachines);
  await loadTargetMachines();
  $("#transfer-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const machineId = $("#transfer-machine").value;
    if (!machineId) return toast("Người nhận chưa có máy", "error");
    try {
      await api(`/api/accounts/${account.id}/transfer`, { method: "PATCH", body: JSON.stringify({ machine_id: machineId, slot_number: Number($("#transfer-slot").value) }) });
      closeModal();
      toast("Đã chuyển kênh", "success");
      await Promise.all([loadAccounts(), loadMachines(), refreshUsers(), refreshDashboard()]);
    } catch {}
  });
}

function leaderOptions(selected = "") {
  return state.users.filter((user) => user.role === "LEADER" && user.is_active).map((leader) => `<option value="${leader.id}" ${leader.id === selected ? "selected" : ""}>${escapeHtml(leader.full_name)}</option>`).join("");
}

function openUserForm(userId = null) {
  const user = state.users.find((item) => item.id === userId);
  const editing = Boolean(user);
  openModal(editing ? `Sửa ${user.full_name}` : "Thêm Leader hoặc Member", `
    <form id="user-form" class="stack-form">
      <div class="form-grid">
        ${editing ? "" : `<label>Tên đăng nhập<input id="user-username" required minlength="3"></label><label>Mật khẩu ban đầu<input id="user-password" type="password" required minlength="8"></label>`}
        <label class="${editing ? "full-row" : ""}">Họ tên<input id="user-full-name" value="${escapeHtml(user?.full_name || "")}" required></label>
        ${editing ? `<label>Role<input value="${escapeHtml(user.role)}" disabled></label>` : `<label>Role<select id="user-role"><option value="LEADER">LEADER</option><option value="MEMBER">MEMBER</option></select></label>`}
        <label id="leader-field" class="full-row ${(!editing || user.role !== "MEMBER") ? "hidden" : ""}">Leader quản lý<select id="user-leader"><option value="">Chọn Leader</option>${leaderOptions(user?.leader_id)}</select></label>
      </div>
      <div class="check-row">
        <label><input id="perm-add" type="checkbox" ${user?.can_add_accounts ? "checked" : ""}> Tự thêm kênh</label>
        <label><input id="perm-delete" type="checkbox" ${user?.can_delete_accounts ? "checked" : ""}> Tự xóa kênh</label>
        <label><input id="perm-check" type="checkbox" ${user?.can_run_checks ?? true ? "checked" : ""}> Được check</label>
        ${editing ? `<label><input id="user-active" type="checkbox" ${user.is_active ? "checked" : ""}> Đang hoạt động</label>` : ""}
      </div>
      <div class="modal-actions">${editing ? '<button id="reset-password-btn" type="button" class="btn danger ghost">Reset mật khẩu</button>' : ""}<button type="button" class="btn subtle" data-close-modal>Hủy</button><button class="btn primary" type="submit">${editing ? "Lưu thay đổi" : "Tạo tài khoản"}</button></div>
    </form>`);

  const roleSelect = $("#user-role");
  roleSelect?.addEventListener("change", () => $("#leader-field").classList.toggle("hidden", roleSelect.value !== "MEMBER"));
  $("#user-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const common = {
      full_name: $("#user-full-name").value.trim(),
      can_add_accounts: $("#perm-add").checked,
      can_delete_accounts: $("#perm-delete").checked,
      can_run_checks: $("#perm-check").checked,
    };
    try {
      if (editing) {
        const payload = { ...common, is_active: $("#user-active").checked };
        if (user.role === "MEMBER") payload.leader_id = $("#user-leader").value;
        await api(`/api/users/${user.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        const role = $("#user-role").value;
        await api("/api/users", { method: "POST", body: JSON.stringify({
          ...common,
          username: $("#user-username").value.trim(),
          password: $("#user-password").value,
          role,
          leader_id: role === "MEMBER" ? $("#user-leader").value : null,
        }) });
      }
      closeModal();
      toast(editing ? "Đã cập nhật người dùng" : "Đã tạo tài khoản", "success");
      await refreshUsers();
    } catch {}
  });
  $("#reset-password-btn")?.addEventListener("click", async () => {
    const password = prompt(`Nhập mật khẩu mới cho ${user.full_name} (tối thiểu 8 ký tự):`);
    if (!password) return;
    try {
      await api(`/api/users/${user.id}/reset-password`, { method: "POST", body: JSON.stringify({ new_password: password }) });
      toast("Đã reset mật khẩu", "success");
    } catch {}
  });
}

function openManageUsers() {
  openModal("Quản lý nhân sự", `<div class="modal-actions" style="margin-top:0"><button id="modal-add-user" class="btn primary">+ Thêm Leader/Member</button></div><div style="margin-top:14px">${state.users.filter((user) => user.role !== "BOSS").map((user) => `<button class="search-result" data-modal-edit-user="${user.id}"><span><strong>${escapeHtml(user.full_name)}</strong><br><small>${user.role} · @${escapeHtml(user.username)}</small></span><small>${user.account_count} kênh · ${user.is_active ? "Hoạt động" : "Đã khóa"}</small></button>`).join("") || '<p class="muted">Chưa có Leader hoặc Member.</p>'}</div>`);
  $("#modal-add-user").addEventListener("click", () => openUserForm());
}

function openChangePassword() {
  openModal("Đổi mật khẩu", `<form id="password-form" class="stack-form"><label>Mật khẩu hiện tại<input id="current-password" type="password" required></label><label>Mật khẩu mới<input id="new-password" type="password" minlength="8" required></label><div class="modal-actions"><button type="button" class="btn subtle" data-close-modal>Hủy</button><button class="btn primary">Đổi mật khẩu</button></div></form>`);
  $("#password-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/auth/change-password", { method: "POST", body: JSON.stringify({ current_password: $("#current-password").value, new_password: $("#new-password").value }) });
      closeModal();
      toast("Đã đổi mật khẩu", "success");
    } catch {}
  });
}

function openSettings() {
  const s = state.settings;
  openModal("Cấu hình checker và lịch tự động", `<form id="settings-form" class="stack-form"><div class="form-grid">
    <label>Chu kỳ tự động (phút)<input id="setting-interval" type="number" min="15" max="1440" value="${s.check_interval_minutes || 60}"></label>
    <label>Ngưỡng thay đổi follow<input id="setting-threshold" type="number" min="1" value="${s.follower_change_threshold || 1}"></label>
    <label>Tổng worker<input id="setting-total-workers" type="number" min="1" max="50" value="${s.max_total_workers || 10}"></label>
    <label>Worker mỗi job<input id="setting-job-workers" type="number" min="1" max="20" value="${s.max_workers_per_job || 3}"></label>
    <label>Timeout (giây)<input id="setting-timeout" type="number" min="3" max="120" value="${s.request_timeout_seconds || 12}"></label>
    <label>Retry lỗi mạng<input id="setting-retry" type="number" min="0" max="5" value="${s.retry_count ?? 2}"></label>
    <label>Xác nhận DIE<input id="setting-dead" type="number" min="2" max="5" value="${s.dead_confirmation_attempts || 2}"></label>
    <label>Delay request (giây)<input id="setting-delay" type="number" step="0.1" min="0" max="60" value="${s.request_delay_seconds ?? 0.3}"></label>
  </div><div class="check-row"><label><input id="setting-auto" type="checkbox" ${s.auto_check_enabled ? "checked" : ""}> Bật check toàn công ty tự động</label><label><input id="setting-notify" type="checkbox" ${s.in_app_notifications_enabled ?? true ? "checked" : ""}> Thông báo trong web</label><label><input id="setting-voice" type="checkbox" ${s.voice_notifications_enabled ? "checked" : ""}> Cho phép đọc loa</label></div>
  <p class="muted">Múi giờ: Asia/Ho_Chi_Minh · Lần chạy kế: ${formatTime(s.next_auto_check_at)}</p><div class="modal-actions"><button type="button" class="btn subtle" data-close-modal>Hủy</button><button class="btn primary">Lưu cấu hình</button></div></form>`);
  $("#settings-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      auto_check_enabled: $("#setting-auto").checked,
      check_interval_minutes: Number($("#setting-interval").value),
      follower_change_threshold: Number($("#setting-threshold").value),
      max_total_workers: Number($("#setting-total-workers").value),
      max_workers_per_job: Number($("#setting-job-workers").value),
      request_timeout_seconds: Number($("#setting-timeout").value),
      retry_count: Number($("#setting-retry").value),
      dead_confirmation_attempts: Number($("#setting-dead").value),
      request_delay_seconds: Number($("#setting-delay").value),
      in_app_notifications_enabled: $("#setting-notify").checked,
      voice_notifications_enabled: $("#setting-voice").checked,
    };
    try {
      const response = await api("/api/settings", { method: "PATCH", body: JSON.stringify(payload) });
      state.settings = (await api("/api/settings")).settings;
      closeModal();
      toast(response.message, "success", 6000);
    } catch {}
  });
}

function openGlobalSearch() {
  openModal("Tìm username toàn công ty", `<form id="global-search-form" class="stack-form"><label>Username TikTok<input id="global-search-input" placeholder="@username" autofocus required></label><button class="btn primary">Tìm kiếm</button></form><div id="global-search-results" style="margin-top:14px"></div>`);
  $("#global-search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const response = await api(`/api/search?q=${encodeURIComponent($("#global-search-input").value)}`);
      $("#global-search-results").innerHTML = response.results.length ? response.results.map((item) => `<button class="search-result" data-search-owner="${item.owner_id}"><span><strong>@${escapeHtml(item.username)}</strong><br><small>${escapeHtml(item.owner_name)} · ${item.owner_role}${item.leader_name ? ` · Leader ${escapeHtml(item.leader_name)}` : ""}</small></span><small>Máy #${item.machine_number}, kênh ${item.slot_number}</small></button>`).join("") : '<p class="muted">Không tìm thấy username.</p>';
    } catch {}
  });
}

async function startCheck(scopeType, targetUserId = null, accountIds = []) {
  try {
    const response = await api("/api/check-runs", { method: "POST", body: JSON.stringify({ scope_type: scopeType, target_user_id: targetUserId, account_ids: accountIds }) });
    renderJob(response.run);
    toast("Đã bắt đầu job check", "success");
  } catch {}
}

function renderJob(run) {
  if (!run) return;
  state.currentRun = run;
  const done = ["COMPLETED", "STOPPED", "FAILED"].includes(run.status);
  $("#job-panel").classList.toggle("hidden", done && Number(run.processed_accounts || 0) === 0);
  $("#job-label").textContent = run.trigger_type === "SCHEDULED" ? "Check tự động toàn công ty" : `Job ${run.status}`;
  $("#job-count").textContent = `${run.processed_accounts || 0}/${run.total_accounts || 0}`;
  $("#job-progress").style.width = `${run.progress_percent || 0}%`;
  $("#job-stats").textContent = `LIVE ${run.live_count || 0} · DIE ${run.die_count || 0} · ERROR ${run.error_count || 0} · Thay đổi follow ${run.follower_changed_count || 0}`;
  $("#stop-job-btn").classList.toggle("hidden", done);
  if (done) setTimeout(() => $("#job-panel").classList.add("hidden"), 4500);
}

function scheduleDataRefresh() {
  clearTimeout(state.refreshTimer);
  state.refreshTimer = setTimeout(async () => {
    try {
      await Promise.all([loadAccounts(), refreshDashboard(), refreshUsers()]);
    } catch {}
  }, 500);
}

function connectWebSocket() {
  if (state.socket) state.socket.close();
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${location.host}/ws`);
  state.socket = socket;
  socket.onmessage = (event) => {
    let message;
    try { message = JSON.parse(event.data); } catch { return; }
    if (["job_started", "job_progress", "job_finished", "job_failed"].includes(message.type)) {
      if (message.data.run) renderJob(message.data.run);
      if (message.type !== "job_started") scheduleDataRefresh();
      if (message.type === "job_finished") toast("Job check đã hoàn thành", "success");
      if (message.type === "job_failed") toast(message.data.run?.message || "Job check thất bại", "error");
    }
    if (message.type === "alert") {
      toast(message.data.message, message.data.type === "STATUS_CHANGE" ? "error" : "success", 9000);
      if (message.data.voice_enabled) speak(message.data.message);
    }
  };
  socket.onclose = () => {
    if (state.user) setTimeout(connectWebSocket, 3000);
  };
}

function updateVoiceButton() {
  $("#voice-enable-btn").textContent = state.speechEnabled ? "🔊 Đang bật đọc loa" : "🔈 Bật đọc thông báo";
}

function toggleSpeech() {
  state.speechEnabled = !state.speechEnabled;
  localStorage.setItem("tiktokSpeechEnabled", state.speechEnabled ? "1" : "0");
  updateVoiceButton();
  if (state.speechEnabled) speak("Đã bật loa trình duyệt. BOSS có thể bật đọc tự động trong mục Cấu hình.");
}

function speak(message) {
  if (!state.speechEnabled || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const speech = new SpeechSynthesisUtterance(message);
  speech.lang = "vi-VN";
  speech.rate = 1;
  window.speechSynthesis.speak(speech);
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#login-error").textContent = "";
  try {
    const response = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ username: $("#login-username").value, password: $("#login-password").value }) }, true);
    state.user = response.user;
    state.csrf = response.csrf_token;
    showApp();
    await loadEverything();
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
});

$("#logout-btn").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }, true); } catch {}
  if (state.socket) state.socket.close();
  showLogin();
});
$("#change-password-btn").addEventListener("click", openChangePassword);
$("#voice-enable-btn").addEventListener("click", toggleSpeech);
$("#quick-add-user-btn").addEventListener("click", () => openUserForm());
$("#manage-users-btn").addEventListener("click", openManageUsers);
$("#settings-btn").addEventListener("click", openSettings);
$("#global-search-btn").addEventListener("click", openGlobalSearch);
$("#add-machine-btn").addEventListener("click", addMachine);
$("#add-account-btn").addEventListener("click", openAddAccounts);
$("#check-selected-btn").addEventListener("click", () => startCheck("SELECTED", null, [...state.selectedAccounts]));
$("#check-owner-btn").addEventListener("click", () => state.companyMode ? startCheck("COMPANY") : startCheck("USER", state.selectedOwnerId));
$("#check-company-btn").addEventListener("click", () => { if (confirm("Bắt đầu check toàn bộ kênh trong công ty?")) startCheck("COMPANY"); });
$("#stop-job-btn").addEventListener("click", async () => {
  if (!state.currentRun) return;
  try { await api(`/api/check-runs/${state.currentRun.id}/stop`, { method: "POST" }); toast("Đã gửi yêu cầu dừng", "success"); } catch {}
});
$("#modal-close").addEventListener("click", closeModal);
$("#modal-backdrop").addEventListener("click", (event) => { if (event.target === $("#modal-backdrop")) closeModal(); });
$("#account-search").addEventListener("input", renderAccounts);
$("#select-all-accounts").addEventListener("change", (event) => {
  filteredAccounts().forEach((account) => event.target.checked ? state.selectedAccounts.add(account.id) : state.selectedAccounts.delete(account.id));
  renderAccounts();
});

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-person-id],[data-edit-user],[data-check-group],[data-machine-id],[data-delete-machine],[data-view-account],[data-delete-account],[data-transfer-account],[data-status],[data-dashboard-filter],[data-close-modal],[data-modal-edit-user],[data-search-owner],[data-owner-id]");
  if (!target) return;
  if (target.dataset.personId) await selectUser(target.dataset.personId);
  else if (target.dataset.editUser) openUserForm(target.dataset.editUser);
  else if (target.dataset.checkGroup) { if (confirm("Check toàn bộ Leader và Member thuộc nhóm này?")) startCheck("LEADER_GROUP", target.dataset.checkGroup); }
  else if (target.dataset.machineId) { state.selectedMachineId = target.dataset.machineId; state.selectedAccounts.clear(); renderMachineTabs(); renderAccounts(); }
  else if (target.dataset.deleteMachine) await deleteMachine(target.dataset.deleteMachine);
  else if (target.dataset.viewAccount) showAccountDetail(target.dataset.viewAccount);
  else if (target.dataset.deleteAccount) await deleteAccount(target.dataset.deleteAccount);
  else if (target.dataset.transferAccount) await openTransferAccount(target.dataset.transferAccount);
  else if (target.dataset.status) { state.statusFilter = target.dataset.status; updateFilterChips(); renderAccounts(); }
  else if (target.dataset.dashboardFilter) await showAllScope(target.dataset.dashboardFilter);
  else if (target.hasAttribute("data-close-modal")) closeModal();
  else if (target.dataset.modalEditUser) openUserForm(target.dataset.modalEditUser);
  else if (target.dataset.searchOwner) { closeModal(); await selectUser(target.dataset.searchOwner); }
  else if (target.dataset.ownerId) { if (target.dataset.ownerId) await selectUser(target.dataset.ownerId); }
});

document.addEventListener("change", (event) => {
  if (!event.target.matches(".account-checkbox")) return;
  const id = event.target.dataset.accountId;
  if (event.target.checked) state.selectedAccounts.add(id); else state.selectedAccounts.delete(id);
  updateOwnerActions(state.users.find((user) => user.id === state.selectedOwnerId) || null);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModal();
});

init();
