const chatEl = document.getElementById("chat");
const appShellEl = document.getElementById("appShell");
const authScreenEl = document.getElementById("authScreen");
const modelSelect = document.getElementById("modelSelect");
const langSelect = document.getElementById("langSelect");
const userListEl = document.getElementById("userList");
const newUserBtn = document.getElementById("newUser");
const activeUserEl = document.getElementById("activeUser");
const progressPanelEl = document.getElementById("progressPanel");
const profileFormEl = document.getElementById("profileForm");
const profileGenderEl = document.getElementById("profileGender");
const profileBirthYearEl = document.getElementById("profileBirthYear");
const profileExperienceEl = document.getElementById("profileExperience");
const profileSubmitBtn = document.getElementById("profileSubmit");
const msgEl = document.getElementById("msg");
const sendBtn = document.getElementById("send");
const loginOpenBtn = document.getElementById("loginOpen");
const loginUsernameEl = document.getElementById("loginUsername");
const loginPasswordEl = document.getElementById("loginPassword");
const loginSubmitBtn = document.getElementById("loginSubmit");
const guestContinueBtn = document.getElementById("guestContinue");
const loginErrorEl = document.getElementById("loginError");
const accountMenuEl = document.getElementById("accountMenu");
const accountTriggerEl = document.getElementById("accountTrigger");
const accountDropdownEl = document.getElementById("accountDropdown");
const accountAvatarEl = document.getElementById("accountAvatar");
const accountNameEl = document.getElementById("accountName");
const accountRoleEl = document.getElementById("accountRole");
const accountInfoEl = document.getElementById("accountInfo");
const logoutBtn = document.getElementById("logoutBtn");
const chatViewBtn = document.getElementById("chatViewBtn");
const accountAdminViewBtn = document.getElementById("accountAdminViewBtn");
const salesTargetViewBtn = document.getElementById("salesTargetViewBtn");
const caseIdeaViewBtn = document.getElementById("caseIdeaViewBtn");
const accountAdminEl = document.getElementById("accountAdmin");
const accountTableEl = document.getElementById("accountTable");
const accountMetricsEl = document.getElementById("accountMetrics");
const accountDetailEl = document.getElementById("accountDetail");
const auditTableEl = document.getElementById("auditTable");
const auditPaginationEl = document.getElementById("auditPagination");
const accountAdminErrorEl = document.getElementById("accountAdminError");
const createAccountBtn = document.getElementById("createAccountBtn");
const toastEl = document.getElementById("toast");
const accountCreateModalEl = document.getElementById("accountCreateModal");
const accountCreateCloseBtn = document.getElementById("accountCreateClose");
const accountCreateCancelBtn = document.getElementById("accountCreateCancel");
const accountCreateSubmitBtn = document.getElementById("accountCreateSubmit");
const createUsernameEl = document.getElementById("createUsername");
const createDisplayNameEl = document.getElementById("createDisplayName");
const createPasswordEl = document.getElementById("createPassword");
const createRoleEl = document.getElementById("createRole");
const createAccountErrorEl = document.getElementById("createAccountError");
const conditionTemplateListEl = document.getElementById("conditionTemplateList");
const conditionTypeEl = document.getElementById("conditionType");
const conditionNameEl = document.getElementById("conditionName");
const conditionLogicEl = document.getElementById("conditionLogic");
const conditionDescriptionEl = document.getElementById("conditionDescription");
const saveConditionTemplateBtn = document.getElementById("saveConditionTemplateBtn");
const conditionViewBtn = document.getElementById("conditionViewBtn");
const conditionAdminEl = document.getElementById("conditionAdmin");
const salesTargetAdminEl = document.getElementById("salesTargetAdmin");
const salesTargetListEl = document.getElementById("salesTargetList");
const salesTargetNameEl = document.getElementById("salesTargetName");
const salesTargetDescriptionEl = document.getElementById("salesTargetDescription");
const salesTargetQuestionEl = document.getElementById("salesTargetQuestion");
const importSalesPromptBtn = document.getElementById("importSalesPromptBtn");
const salesTargetPromptFileEl = document.getElementById("salesTargetPromptFile");
const saveSalesTargetBtn = document.getElementById("saveSalesTargetBtn");
const cancelSalesTargetBtn = document.getElementById("cancelSalesTargetBtn");
const caseIdeaAdminEl = document.getElementById("caseIdeaAdmin");
const caseIdeaListEl = document.getElementById("caseIdeaList");
const caseIdeaNameEl = document.getElementById("caseIdeaName");
const caseIdeaIndicatorsEl = document.getElementById("caseIdeaIndicators");
const caseIdeaDescriptionEl = document.getElementById("caseIdeaDescription");
const saveCaseIdeaBtn = document.getElementById("saveCaseIdeaBtn");
const cancelCaseIdeaBtn = document.getElementById("cancelCaseIdeaBtn");
const conditionStep1El = document.getElementById("conditionStep1");
const conditionStep1Btn = document.getElementById("conditionStep1Btn");
const conditionStep2Btn = document.getElementById("conditionStep2Btn");
const conditionStep3Btn = document.getElementById("conditionStep3Btn");
const conditionStep3El = document.getElementById("conditionStep3");
const activeFlowFilterTypeEl = document.getElementById("activeFlowFilterType");
const activeFlowSearchEl = document.getElementById("activeFlowSearch");
const activeFlowListEl = document.getElementById("activeFlowList");

const conditionFilterTypeEl = document.getElementById("conditionFilterType");
const addConditionTypeBtn = document.getElementById("addConditionTypeBtn");

const conditionTypeModalEl = document.getElementById("conditionTypeModal");
const conditionTypeModalCloseBtn = document.getElementById("conditionTypeModalClose");
const conditionTypeCancelBtn =
  document.getElementById("conditionTypeCancel");

const conditionTypeSaveBtn =
  document.getElementById("conditionTypeSave");

const conditionTypeNameEl =
  document.getElementById("conditionTypeName");

const conditionTypeErrorEl =
  document.getElementById("conditionTypeError");

const conditionStep2El = document.getElementById("conditionStep2");
const confirmedConditionLibraryEl = document.getElementById("confirmedConditionLibrary");
const flowNameEl = document.getElementById("flowName");
const flowExpressionEl = document.getElementById("flowExpression");
const flowPromptTemplateEl = document.getElementById("flowPromptTemplate");
const flowNameCountEl = document.getElementById("flowNameCount");
const flowPromptCountEl = document.getElementById("flowPromptCount");
const saveConditionFlowBtn = document.getElementById("saveConditionFlow");
const conditionFlowListEl = document.getElementById("conditionFlowList");
const cancelFlowEditBtn = document.getElementById("cancelFlowEdit");
const flowSearchEl = document.getElementById("flowSearch");
const clearSelectedConditionsBtn = document.getElementById("clearSelectedConditions");

const openFlowModalBtn = document.getElementById("openFlowModalBtn");
const flowModalEl = document.getElementById("flowModal");
const flowModalCloseBtn = document.getElementById("flowModalClose");
const flowConditionSearchEl = document.getElementById("flowConditionSearch");
const addSelectedConditionBtn = document.getElementById("addSelectedConditionBtn");
const flowConditionKeywordEl = document.getElementById("flowConditionKeyword");

const conditionSearchEl = document.getElementById("conditionSearch");
const conditionPaginationEl = document.getElementById("conditionPagination");
const ACTIVE_USER_STORAGE_KEY = "salesDemoActiveUser";
const AUDIT_PAGE_SIZE = 3;

let users = [];
let currentUserId = null;
let currentAccount = null;
let guestMode = false;
let appStarted = false;
let accounts = [];
let accountAuditLogs = [];
let auditPage = 1;
let selectedAccountId = null;
let conditionTemplates = [];
let conditionFlows = [];
let conditionTypes = [];
let salesDiscoveryTargets = [];
let caseIdeas = [];
let editingSalesTargetId = null;
let editingCaseIdeaId = null;
let editingConditionFlowId = null;
let selectedConditions = [];
let nextOperator = "AND";
let editingConditionTemplateId = null;
let checkingDemoFlowId = null;
let demoCheckResults = {};
let activeFlowCheckDates = {};
let conditionPage = 1;
const CONDITION_PAGE_SIZE = 7;
let currentView = "chat";
let lastRenderedHistorySignature = "";
let isChatStreaming = false;

const TARGET_LABELS = {
  investment_experience: "Thâm niên đầu tư",
  nav: "NAV",
  portfolio_cost: "Danh mục + giá vốn",
  decision_basis: "Cơ sở ra quyết định",
};

const TARGET_ORDER = [
  "investment_experience",
  "nav",
  "portfolio_cost",
  "decision_basis",
];

const MOJIBAKE_PATTERN =
  /(Ã|Ä|Æ|Ð|ð|áº|á»|Â|â[€œ€™†€¦„‡˜—–‹›“”•]|�|[\u0080-\u009f])/;

const CP1252_BYTES = new Map([
  [0x20ac, 0x80],
  [0x201a, 0x82],
  [0x0192, 0x83],
  [0x201e, 0x84],
  [0x2026, 0x85],
  [0x2020, 0x86],
  [0x2021, 0x87],
  [0x02c6, 0x88],
  [0x2030, 0x89],
  [0x0160, 0x8a],
  [0x2039, 0x8b],
  [0x0152, 0x8c],
  [0x017d, 0x8e],
  [0x2018, 0x91],
  [0x2019, 0x92],
  [0x201c, 0x93],
  [0x201d, 0x94],
  [0x2022, 0x95],
  [0x2013, 0x96],
  [0x2014, 0x97],
  [0x02dc, 0x98],
  [0x2122, 0x99],
  [0x0161, 0x9a],
  [0x203a, 0x9b],
  [0x0153, 0x9c],
  [0x017e, 0x9e],
  [0x0178, 0x9f],
]);

function mojibakeScore(value) {
  return (String(value || "").match(new RegExp(MOJIBAKE_PATTERN.source, "g")) || []).length;
}

function encodeMojibakeBytes(value) {
  const bytes = [];
  for (const char of String(value || "")) {
    const code = char.codePointAt(0);
    if (code <= 0xff) {
      bytes.push(code);
    } else if (CP1252_BYTES.has(code)) {
      bytes.push(CP1252_BYTES.get(code));
    } else {
      return null;
    }
  }
  return new Uint8Array(bytes);
}

function repairDisplayText(value) {
  let text = String(value ?? "");
  if (!MOJIBAKE_PATTERN.test(text)) return text;

  for (let i = 0; i < 3; i += 1) {
    const before = mojibakeScore(text);
    const bytes = encodeMojibakeBytes(text);
    if (!bytes) break;
    let repaired = text;
    try {
      repaired = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      break;
    }
    if (mojibakeScore(repaired) >= before) break;
    text = repaired;
  }
  return text;
}

/* =========================
   Auth Helpers
========================= */

function roleLabel(role) {
  const labels = {
    super_admin: "Super Admin",
    admin: "Admin",
    member: "Member",
  };
  return labels[role] || "Guest";
}

function accountInitials(account) {
  if (!account) return "?";
  if (account.role === "super_admin") return "SA";
  if (account.role === "admin") return "AD";
  return "MB";
}

function canUseChat() {
  return Boolean(currentAccount) || guestMode;
}

function canViewProgress() {
  return ["admin", "super_admin"].includes(currentAccount?.role);
}

function setChatAccessState() {
  const allowed = canUseChat();
  msgEl.disabled = !allowed || isChatStreaming;
  sendBtn.disabled = !allowed || isChatStreaming;
  newUserBtn.disabled = !allowed;
  profileSubmitBtn.disabled = !allowed;
  document.body.classList.toggle("chat-locked", !allowed);
  msgEl.placeholder = isChatStreaming
    ? "Đang xử lý câu hỏi..."
    : allowed
      ? "Nhap cau hoi..."
      : "Tài khoản này chưa có quyền sử dụng chatbot";
}

function renderAuthState() {
  const loggedIn = Boolean(currentAccount);
  loginOpenBtn.hidden = loggedIn;
  loginOpenBtn.classList.toggle("hidden", loggedIn);
  accountMenuEl.hidden = !loggedIn;
  accountMenuEl.classList.toggle("hidden", !loggedIn);

  if (!currentAccount) {
    closeAccountDropdown();
    setChatAccessState();
    return;
  }

  accountAvatarEl.textContent = accountInitials(currentAccount);
  accountNameEl.textContent = currentAccount.display_name || currentAccount.username;
  accountRoleEl.textContent = roleLabel(currentAccount.role);
  accountInfoEl.textContent = `${currentAccount.username} • ${roleLabel(currentAccount.role)}`;
  const canManageAccounts = currentAccount.role === "super_admin";
  const canManageConditions =
    currentAccount?.role === "super_admin";
  const canManageSalesTargets = ["admin", "super_admin"].includes(currentAccount?.role);
  const canManageCaseIdeas = ["admin", "super_admin"].includes(currentAccount?.role);

  if (conditionViewBtn) {
    conditionViewBtn.hidden = !canManageConditions;
    conditionViewBtn.classList.toggle(
      "hidden",
      !canManageConditions
    );
  }
  if (salesTargetViewBtn) {
    salesTargetViewBtn.hidden = !canManageSalesTargets;
    salesTargetViewBtn.classList.toggle(
      "hidden",
      !canManageSalesTargets
    );
  }
  if (caseIdeaViewBtn) {
    caseIdeaViewBtn.hidden = !canManageCaseIdeas;
    caseIdeaViewBtn.classList.toggle(
      "hidden",
      !canManageCaseIdeas
    );
  }
  accountAdminViewBtn.hidden = !canManageAccounts;
  accountAdminViewBtn.classList.toggle("hidden", !canManageAccounts);
  if (!canManageAccounts && currentView === "accounts") showChatView();
  if (!canManageConditions && currentView === "conditions") showChatView();
  if (!canManageSalesTargets && currentView === "sales-targets") showChatView();
  if (!canManageCaseIdeas && currentView === "case-ideas") showChatView();
  setChatAccessState();
}

function showLoginError(message) {
  loginErrorEl.textContent = message;
  loginErrorEl.hidden = false;
  loginErrorEl.classList.remove("hidden");
}

function hideLoginError() {
  loginErrorEl.textContent = "";
  loginErrorEl.hidden = true;
  loginErrorEl.classList.add("hidden");
}

function showAuthScreen() {
  hideLoginError();
  authScreenEl.hidden = false;
  authScreenEl.classList.remove("hidden");
  appShellEl.hidden = true;
  appShellEl.classList.add("hidden");
  loginUsernameEl.focus();
}

function hideAuthScreen() {
  authScreenEl.hidden = true;
  authScreenEl.classList.add("hidden");
  appShellEl.hidden = false;
  appShellEl.classList.remove("hidden");
  loginPasswordEl.value = "";
}

function openLoginModal() {
  guestMode = false;
  showAuthScreen();
}

function closeLoginModal() {
  hideAuthScreen();
}

function toggleAccountDropdown() {
  const willOpen = accountDropdownEl.hidden;
  accountDropdownEl.hidden = !willOpen;
  accountDropdownEl.classList.toggle("hidden", !willOpen);
}

function closeAccountDropdown() {
  accountDropdownEl.hidden = true;
  accountDropdownEl.classList.add("hidden");
}

async function enterApp() {
  hideAuthScreen();
  renderAuthState();
  chatEl.innerHTML = "";
  msgEl.value = "";

  if (!appStarted) {
    await loadModels();
    await loadUsers();
    renderUsers();
    appStarted = true;
  }

  if (currentUserId) {
    await selectUser(currentUserId);
  } else {
    activeUserEl.textContent = "Nobody";
    hideProfileForm();
    addEmptyState();
  }
}

async function restoreAuthSession() {
  try {
    const res = await fetch("/auth/me", { credentials: "same-origin" });
    if (!res.ok) throw new Error("Invalid session");
    const data = await res.json();
    currentAccount = data?.account || null;
  } catch {
    currentAccount = null;
  }

  renderAuthState();
}

async function continueAsGuest() {
  currentAccount = null;
  guestMode = true;
  await enterApp();
}

async function login() {
  const username = loginUsernameEl.value.trim();
  const password = loginPasswordEl.value;

  if (!username || !password) {
    showLoginError("Vui lòng nhập tài khoản và mật khẩu.");
    return;
  }

  loginSubmitBtn.disabled = true;
  loginSubmitBtn.textContent = "Đang đăng nhập...";
  hideLoginError();

  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ username, password }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || "Đăng nhập thất bại.");

    currentAccount = data.account || null;
    guestMode = false;
    await enterApp();
  } catch (err) {
    showLoginError(err.message || "Không thể đăng nhập.");
  } finally {
    loginSubmitBtn.disabled = false;
    loginSubmitBtn.textContent = "Đăng nhập";
  }
}

async function logout() {
  try {
    await fetch("/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });
  } catch {
    console.warn("Cannot revoke auth session");
  }

  currentAccount = null;
  guestMode = false;
  appStarted = false;
  closeAccountDropdown();
  showAuthScreen();
}

/* =========================
   Account Admin
========================= */

function showAdminError(message) {
  accountAdminErrorEl.textContent = message;
  accountAdminErrorEl.hidden = false;
  accountAdminErrorEl.classList.remove("hidden");
}

function hideAdminError() {
  accountAdminErrorEl.textContent = "";
  accountAdminErrorEl.hidden = true;
  accountAdminErrorEl.classList.add("hidden");
}

function showToast(message, type = "success") {
  toastEl.textContent = message;
  toastEl.className = `toast ${type}`;
  toastEl.hidden = false;
  toastEl.getBoundingClientRect();
  window.requestAnimationFrame(() => {
    toastEl.classList.add("show");
  });
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toastEl.classList.remove("show");
    window.setTimeout(() => {
      toastEl.hidden = true;
      toastEl.classList.add("hidden");
    }, 240);
  }, 2600);
}

function showPermissionDenied() {
  showToast("Tài khoản này chưa có quyền sử dụng chatbot.", "error");
}

function showCreateAccountError(message) {
  createAccountErrorEl.textContent = message;
  createAccountErrorEl.hidden = false;
  createAccountErrorEl.classList.remove("hidden");
}

function hideCreateAccountError() {
  createAccountErrorEl.textContent = "";
  createAccountErrorEl.hidden = true;
  createAccountErrorEl.classList.add("hidden");
}

function openCreateAccountModal() {
  hideCreateAccountError();
  createUsernameEl.value = "";
  createDisplayNameEl.value = "";
  createPasswordEl.value = "";
  createRoleEl.value = "admin";
  accountCreateSubmitBtn.disabled = false;
  accountCreateSubmitBtn.textContent = "Tạo tài khoản";
  accountCreateModalEl.hidden = false;
  accountCreateModalEl.classList.remove("hidden");
  createUsernameEl.focus();
}

function closeCreateAccountModal() {
  accountCreateModalEl.hidden = true;
  accountCreateModalEl.classList.add("hidden");
  createPasswordEl.value = "";
}

function setMainView(view) {
  currentView = view;

  const isAccounts = view === "accounts";
  const isConditions = view === "conditions";
  const isSalesTargets = view === "sales-targets";
  const isCaseIdeas = view === "case-ideas";
  const isAdminView = isAccounts || isConditions || isSalesTargets || isCaseIdeas;

  const sidebarEl = document.querySelector(".sidebar");
  const composerEl = document.querySelector(".composer");

  accountAdminEl.hidden = !isAccounts;
  accountAdminEl.classList.toggle("hidden", !isAccounts);

  if (conditionAdminEl) {
    conditionAdminEl.hidden = !isConditions;
    conditionAdminEl.classList.toggle("hidden", !isConditions);
  }

  if (salesTargetAdminEl) {
    salesTargetAdminEl.hidden = !isSalesTargets;
    salesTargetAdminEl.classList.toggle("hidden", !isSalesTargets);
  }

  if (caseIdeaAdminEl) {
    caseIdeaAdminEl.hidden = !isCaseIdeas;
    caseIdeaAdminEl.classList.toggle("hidden", !isCaseIdeas);
  }

  const hideProgress = isAdminView || !canViewProgress();
  progressPanelEl.hidden = hideProgress;
  progressPanelEl.classList.toggle("hidden", hideProgress);

  chatEl.hidden = isAdminView;
  chatEl.classList.toggle("hidden", isAdminView);

  if (composerEl) {
    composerEl.hidden = isAdminView;
    composerEl.classList.toggle("hidden", isAdminView);
  }

  if (sidebarEl) {
    sidebarEl.hidden = isAdminView;
    sidebarEl.classList.toggle("hidden", isAdminView);
  }

  if (appShellEl) {
    appShellEl.classList.toggle("admin-fullscreen", isAdminView);
  }

  closeAccountDropdown();

  if (isConditions) {
    loadConditionTemplates().then(loadConditionFlows);
  }

  if (isSalesTargets) {
    loadSalesTargets();
  }

  if (isCaseIdeas) {
    loadCaseIdeas();
  }
}

function showConditionStep(step) {
  const isStep1 = step === 1;
  const isStep2 = step === 2;
  const isStep3 = step === 3;

  if (conditionStep1El) {
    conditionStep1El.hidden = !isStep1;
    conditionStep1El.classList.toggle("hidden", !isStep1);
  }

  if (conditionStep2El) {
    conditionStep2El.hidden = !isStep2;
    conditionStep2El.classList.toggle("hidden", !isStep2);
  }

  if (conditionStep3El) {
    conditionStep3El.hidden = !isStep3;
    conditionStep3El.classList.toggle("hidden", !isStep3);
  }

  conditionStep1Btn?.classList.toggle("active", isStep1);
  conditionStep2Btn?.classList.toggle("active", isStep2);
  conditionStep3Btn?.classList.toggle("active", isStep3);

  if (isStep2 || isStep3) {
    loadConditionTemplates().then(loadConditionFlows);
  }

  if (isStep3) {
    renderActiveFlows();
  }
}

function localDateString(date = new Date()) {
  return date.toLocaleDateString("en-CA");
}

function getActiveFlowCheckDate(flowId) {
  const key = String(flowId);

  if (!activeFlowCheckDates[key]) {
    activeFlowCheckDates[key] = localDateString();
  }

  return activeFlowCheckDates[key];
}

function setActiveFlowCheckDate(flowId, value) {
  activeFlowCheckDates[String(flowId)] = value || localDateString();
}

async function showChatView() {
  setMainView("chat");
  if (!currentUserId) return;

  const messages = await loadChatHistory(currentUserId);
  renderChatHistory(messages);
  await refreshProgress(currentUserId);
}

async function showAccountAdminView() {
  if (currentAccount?.role !== "super_admin") return;
  hideProfileForm();
  setMainView("accounts");
  await loadAccounts();
}

async function showSalesTargetAdminView() {
  if (!["admin", "super_admin"].includes(currentAccount?.role)) return;
  hideProfileForm();
  setMainView("sales-targets");
  await loadSalesTargets();
}

function resetSalesTargetForm() {
  editingSalesTargetId = null;
  if (salesTargetNameEl) salesTargetNameEl.value = "";
  if (salesTargetDescriptionEl) salesTargetDescriptionEl.value = "";
  if (salesTargetQuestionEl) salesTargetQuestionEl.value = "";
  if (salesTargetPromptFileEl) salesTargetPromptFileEl.value = "";
  if (saveSalesTargetBtn) saveSalesTargetBtn.textContent = "Lưu target";
}

function openSalesPromptFilePicker() {
  salesTargetPromptFileEl?.click();
}

function importSalesPromptFromFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;

  const fileName = (file.name || "").toLowerCase();
  const isTextFile = file.type === "text/plain" || fileName.endsWith(".txt");

  if (!isTextFile) {
    showToast("Chỉ hỗ trợ file .txt", "error");
    event.target.value = "";
    return;
  }

  if (file.size > 300 * 1024) {
    showToast("File prompt quá lớn, tối đa 300KB", "error");
    event.target.value = "";
    return;
  }

  if (salesTargetQuestionEl?.value.trim()) {
    const ok = confirm("Prompt hiện tại sẽ bị thay bằng nội dung file .txt. Tiếp tục?");
    if (!ok) {
      event.target.value = "";
      return;
    }
  }

  const reader = new FileReader();
  reader.onload = () => {
    salesTargetQuestionEl.value = String(reader.result || "").trim();
    showToast("Đã nạp prompt từ file .txt");
    event.target.value = "";
  };
  reader.onerror = () => {
    showToast("Không đọc được file prompt", "error");
    event.target.value = "";
  };
  reader.readAsText(file, "UTF-8");
}


async function loadSalesTargets() {
  if (!salesTargetListEl) return;

  try {
    const res = await fetch("/sales-discovery/targets", {
      credentials: "same-origin",
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) throw new Error(data?.detail || "Cannot load targets");

    salesDiscoveryTargets = data.targets || [];
    renderSalesTargets();
  } catch {
    salesTargetListEl.innerHTML = `<div class="empty-users">Không tải được danh sách target.</div>`;
  }
}

function renderSalesTargets() {
  if (!salesTargetListEl) return;

  if (!salesDiscoveryTargets.length) {
    salesTargetListEl.innerHTML = `<div class="empty-users">Chưa có target khai thác.</div>`;
    return;
  }

  salesTargetListEl.innerHTML = salesDiscoveryTargets.map((target, index) => {
    const confirmed = target.status === "confirmed" && Boolean(target.active);
    return `
      <div class="sales-target-row">
        <div>
          <strong>${escapeHtml(target.name || target.target_key)}</strong>
          <small>${escapeHtml(target.target_key || "-")}</small>
        </div>
        <div>${escapeHtml(target.description || "-")}</div>
        <div>${escapeHtml(target.suggested_question || "-")}</div>
        <div class="condition-actions sales-target-actions">
          <button type="button" title="Lên" ${index === 0 ? "disabled" : ""} onclick="reorderSalesTarget(${target.id}, 'up')">↑</button>
          <button type="button" title="Xuống" ${index === salesDiscoveryTargets.length - 1 ? "disabled" : ""} onclick="reorderSalesTarget(${target.id}, 'down')">↓</button>
          <button type="button" title="Sửa" onclick="editSalesTarget(${target.id})">✎</button>
          <button
            type="button"
            class="${confirmed ? "flow-confirmed" : "flow-unconfirmed"}"
            title="${confirmed ? "Đã bật" : "Chờ bật"}"
            onclick="confirmSalesTarget(${target.id})"
          >✓</button>
          <button type="button" title="Xóa" onclick="deleteSalesTarget(${target.id})">×</button>
        </div>
      </div>
    `;
  }).join("");
}

function editSalesTarget(id) {
  const target = salesDiscoveryTargets.find((item) => Number(item.id) === Number(id));
  if (!target) return;

  editingSalesTargetId = target.id;
  salesTargetNameEl.value = target.name || "";
  salesTargetDescriptionEl.value = target.description || "";
  salesTargetQuestionEl.value = target.suggested_question || "";
  saveSalesTargetBtn.textContent = "Cập nhật target";
}

async function saveSalesTarget() {
  const editingTarget = salesDiscoveryTargets.find(
    (item) => Number(item.id) === Number(editingSalesTargetId)
  );
  const payload = {
    target_key: editingTarget?.target_key || "",
    name: salesTargetNameEl.value.trim(),
    description: salesTargetDescriptionEl.value.trim(),
    suggested_question: salesTargetQuestionEl.value.trim(),
    recognizer_key: editingTarget?.recognizer_key || "",
    status: editingTarget?.status || "waiting",
    active: Boolean(editingTarget?.active),
  };

  if (!payload.name) {
    showToast("Vui lòng nhập tên target", "error");
    return;
  }

  saveSalesTargetBtn.disabled = true;

  try {
    const url = editingSalesTargetId
      ? `/sales-discovery/targets/${editingSalesTargetId}`
      : "/sales-discovery/targets";
    const method = editingSalesTargetId ? "PATCH" : "POST";
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) throw new Error(data?.detail || "Lưu target thất bại");

    resetSalesTargetForm();
    await loadSalesTargets();
    showToast("Đã lưu target khai thác");
  } catch (err) {
    showToast(err.message || "Lưu target thất bại", "error");
  } finally {
    saveSalesTargetBtn.disabled = false;
  }
}

async function confirmSalesTarget(id) {
  const target = salesDiscoveryTargets.find((item) => Number(item.id) === Number(id));
  if (!target) return;

  const payload = {
    target_key: target.target_key || "",
    name: target.name || "",
    description: target.description || "",
    suggested_question: target.suggested_question || "",
    recognizer_key: target.recognizer_key || "",
    status: "confirmed",
    active: true,
  };

  const res = await fetch(`/sales-discovery/targets/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    showToast("Bật target thất bại", "error");
    return;
  }

  await loadSalesTargets();
  showToast("Đã bật target");
}

async function deleteSalesTarget(id) {
  if (!confirm("Xóa target khai thác này?")) return;

  const res = await fetch(`/sales-discovery/targets/${id}`, {
    method: "DELETE",
    credentials: "same-origin",
  });

  if (!res.ok) {
    showToast("Xóa target thất bại", "error");
    return;
  }

  if (Number(editingSalesTargetId) === Number(id)) {
    resetSalesTargetForm();
  }
  await loadSalesTargets();
  showToast("Đã xóa target");
}

async function reorderSalesTarget(id, direction) {
  const res = await fetch(`/sales-discovery/targets/${id}/reorder`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ direction }),
  });

  if (!res.ok) {
    showToast("Sắp xếp target thất bại", "error");
    return;
  }

  await loadSalesTargets();
}

async function showCaseIdeaAdminView() {
  if (!["admin", "super_admin"].includes(currentAccount?.role)) return;
  hideProfileForm();
  setMainView("case-ideas");
  await loadCaseIdeas();
}

function resetCaseIdeaForm() {
  editingCaseIdeaId = null;
  if (caseIdeaNameEl) caseIdeaNameEl.value = "";
  if (caseIdeaIndicatorsEl) caseIdeaIndicatorsEl.value = "";
  if (caseIdeaDescriptionEl) caseIdeaDescriptionEl.value = "";
  if (saveCaseIdeaBtn) saveCaseIdeaBtn.textContent = "Lưu case";
}

async function loadCaseIdeas() {
  if (!caseIdeaListEl) return;

  try {
    const res = await fetch("/case-ideas", {
      credentials: "same-origin",
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) throw new Error(data?.detail || "Không tải được danh sách case");

    caseIdeas = data.cases || [];
    renderCaseIdeas();
  } catch (err) {
    caseIdeaListEl.innerHTML = `<div class="empty-users">${escapeHtml(err.message || "Không tải được danh sách case.")}</div>`;
  }
}

function renderCaseIdeas() {
  if (!caseIdeaListEl) return;

  if (!caseIdeas.length) {
    caseIdeaListEl.innerHTML = `<div class="empty-users">Chưa có case ý tưởng.</div>`;
    return;
  }

  caseIdeaListEl.innerHTML = caseIdeas.map((item) => {
    const supported = item.status === "supported";
    return `
      <div class="case-idea-row">
        <div>
          <strong>${escapeHtml(item.name || "-")}</strong>
          <small>#${escapeHtml(item.id || "-")}</small>
        </div>
        <div>${escapeHtml(item.indicators || "-")}</div>
        <div>${escapeHtml(item.description || "-")}</div>
        <div class="condition-actions case-idea-actions">
          <button type="button" title="Sửa" onclick="editCaseIdea(${item.id})">✎</button>
          <button
            type="button"
            class="${supported ? "flow-confirmed" : "flow-unconfirmed"}"
            title="${supported ? "Dev đã hỗ trợ" : "Chờ dev hỗ trợ"}"
            onclick="confirmCaseIdea(${item.id})"
            ${supported ? "disabled" : ""}
          >✓</button>
          <button type="button" title="Xóa" onclick="deleteCaseIdea(${item.id})">×</button>
        </div>
      </div>
    `;
  }).join("");
}

function editCaseIdea(id) {
  const item = caseIdeas.find((caseIdea) => Number(caseIdea.id) === Number(id));
  if (!item) return;

  editingCaseIdeaId = item.id;
  caseIdeaNameEl.value = item.name || "";
  caseIdeaIndicatorsEl.value = item.indicators || "";
  caseIdeaDescriptionEl.value = item.description || "";
  saveCaseIdeaBtn.textContent = "Cập nhật case";
}

async function saveCaseIdea() {
  const payload = {
    name: caseIdeaNameEl.value.trim(),
    indicators: caseIdeaIndicatorsEl.value.trim(),
    description: caseIdeaDescriptionEl.value.trim(),
  };

  if (!payload.name) {
    showToast("Vui lòng nhập tên case", "error");
    return;
  }

  saveCaseIdeaBtn.disabled = true;

  try {
    const url = editingCaseIdeaId
      ? `/case-ideas/${editingCaseIdeaId}`
      : "/case-ideas";
    const method = editingCaseIdeaId ? "PATCH" : "POST";
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) throw new Error(data?.detail || "Lưu case thất bại");

    resetCaseIdeaForm();
    await loadCaseIdeas();
    showToast("Đã lưu case ý tưởng");
  } catch (err) {
    showToast(err.message || "Lưu case thất bại", "error");
  } finally {
    saveCaseIdeaBtn.disabled = false;
  }
}

async function confirmCaseIdea(id) {
  const ok = confirm("Đánh dấu case này là dev đã hỗ trợ?");
  if (!ok) return;

  const res = await fetch(`/case-ideas/${id}/confirm`, {
    method: "POST",
    credentials: "same-origin",
  });

  if (!res.ok) {
    showToast("Xác nhận case thất bại", "error");
    return;
  }

  await loadCaseIdeas();
  showToast("Đã đánh dấu case được hỗ trợ");
}

async function deleteCaseIdea(id) {
  if (!confirm("Xóa case ý tưởng này?")) return;

  const res = await fetch(`/case-ideas/${id}`, {
    method: "DELETE",
    credentials: "same-origin",
  });

  if (!res.ok) {
    showToast("Xóa case thất bại", "error");
    return;
  }

  if (Number(editingCaseIdeaId) === Number(id)) {
    resetCaseIdeaForm();
  }
  await loadCaseIdeas();
  showToast("Đã xóa case");
}

function escapeHtml(value) {
  return repairDisplayText(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function accountCounts() {
  return {
    total: accounts.length,
    admin: accounts.filter((account) => account.role === "admin").length,
    member: accounts.filter((account) => account.role === "member").length,
    locked: accounts.filter((account) => account.status === "locked").length,
  };
}

function renderAccountMetrics() {
  const counts = accountCounts();
  const metrics = [
    ["Tổng tài khoản", counts.total, "👥"],
    ["Admin", counts.admin, "🛡"],
    ["Member", counts.member, "👤"],
    ["Đang khóa", counts.locked, "🔒"],
  ];

  accountMetricsEl.innerHTML = "";
  metrics.forEach(([label, value, icon]) => {
    const card = document.createElement("div");
    card.className = "metric-card";
    card.innerHTML = `<span class="metric-icon">${icon}</span><span><small></small><strong></strong></span>`;
    card.querySelector("small").textContent = label;
    card.querySelector("strong").textContent = value;
    accountMetricsEl.appendChild(card);
  });
}

function selectedAccount() {
  return accounts.find((account) => account.id === selectedAccountId) || accounts[0] || null;
}

function renderAccounts() {
  renderAccountMetrics();
  accountTableEl.innerHTML = "";

  const header = document.createElement("div");
  header.className = "account-row head";
  ["#", "Tên đăng nhập", "Vai trò", "Trạng thái", "Lần đăng nhập", "Hành động"].forEach((text) => {
    const cell = document.createElement("div");
    cell.textContent = text;
    header.appendChild(cell);
  });
  accountTableEl.appendChild(header);

  if (!accounts.length) {
    const empty = document.createElement("div");
    empty.className = "account-empty";
    empty.textContent = "Chưa có tài khoản.";
    accountTableEl.appendChild(empty);
    renderAccountDetail(null);
    return;
  }

  if (!selectedAccountId || !accounts.some((account) => account.id === selectedAccountId)) {
    selectedAccountId = accounts[0].id;
  }

  accounts.forEach((account, index) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `account-row account-row-button ${account.id === selectedAccountId ? "selected" : ""}`;
    row.addEventListener("click", () => {
      selectedAccountId = account.id;
      renderAccounts();
    });

    const cells = [
      String(index + 1),
      account.username,
      roleLabel(account.role),
      account.status,
      account.last_login_at || "Chưa đăng nhập",
    ];

    cells.forEach((text, cellIndex) => {
      const cell = document.createElement("div");
      if (cellIndex === 2) {
        cell.innerHTML = `<span class="badge ${account.role}">${text}</span>`;
      } else if (cellIndex === 3) {
        cell.innerHTML = `<span class="badge ${account.status}">${text}</span>`;
      } else {
        cell.textContent = text;
      }
      row.appendChild(cell);
    });

    const action = document.createElement("div");
    action.className = "row-menu";
    action.textContent = "⋮";
    row.appendChild(action);
    accountTableEl.appendChild(row);
  });

  renderAccountDetail(selectedAccount());
}

async function renderAccountDetail(account) {
  if (!account) {
    accountDetailEl.innerHTML = `<div class="account-empty">Chọn một tài khoản để xem chi tiết.</div>`;
    return;
  }

  const isRoot = account.role === "super_admin";
  accountDetailEl.innerHTML = `
    <div class="detail-profile">
      <div class="detail-avatar">${accountInitials(account)}</div>
      <div>
        <strong>${account.username}</strong>
        <span>${roleLabel(account.role)}</span>
      </div>
    </div>
    <div class="detail-grid">
      <label class="login-field">
        <span>Tên đăng nhập</span>
        <input id="detailUsername" value="${account.username}" disabled />
      </label>
      <label class="login-field">
        <span>Vai trò</span>
        <select id="detailRole" ${isRoot ? "disabled" : ""}>
          <option value="admin">Admin</option>
          <option value="member">Member</option>
        </select>
      </label>
    </div>
    <div class="status-line">
      <span>Trạng thái</span>
      <label class="switch-line">
        <input id="detailStatus" type="checkbox" ${account.status === "active" ? "checked" : ""} ${isRoot ? "disabled" : ""} />
        <span>Active</span>
      </label>
    </div>
    <div class="detail-actions">
      <button id="detailDelete" class="danger" type="button" ${isRoot ? "disabled" : ""}>Xóa</button>
      <button id="detailReset" type="button" ${isRoot ? "disabled" : ""}>Reset mật khẩu</button>
      <button id="detailSave" class="primary" type="button" ${isRoot ? "disabled" : ""}>Lưu thay đổi</button>
    </div>
  `;

  const roleSelect = document.getElementById("detailRole");
  if (roleSelect && !isRoot) roleSelect.value = account.role;

  document.getElementById("detailReset")?.addEventListener("click", () => resetAccountPassword(account));
  document.getElementById("detailDelete")?.addEventListener("click", () => deleteAccount(account));
  document.getElementById("detailSave")?.addEventListener("click", () => {
    const nextRole = document.getElementById("detailRole")?.value;
    const nextStatus = document.getElementById("detailStatus")?.checked ? "active" : "locked";
    saveAccountDetail(account.id, {role: nextRole, status: nextStatus});
  });
}

function renderAuditLogs() {
  auditTableEl.innerHTML = "";
  auditPaginationEl.innerHTML = "";

  const header = document.createElement("div");
  header.className = "audit-row head";
  ["Thời gian", "Người thực hiện", "Hành động", "Đối tượng", "Chi tiết"].forEach((text) => {
    const cell = document.createElement("div");
    cell.textContent = text;
    header.appendChild(cell);
  });
  auditTableEl.appendChild(header);

  if (!accountAuditLogs.length) {
    const empty = document.createElement("div");
    empty.className = "account-empty";
    empty.textContent = "Chưa có nhật ký thao tác.";
    auditTableEl.appendChild(empty);
    return;
  }

  const totalPages = Math.max(1, Math.ceil(accountAuditLogs.length / AUDIT_PAGE_SIZE));
  auditPage = Math.min(Math.max(1, auditPage), totalPages);
  const startIndex = (auditPage - 1) * AUDIT_PAGE_SIZE;
  const pageLogs = accountAuditLogs.slice(startIndex, startIndex + AUDIT_PAGE_SIZE);

  pageLogs.forEach((log) => {
    const row = document.createElement("div");
    row.className = "audit-row";
    const detail = log.detail_json || "";
    [log.created_at, log.actor_username, log.action, log.target_username, detail].forEach((text) => {
      const cell = document.createElement("div");
      cell.textContent = text || "-";
      row.appendChild(cell);
    });
    auditTableEl.appendChild(row);
  });

  if (totalPages > 1) {
    auditPaginationEl.innerHTML = `
      <span>Trang ${auditPage}/${totalPages}</span>
      <button type="button" id="auditPrev" ${auditPage === 1 ? "disabled" : ""}>Trước</button>
      <button type="button" id="auditNext" ${auditPage === totalPages ? "disabled" : ""}>Sau</button>
    `;
    document.getElementById("auditPrev")?.addEventListener("click", () => {
      auditPage -= 1;
      renderAuditLogs();
    });
    document.getElementById("auditNext")?.addEventListener("click", () => {
      auditPage += 1;
      renderAuditLogs();
    });
  }
}

async function loadAuditLogs() {
  try {
    const res = await fetch("/accounts/audit-logs", { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    accountAuditLogs = Array.isArray(data?.logs) ? data.logs : [];
    auditPage = 1;
  } catch {
    accountAuditLogs = [];
    auditPage = 1;
  }
  renderAuditLogs();
}

async function loadAccounts() {
  accountTableEl.innerHTML = `<div class="account-empty">Đang tải tài khoản...</div>`;
  try {
    const res = await fetch("/accounts", { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || "Không tải được danh sách tài khoản.");
    accounts = Array.isArray(data?.accounts) ? data.accounts : [];
    renderAccounts();
    await loadAuditLogs();
  } catch (err) {
    accountTableEl.innerHTML = `<div class="account-empty">${err.message || "Không tải được tài khoản."}</div>`;
  }
}

async function createAccount() {
  const username = createUsernameEl.value.trim();
  const displayName = createDisplayNameEl.value.trim();
  const password = createPasswordEl.value;
  const role = createRoleEl.value;

  if (!username) {
    showCreateAccountError("Vui lòng nhập tên đăng nhập.");
    createUsernameEl.focus();
    return;
  }

  if (!displayName) {
    showCreateAccountError("Vui lòng nhập tên hiển thị.");
    createDisplayNameEl.focus();
    return;
  }

  if (password.length < 8) {
    showCreateAccountError("Mật khẩu tạm thời cần tối thiểu 8 ký tự.");
    createPasswordEl.focus();
    return;
  }

  hideAdminError();
  hideCreateAccountError();
  accountCreateSubmitBtn.disabled = true;
  accountCreateSubmitBtn.textContent = "Đang tạo...";

  try {
    const res = await fetch("/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        username,
        display_name: displayName,
        password,
        role,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || "Không tạo được tài khoản.");
    selectedAccountId = data?.account?.id || selectedAccountId;
    closeCreateAccountModal();
    await loadAccounts();
    showToast("Đã tạo tài khoản mới.");
  } catch (err) {
    showCreateAccountError(err.message || "Không tạo được tài khoản.");
  } finally {
    accountCreateSubmitBtn.disabled = false;
    accountCreateSubmitBtn.textContent = "Tạo tài khoản";
  }
}

async function updateAccount(accountId, patch) {
  try {
    const res = await fetch(`/accounts/${accountId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(patch),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || "Không cập nhật được tài khoản.");
    await loadAccounts();
  } catch (err) {
    window.alert(err.message || "Không cập nhật được tài khoản.");
  }
}

async function resetAccountPassword(account) {
  const password = window.prompt(`Nhập mật khẩu mới cho ${account.username}:`);
  if (!password) return;

  try {
    const res = await fetch(`/accounts/${account.id}/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || "Không reset được mật khẩu.");
    window.alert("Đã reset mật khẩu.");
    await loadAccounts();
  } catch (err) {
    window.alert(err.message || "Không reset được mật khẩu.");
  }
}

async function deleteAccount(account) {
  const ok = window.confirm(`Xóa tài khoản ${account.username}?`);
  if (!ok) return;

  try {
    const res = await fetch(`/accounts/${account.id}`, {
      method: "DELETE",
      credentials: "same-origin",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || "Không xóa được tài khoản.");
    await loadAccounts();
  } catch (err) {
    window.alert(err.message || "Không xóa được tài khoản.");
  }
}

/* =========================
   UI Helpers
========================= */

function addBubble(text, cls) {
  const div = document.createElement("div");
  div.className = `bubble ${cls}`;
  div.textContent = repairDisplayText(text);
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

function addStartPrompt() {
  if (!currentUserId) {
    addEmptyState();
    return;
  }

  const div = document.createElement("div");
  div.className = "bubble ai start-card";

  const text = document.createElement("div");
  text.textContent = "Sẵn sàng demo chatbot nhân viên tư vấn khai thác thông tin khách hàng.";

  const btn = document.createElement("button");
  btn.className = "start-btn";
  btn.textContent = "Bắt đầu tư vấn";
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Đang bắt đầu...";
    div.remove();
    await loadSalesOpening();
  });

  div.appendChild(text);
  div.appendChild(btn);
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function addEmptyState() {
  const div = document.createElement("div");
  div.className = "bubble ai start-card";

  const text = document.createElement("div");
  text.textContent = "Chưa có khách demo. Bấm + User mới để tạo một khách và bắt đầu tư vấn.";

  const btn = document.createElement("button");
  btn.className = "start-btn";
  btn.textContent = "+ User mới";
  btn.addEventListener("click", addNewUser);

  div.appendChild(text);
  div.appendChild(btn);
  chatEl.appendChild(div);
}

function renderProgress(state) {
  if (!canViewProgress()) {
    progressPanelEl.innerHTML = "";
    progressPanelEl.hidden = true;
    progressPanelEl.classList.add("hidden");
    return;
  }

  progressPanelEl.innerHTML = "";

  const title = document.createElement("div");
  title.className = "progress-title";
  title.textContent = "Tiến độ khai thác";
  progressPanelEl.appendChild(title);

  const targets = state?.targets || {};
  const configs = Array.isArray(state?.target_configs) && state.target_configs.length
    ? state.target_configs
    : TARGET_ORDER.map((key, index) => ({
        target_key: key,
        name: TARGET_LABELS[key] || key,
        sort_order: index + 1,
      }));

  configs.forEach((config) => {
    const key = config.target_key;
    const item = document.createElement("div");
    const status = targets[key]?.status || "missing";
    const value = targets[key]?.value || "chưa có";
    item.className = `progress-item ${status}`;

    const label = document.createElement("span");
    label.className = "progress-label";
    label.textContent = repairDisplayText(`${status === "complete" ? "✓" : status === "partial" ? "◐" : "○"} ${config.name || TARGET_LABELS[key] || key}`);

    const val = document.createElement("span");
    val.className = "progress-value";
    val.textContent = status === "missing" ? "chưa có" : repairDisplayText(value);

    item.appendChild(label);
    item.appendChild(val);
    progressPanelEl.appendChild(item);
  });
}

async function refreshProgress(userId = currentUserId) {
  if (!canViewProgress()) {
    renderProgress({ targets: {} });
    return { targets: {} };
  }

  if (!userId) {
    const emptyState = { targets: {} };
    renderProgress(emptyState);
    return emptyState;
  }

  try {
    const res = await fetch(`/sales-discovery/state/${encodeURIComponent(userId)}`);
    if (!res.ok) return null;
    const state = await res.json();
    renderProgress(state);
    return state;
  } catch {
    console.warn("Cannot load discovery state");
    return null;
  }
}

async function loadProfile(userId) {
  try {
    const res = await fetch(`/sales-discovery/profile/${encodeURIComponent(userId)}`);
    if (!res.ok) return null;
    const data = await res.json();
    return data?.profile || null;
  } catch {
    console.warn("Cannot load customer profile");
    return null;
  }
}

function showProfileForm(profile = null) {
  profileFormEl.hidden = false;
  profileFormEl.classList.remove("hidden");
  profileFormEl.style.alignSelf = "stretch";
  profileFormEl.style.width = "calc(100% - 56px)";
  profileGenderEl.value = profile?.gender || "Nam";
  profileBirthYearEl.value = profile?.birth_year || "";
  profileExperienceEl.value = profile?.investment_experience || "Mới tham gia";
}

function hideProfileForm() {
  profileFormEl.classList.add("hidden");
  profileFormEl.hidden = true;
}

async function saveProfile() {
  if (!canUseChat()) {
    showPermissionDenied();
    return;
  }

  if (!currentUserId) {
    addBubble("Bạn cần tạo hoặc chọn một khách trước khi lưu thông tin.", "ai");
    return;
  }

  const payload = {
    gender: profileGenderEl.value,
    birth_year: profileBirthYearEl.value.trim(),
    investment_experience: profileExperienceEl.value,
  };

  if (!payload.birth_year) {
    window.alert("Vui lòng nhập năm sinh.");
    return;
  }

  profileSubmitBtn.disabled = true;
  profileSubmitBtn.textContent = "Đang lưu...";

  try {
    const res = await fetch(`/sales-discovery/profile/${encodeURIComponent(currentUserId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error("Cannot save profile");

    const data = await res.json();
    hideProfileForm();
    chatEl.innerHTML = "";
    if (data?.message) addBubble(data.message, "ai");
    await refreshProgress(currentUserId);
  } catch {
    addBubble("Không thể lưu thông tin ban đầu. Vui lòng thử lại.", "ai");
  } finally {
    profileSubmitBtn.disabled = false;
    profileSubmitBtn.textContent = "Lưu và bắt đầu tư vấn";
  }
}

async function loadUsers() {
  try {
    const res = await fetch("/sales-discovery/users");
    if (!res.ok) throw new Error("Cannot load users");
    const data = await res.json();
    users = Array.isArray(data?.users) ? data.users : [];
  } catch {
    console.warn("Cannot load users from server");
    users = [];
  }

  const savedActive = localStorage.getItem(ACTIVE_USER_STORAGE_KEY);
  currentUserId = users.some((user) => user.id === savedActive)
    ? savedActive
    : users[0]?.id || null;
}

function saveActiveUser() {
  if (currentUserId) {
    localStorage.setItem(ACTIVE_USER_STORAGE_KEY, currentUserId);
  } else {
    localStorage.removeItem(ACTIVE_USER_STORAGE_KEY);
  }
}

function renderUsers() {
  userListEl.innerHTML = "";

  if (!users.length) {
    const empty = document.createElement("div");
    empty.className = "empty-users";
    empty.textContent = "Chưa có khách";
    userListEl.appendChild(empty);
    return;
  }

  users.forEach((user) => {
    const row = document.createElement("div");
    row.className = `user-item ${user.id === currentUserId ? "active" : ""}`;

    const main = document.createElement("button");
    main.className = "user-main";
    main.type = "button";

    const name = document.createElement("span");
    name.className = "user-name";
    name.textContent = user.name;

    const id = document.createElement("span");
    id.className = "user-id";
    id.textContent = user.id;

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "delete-user";
    deleteBtn.type = "button";
    deleteBtn.title = "Xóa khách";
    deleteBtn.textContent = "×";
    deleteBtn.addEventListener("click", () => deleteUser(user.id));

    main.appendChild(name);
    main.appendChild(id);
    main.addEventListener("click", () => selectUser(user.id));
    row.appendChild(main);
    row.appendChild(deleteBtn);
    userListEl.appendChild(row);
  });
}

async function loadChatHistory(userId) {
  try {
    const res = await fetch(`/chat/history/${encodeURIComponent(userId)}`);
    if (!res.ok) return [];

    const data = await res.json();
    return Array.isArray(data?.messages) ? data.messages : [];
  } catch {
    console.warn("Cannot load chat history");
    return [];
  }
}

function renderChatHistory(messages) {
  chatEl.innerHTML = "";
  lastRenderedHistorySignature = chatHistorySignature(messages);

  messages.forEach((msg) => {
    if (msg.role === "user") {
      addBubble(msg.content, "user");
    }

    if (msg.role === "assistant") {
      addBubble(msg.content, "ai");
    }
  });
}

function chatHistorySignature(messages) {
  return JSON.stringify((messages || []).map((msg) => [msg.role, msg.content, msg.created_at || ""]));
}

async function refreshVisibleChatHistory() {
  if (
    isChatStreaming ||
    currentView !== "chat" ||
    !currentUserId ||
    profileFormEl && !profileFormEl.hidden
  ) return;

  const messages = await loadChatHistory(currentUserId);
  const signature = chatHistorySignature(messages);
  if (signature === lastRenderedHistorySignature) return;

  renderChatHistory(messages);
}

async function selectUser(userId) {
  currentUserId = userId;
  const user = users.find((item) => item.id === currentUserId);
  activeUserEl.textContent = user ? `Đang tư vấn: ${user.name} (${user.id})` : "Chưa chọn khách";
  chatEl.innerHTML = "";
  msgEl.value = "";
  saveActiveUser();
  renderUsers();

  const messages = await loadChatHistory(currentUserId);
  const profile = await loadProfile(currentUserId);
  renderChatHistory(messages);
  const state = await refreshProgress(currentUserId);
  const experienceStatus = state?.targets?.investment_experience?.status;
  const needsInitialProfile = experienceStatus !== "complete";

  if (needsInitialProfile) {
    showProfileForm(profile);
  } else {
    hideProfileForm();
    if (!messages.length) {
      addStartPrompt();
    }
  }
}

async function addNewUser() {
  if (!canUseChat()) {
    showPermissionDenied();
    return;
  }

  try {
    const res = await fetch("/sales-discovery/users", { method: "POST" });
    if (!res.ok) throw new Error("Cannot create user");
    const data = await res.json();
    const user = data?.user;
    await loadUsers();
    if (user?.id) {
      await selectUser(user.id);
    } else {
      renderUsers();
    }
  } catch {
    addBubble("Không thể tạo khách mới. Vui lòng thử lại.", "ai");
  }
}

async function deleteUser(userId) {
  const user = users.find((item) => item.id === userId);
  const label = user ? `${user.name} (${user.id})` : userId;
  const ok = window.confirm(`Xóa ${label} và toàn bộ dữ liệu đã lưu trong DB?`);

  if (!ok) return;

  try {
    await fetch(`/sales-discovery/users/${encodeURIComponent(userId)}`, {
      method: "DELETE",
    });
  } catch {
    console.warn("Cannot delete user data on server");
  }

  await loadUsers();
  currentUserId = users[0]?.id || null;
  saveActiveUser();
  renderUsers();
  chatEl.innerHTML = "";
  msgEl.value = "";
  activeUserEl.textContent = currentUserId ? "" : "Chưa chọn khách";
  await refreshProgress(currentUserId);

  if (currentUserId) {
    await selectUser(currentUserId);
  } else {
    hideProfileForm();
    addEmptyState();
  }
}

function renderConditionTypeOptions() {
  const types = conditionTypes;

  if (conditionFilterTypeEl) {
    const current = conditionFilterTypeEl.value;

    conditionFilterTypeEl.innerHTML = `
      <option value="">Tất cả type</option>
      ${types.map((type) => `
        <option value="${escapeHtml(type.value_key)}">
          ${escapeHtml(type.label)}
        </option>
      `).join("")}
    `;

    conditionFilterTypeEl.value = current;
  }

  if (conditionTypeEl) {
    const current = conditionTypeEl.value;

    conditionTypeEl.innerHTML = types.map((type) => `
      <option value="${escapeHtml(type.value_key)}">
        ${escapeHtml(type.label)}
      </option>
    `).join("");

    if (current) conditionTypeEl.value = current;
  }

  if (activeFlowFilterTypeEl) {
    const current = activeFlowFilterTypeEl.value;

    activeFlowFilterTypeEl.innerHTML = `
      <option value="">Tất cả loại mẫu</option>
      ${types.map((type) => `
        <option value="${escapeHtml(type.value_key)}">
          ${escapeHtml(type.label)}
        </option>
      `).join("")}
    `;

    activeFlowFilterTypeEl.value = current;
  }

  const flowFilterTypeEl = document.getElementById("flowFilterType");

  if (flowFilterTypeEl) {
    const current = flowFilterTypeEl.value;

    flowFilterTypeEl.innerHTML = `
      <option value="">Tất cả loại mẫu</option>
      ${types.map((type) => `
        <option value="${escapeHtml(type.value_key)}">
          ${escapeHtml(type.label)}
        </option>
      `).join("")}
    `;

    flowFilterTypeEl.value = current;
  }
}

function openConditionTypeModal() {
  if (!conditionTypeModalEl) return;

  conditionTypeModalEl.hidden = false;
  conditionTypeModalEl.classList.remove("hidden");

  if (conditionTypeNameEl) {
    conditionTypeNameEl.value = "";
    setTimeout(() => conditionTypeNameEl.focus(), 50);
  }
}

async function saveNewConditionType() {
  const label = conditionTypeNameEl?.value?.trim();

  if (!label) {
    conditionTypeErrorEl.textContent = "Vui lòng nhập tên type";
    return;
  }

  conditionTypeErrorEl.textContent = "";

  try {
    const res = await fetch("/condition-types", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "same-origin",
      body: JSON.stringify({ label }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(data?.detail || "Không tạo được type");
    }

    await loadConditionTypes();

    const createdType = conditionTypes.find(
      (item) => item.label === label
    );

    if (createdType?.value_key && conditionTypeEl) {
      conditionTypeEl.value = createdType.value_key;
    }

    closeConditionTypeModal();
    showToast("Đã thêm type mới");
  } catch (err) {
    console.error(err);
    conditionTypeErrorEl.textContent =
      err.message || "Không tạo được type";
  }
}

function closeConditionTypeModal() {
  if (!conditionTypeModalEl) return;

  conditionTypeModalEl.hidden = true;
  conditionTypeModalEl.classList.add("hidden");

  if (conditionTypeNameEl) {
    conditionTypeNameEl.value = "";
  }
}

async function loadConditionTemplates() {
  const res = await fetch("/condition-templates", {
    credentials: "same-origin",
  });

  if (!res.ok) {
    throw new Error("Không tải được danh sách mẫu điều kiện");
  }

  const data = await res.json();
  conditionTemplates = data.templates || [];
  renderConditionTemplates();
}

async function loadConditionFlows() {
  const res = await fetch("/condition-flows", {
    credentials: "same-origin",
  });

  if (!res.ok) {
    throw new Error("Không tải được danh sách mẫu kết hợp");
  }

  const data = await res.json();
  conditionFlows = data.flows || [];

  renderConfirmedConditionLibrary();
  renderConditionFlows();
  renderActiveFlows();
}

async function loadConditionTypes() {
  try {
    const res = await fetch("/condition-types", {
      credentials: "same-origin",
    });

    if (!res.ok) {
      throw new Error();
    }

    const data = await res.json();

    conditionTypes = Array.isArray(data?.types)
      ? data.types
      : [];

    renderConditionTypeOptions();

  } catch (err) {
    console.error(err);

    showToast(
      "Không tải được danh sách type",
      "error"
    );
  }
}

function openFlowModal() {
  if (!flowModalEl) return;
  updateFlowFieldCounts();
  flowModalEl.hidden = false;
  flowModalEl.classList.remove("hidden");
  flowNameEl?.focus();
}

function closeFlowModal() {
  if (!flowModalEl) return;
  flowModalEl.hidden = true;
  flowModalEl.classList.add("hidden");
}

function updateFlowFieldCounts() {
  if (flowNameCountEl && flowNameEl) {
    flowNameCountEl.textContent = `${flowNameEl.value.length}/100`;
  }

  if (flowPromptCountEl && flowPromptTemplateEl) {
    flowPromptCountEl.textContent = `${flowPromptTemplateEl.value.length}/500`;
  }
}

function renderConfirmedConditionLibrary() {
  if (!flowConditionSearchEl && !confirmedConditionLibraryEl) return;

  const confirmed = conditionTemplates.filter(
    (item) => item.status === "confirmed"
  );

  // Nếu HTML mới dùng dropdown
  if (flowConditionSearchEl?.tagName === "SELECT") {
    const keyword = (flowConditionKeywordEl?.value || "")
      .trim()
      .toLowerCase();

    const filtered = confirmed.filter((item) => {
      const name = (item.name || "").toLowerCase();
      const logic = (item.condition_logic || "").toLowerCase();
      const desc = (item.description || "").toLowerCase();

      return (
        !keyword ||
        name.includes(keyword) ||
        logic.includes(keyword) ||
        desc.includes(keyword)
      );
    });

    flowConditionSearchEl.innerHTML = `
      <option value="">
        ${filtered.length ? "Chọn điều kiện..." : "Không tìm thấy điều kiện"}
      </option>
      ${
        filtered.map((item) => `
          <option value="${item.id}">
            ${escapeHtml(item.name)}
          </option>
        `).join("")
      }
    `;

    // nếu search ra đúng 1 kết quả thì tự chọn luôn
    if (keyword && filtered.length === 1) {
      flowConditionSearchEl.value = String(filtered[0].id);
    }

    return;
  }

  // Fallback nếu vẫn dùng input search + list cũ
  if (!confirmedConditionLibraryEl) return;

  const keyword = (flowConditionSearchEl?.value || "").trim().toLowerCase();

  const filtered = confirmed.filter((item) => {
    return (
      !keyword ||
      (item.name || "").toLowerCase().includes(keyword) ||
      (item.condition_logic || "").toLowerCase().includes(keyword) ||
      (item.description || "").toLowerCase().includes(keyword)
    );
  });

  if (!filtered.length) {
    confirmedConditionLibraryEl.innerHTML =
      `<div class="empty-users">Chưa có điều kiện đã xác nhận</div>`;
    return;
  }

  confirmedConditionLibraryEl.innerHTML = filtered.map((item) => `
    <div class="flow-condition-option">
      <div>
        <strong>${escapeHtml(item.name)}</strong>
        <small>${escapeHtml(item.condition_logic || "")}</small>
      </div>
      <button type="button" onclick="addConditionToExpression(${item.id})">+</button>
    </div>
  `).join("");
}

function addConditionToExpression(id) {
  const found = conditionTemplates.find(
    (item) => Number(item.id) === Number(id)
  );

  if (!found) {
    showToast("Không tìm thấy điều kiện", "error");
    return;
  }

  if (
    selectedConditions.some(
      (item) => Number(item.id) === Number(id)
    )
  ) {
    showToast("Điều kiện này đã được thêm", "error");
    return;
  }

  selectedConditions.push({
    id: found.id,
    name: found.name || `Điều kiện ${found.id}`,
    operator: selectedConditions.length ? nextOperator : "",
  });

  renderSelectedConditions();
}

function renderSelectedConditions() {
  const wrap =
    document.getElementById("flowPreview") ||
    document.getElementById("selectedFlowConditions");

  if (!wrap) return;

  if (!selectedConditions.length) {
    wrap.innerHTML = `
      <span class="builder-preview-empty">
        Chưa chọn điều kiện nào
      </span>
    `;
    buildFlowPreview();
    return;
  }

  wrap.innerHTML = selectedConditions.map((item, index) => {
    const label = String.fromCharCode(65 + index);

    return `
      ${index > 0 ? `<span class="builder-preview-op">${item.operator}</span>` : ""}
      <span class="builder-preview-node">
        <b>${label}</b>
        ${escapeHtml(item.name)}
        <button
          type="button"
          class="builder-remove"
          onclick="removeSelectedCondition(${item.id})"
        >
          ×
        </button>
      </span>
    `;
  }).join("");
  buildFlowPreview();
}

function removeSelectedCondition(id) {
  selectedConditions = selectedConditions.filter((x) => x.id !== id);
  renderSelectedConditions();
}

function clearSelectedConditions() {
  selectedConditions = [];
  renderSelectedConditions();
}

function buildFlowPreview() {
  if (!flowExpressionEl) return;

  if (!selectedConditions.length) {
    flowExpressionEl.value = "";
    return;
  }

  flowExpressionEl.value = selectedConditions
    .map((item, index) => {
      if (index === 0) return String(item.id);
      return `${item.operator || "AND"} ${item.id}`;
    })
    .join(" ");
}

async function saveConditionFlow() {
  const existingFlow = editingConditionFlowId
    ? conditionFlows.find((flow) => Number(flow.id) === Number(editingConditionFlowId))
    : null;
  const payload = {
    name: flowNameEl.value.trim(),
    expression: flowExpressionEl.value.trim(),
    prompt_template: flowPromptTemplateEl.value.trim(),
    trigger_prompt: existingFlow?.trigger_prompt || "",
    status: "draft",
  };

  if (!payload.name || !payload.expression || !payload.prompt_template) {
    showToast("Vui lòng nhập đủ tên, biểu thức và câu mẫu", "error");
    return;
  }

  const isEditing = Boolean(editingConditionFlowId);
  const url = isEditing
    ? `/condition-flows/${editingConditionFlowId}`
    : "/condition-flows";

  const method = isEditing ? "PATCH" : "POST";

  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    showToast("Lưu mẫu kết hợp thất bại", "error");
    return;
  }

  flowNameEl.value = "";
  flowExpressionEl.value = "";
  flowPromptTemplateEl.value = "";
  selectedConditions = [];
  editingConditionFlowId = null;
  updateFlowFieldCounts();
  renderSelectedConditions();

  await loadConditionFlows();
  closeFlowModal();
  showToast("Đã lưu mẫu kết hợp");
}

function getConditionNameById(id) {
  const found = conditionTemplates.find(
    (item) => Number(item.id) === Number(id)
  );

  return found?.name || `Điều kiện ${id}`;
}

function formatFlowExpression(expression = "") {
  return String(expression)
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => {
      const upper = part.toUpperCase();

      if (upper === "AND" || upper === "OR") {
        return upper;
      }

      const id = Number(part);
      if (!id) return part;

      return getConditionNameById(id);
    })
    .join(" ");
}

function renderConditionFlows() {
  if (!conditionFlowListEl) return;

  const keyword = (flowSearchEl?.value || "").trim().toLowerCase();
  const visibleFlows = conditionFlows.filter((flow) => {
    const readableExpression = formatFlowExpression(flow.expression || "");

    return (
      !keyword ||
      (flow.name || "").toLowerCase().includes(keyword) ||
      (flow.prompt_template || "").toLowerCase().includes(keyword) ||
      readableExpression.toLowerCase().includes(keyword)
    );
  });

  if (!visibleFlows.length) {
    conditionFlowListEl.innerHTML =
      `<div class="empty-users">${conditionFlows.length ? "Không tìm thấy mẫu kết hợp" : "Chưa có mẫu kết hợp"}</div>`;
    return;
  }

  conditionFlowListEl.innerHTML = visibleFlows.map((flow) => {
    const confirmed = flow.status === "confirmed";

    return `
      <div class="step2-flow-row">
        <div>
          <strong>${escapeHtml(flow.name)}</strong>
        </div>

        <div>
          ${escapeHtml(flow.prompt_template || "-")}
        </div>

        <div class="logic-cell">
          ${escapeHtml(formatFlowExpression(flow.expression || "-"))}
        </div>

        <div class="condition-actions">
          <button
            type="button"
            title="Sửa"
            onclick="editConditionFlow(${flow.id})"
          >
            ✎
          </button>

          <button
            type="button"
            class="${confirmed ? "flow-confirmed" : "flow-unconfirmed"}"
            title="${confirmed ? "Đã xác nhận" : "Chưa xác nhận"}"
            onclick="confirmConditionFlow(${flow.id})"
          >
            ✓
          </button>

          <button
            type="button"
            title="Xóa"
            onclick="deleteConditionFlow(${flow.id})"
          >
            ×
          </button>
        </div>
      </div>
    `;
  }).join("");
}

function renderActiveFlows() {
  if (!activeFlowListEl) return;

  const typeFilter = activeFlowFilterTypeEl?.value || "";
  const keyword = (activeFlowSearchEl?.value || "").trim().toLowerCase();

  const confirmedFlows = conditionFlows.filter((flow) => {
    const isConfirmed = flow.status === "confirmed";
    const matchType = !typeFilter || flow.type === typeFilter;
    const readableExpression = formatFlowExpression(flow.expression || "");

    const matchKeyword =
      !keyword ||
      (flow.name || "").toLowerCase().includes(keyword) ||
      readableExpression.toLowerCase().includes(keyword) ||
      (flow.prompt_template || "").toLowerCase().includes(keyword) ||
      (flow.trigger_prompt || "").toLowerCase().includes(keyword);

    return isConfirmed && matchType && matchKeyword;
  });

  if (!confirmedFlows.length) {
    activeFlowListEl.innerHTML =
      `<div class="empty-users">Chưa có mẫu nào được xác nhận ở bước 2</div>`;
    return;
  }

  activeFlowListEl.innerHTML = confirmedFlows.map((flow) => {
    const active = flow.is_active || flow.active || flow.enabled;
    const checking = Number(checkingDemoFlowId) === Number(flow.id);
    const checkResult = demoCheckResults[flow.id];
    const checkDate = getActiveFlowCheckDate(flow.id);

    return `
      <div class="step3-flow-row">
        <div>
          <strong>${escapeHtml(flow.name)}</strong>
        </div>

        <div>
          ${escapeHtml(flow.prompt_template || "-")}
        </div>

        <div class="logic-cell">
          ${escapeHtml(formatFlowExpression(flow.expression || "-"))}
        </div>

        <div>
          <textarea
            id="triggerPrompt-${flow.id}"
            class="step3-trigger-prompt"
            maxlength="500"
            placeholder="Nhập prompt..."
            onblur="updateActiveFlowTriggerPrompt(${flow.id}, this.value)"
          >${escapeHtml(flow.trigger_prompt || "")}</textarea>
        </div>

        <div>
          <input
            class="step3-row-date"
            type="date"
            value="${escapeHtml(checkDate)}"
            onchange="setActiveFlowCheckDate(${flow.id}, this.value)"
          />
        </div>

        <div class="condition-actions">
          <button
            type="button"
            class="demo-check-btn"
            title="Check demo"
            ${checking ? "disabled" : ""}
            onclick="demoCheckConditionFlow(${flow.id})"
          >
            ${checking ? "Đang check..." : "Check demo"}
          </button>

          <button
            type="button"
            class="${active ? "flow-confirmed" : "flow-unconfirmed"}"
            title="${active ? "Đang bật" : "Đang tắt"}"
            onclick="toggleActiveFlow(${flow.id})"
          >
            ✓
          </button>
        </div>

        ${renderDemoCheckResult(checkResult)}
      </div>
    `;
  }).join("");
}

async function updateActiveFlowTriggerPrompt(id, value) {
  const prompt = String(value || "").trim();
  const flow = conditionFlows.find((item) => Number(item.id) === Number(id));

  if (!flow || (flow.trigger_prompt || "") === prompt) return;

  flow.trigger_prompt = prompt;

  try {
    const res = await fetch(`/condition-flows/${id}/trigger-prompt`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        trigger_prompt: prompt,
      }),
    });

    if (!res.ok) {
      showToast("Lưu prompt thất bại", "error");
      await loadConditionFlows();
      return;
    }
  } catch {
    showToast("Không gọi được API lưu prompt", "error");
    await loadConditionFlows();
  }
}

function renderDemoCheckResult(result) {
  if (!result) return "";

  const rows = (result.results || []).map((item) => {
    const matched = Boolean(item.matched);
    const title = item.template_name || `Điều kiện ${item.template_id || "-"}`;
    const key = item.condition_key || item.condition || "";
    const message = item.message || (matched ? "Đạt" : "Không đạt");

    return `
      <div class="demo-check-condition ${matched ? "matched" : "unmatched"}">
        <span>${matched ? "✓" : "!"}</span>
        <div>
          <strong>${escapeHtml(title)}</strong>
          <small>${escapeHtml(key || "-")}</small>
          <p>${escapeHtml(message)}</p>
        </div>
      </div>
    `;
  }).join("");
  const checkDateLine = result.check_date
    ? `<span>${escapeHtml(`Ngay check ${result.check_date}`)}</span>`
    : "";

  return `
    <div class="demo-check-result ${result.matched ? "matched" : "unmatched"}">
      <div class="demo-check-summary">
        ${checkDateLine}
        <strong>${result.matched ? "Mẫu đã thỏa điều kiện" : "Mẫu chưa thỏa điều kiện"}</strong>
        <span>${result.matched ? `Đã gửi cho ${result.delivered_count || 0} user` : "Chưa gửi thông báo"}</span>
      </div>
      <div class="demo-check-conditions">
        ${rows || `<div class="demo-check-empty">Không có điều kiện con để kiểm tra</div>`}
      </div>
    </div>
  `;
}

async function demoCheckConditionFlow(id) {
  checkingDemoFlowId = id;
  demoCheckResults[id] = null;
  renderActiveFlows();

  const checkDate = getActiveFlowCheckDate(id);

  try {
    const res = await fetch(`/condition-flows/${id}/demo-check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        context: {
          date: checkDate,
        },
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      demoCheckResults[id] = {
        matched: false,
        results: [],
      };
      showToast(data?.detail || "Check demo thất bại", "error");
      return;
    }

    demoCheckResults[id] = {
      ...data,
      check_date: data.check_date || checkDate,
    };

    if (data.matched) {
      showToast(`Đã gửi demo cho ${data.delivered_count || 0} user`);
      await refreshVisibleChatHistory();
      return;
    }

    showToast("Mẫu này chưa thỏa điều kiện", "error");
  } catch {
    demoCheckResults[id] = {
      matched: false,
      results: [],
    };
    showToast("Không gọi được API check demo", "error");
  } finally {
    checkingDemoFlowId = null;
    renderActiveFlows();
  }
}

async function toggleActiveFlow(id) {
  const flow = conditionFlows.find((item) => item.id === id);
  if (!flow) return;

  const current = Boolean(flow.is_active || flow.active || flow.enabled);
  const nextActive = !current;

  flow.is_active = nextActive;
  flow.active = nextActive;
  flow.enabled = nextActive;

  renderActiveFlows();

  try {
    const res = await fetch(`/condition-flows/${id}/active`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ active: nextActive }),
    });

    if (!res.ok) throw new Error("toggle failed");

    showToast(nextActive ? "Đã bật kịch bản" : "Đã tắt kịch bản");
  } catch {
    flow.is_active = current;
    flow.active = current;
    flow.enabled = current;
    renderActiveFlows();
    showToast("Không lưu được trạng thái bật/tắt", "error");
  }
}

function hydrateSelectedConditionsFromExpression(expression = "") {
  selectedConditions = [];

  const parts = String(expression).trim().split(/\s+/).filter(Boolean);
  let pendingOperator = "";

  parts.forEach((part) => {
    const upper = part.toUpperCase();

    if (upper === "AND" || upper === "OR") {
      pendingOperator = upper;
      return;
    }

    const id = Number(part);
    if (!id) return;

    const found = conditionTemplates.find((item) => item.id === id);
    if (!found) return;

    selectedConditions.push({
      id: found.id,
      name: found.name || `Điều kiện ${found.id}`,
      operator: selectedConditions.length ? (pendingOperator || "AND") : "",
    });

    pendingOperator = "";
  });

  renderSelectedConditions();
}

function editConditionFlow(id) {
  const flow = conditionFlows.find((item) => item.id === id);

  if (!flow) return;

  editingConditionFlowId = id;
  flowNameEl.value = flow.name || "";
  flowExpressionEl.value = flow.expression || "";
  flowPromptTemplateEl.value = flow.prompt_template || "";
  updateFlowFieldCounts();
  hydrateSelectedConditionsFromExpression(flow.expression || "");

  openFlowModal();
  showToast("Đang chỉnh sửa mẫu kết hợp");
}

async function deleteConditionFlow(id) {
  if (!confirm("Xóa mẫu kết hợp này?")) return;

  const res = await fetch(`/condition-flows/${id}`, {
    method: "DELETE",
    credentials: "same-origin",
  });

  if (!res.ok) {
    showToast("Xóa mẫu kết hợp thất bại", "error");
    return;
  }

  await loadConditionFlows();
  showToast("Đã xóa mẫu kết hợp");
}

async function confirmConditionFlow(id) {
  const ok = confirm("Xác nhận mẫu kết hợp này để chuyển sang bước 3?");

  if (!ok) return;

  const res = await fetch(`/condition-flows/${id}/confirm`, {
    method: "POST",
    credentials: "same-origin",
  });

  if (!res.ok) {
    showToast("Xác nhận mẫu kết hợp thất bại", "error");
    return;
  }

  await loadConditionFlows();

  showToast("Đã xác nhận mẫu kết hợp, chuyển sang bước 3");
}

function cancelFlowEdit() {
  editingConditionFlowId = null;
  flowNameEl.value = "";
  flowExpressionEl.value = "";
  flowPromptTemplateEl.value = "";
  selectedConditions = [];
  updateFlowFieldCounts();
  renderSelectedConditions();
}

async function saveConditionTemplate() {
  const payload = {
    type: conditionTypeEl.value,
    name: conditionNameEl.value.trim(),
    condition_logic: conditionLogicEl.value.trim(),
    description: conditionDescriptionEl.value.trim(),
  };

  if (!payload.name || !payload.condition_logic || !payload.description) {
    showToast("Vui lòng nhập đủ tên, điều kiện và mô tả", "error");
    return;
  }

  const isEditing = Boolean(editingConditionTemplateId);

  const url = isEditing
    ? `/condition-templates/${editingConditionTemplateId}`
    : "/condition-templates";

  const method = isEditing ? "PATCH" : "POST";

  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    showToast(
      isEditing
        ? "Cập nhật mẫu điều kiện thất bại"
        : "Lưu mẫu điều kiện thất bại",
      "error"
    );
    return;
  }

  conditionNameEl.value = "";
  conditionLogicEl.value = "";
  conditionDescriptionEl.value = "";
  editingConditionTemplateId = null;
  saveConditionTemplateBtn.textContent = "Lưu & gửi Dev duyệt";

  await loadConditionTemplates();

  showToast(
    isEditing
      ? "Đã cập nhật mẫu điều kiện"
      : "Đã lưu mẫu điều kiện"
  );
}

async function deleteConditionTemplate(id) {
  if (!confirm("Xóa mẫu điều kiện này?")) return;

  const res = await fetch(`/condition-templates/${id}`, {
    method: "DELETE",
    credentials: "same-origin",
  });

  if (!res.ok) {
    showToast("Xóa thất bại");
    return;
  }

  await loadConditionTemplates();
  showToast("Đã xóa mẫu điều kiện");
}

function editConditionTemplate(id) {
  const item = conditionTemplates.find((template) => template.id === id);

  if (!item) {
    showToast("Không tìm thấy mẫu để sửa", "error");
    return;
  }

  editingConditionTemplateId = id;
  conditionTypeEl.value = item.type;
  conditionNameEl.value = item.name || "";
  conditionLogicEl.value = item.condition_logic || "";
  conditionDescriptionEl.value = item.description || "";

  saveConditionTemplateBtn.textContent = "Cập nhật mẫu";
  conditionNameEl.focus();

  showToast("Đang chỉnh sửa mẫu điều kiện");
}

async function confirmConditionTemplate(id) {
  const item = conditionTemplates.find((template) => Number(template.id) === Number(id));

  if (item?.support_status === "unsupported") {
    showToast("Backend chưa xác nhận điều kiện này", "error");
    return;
  }

  const ok = confirm("Xác nhận Dev đã code xong mẫu điều kiện này?");

  if (!ok) return;

  const res = await fetch(`/condition-templates/${id}/confirm`, {
    method: "POST",
    credentials: "same-origin",
  });

  if (!res.ok) {
    showToast("Xác nhận thất bại", "error");
    return;
  }

  await loadConditionTemplates();
  showToast("Đã xác nhận mẫu điều kiện");
}

async function confirmConditionTemplateSafe(id) {
  const item = conditionTemplates.find((template) => Number(template.id) === Number(id));

  if (item?.support_status === "unsupported") {
    showToast("Backend chua ho tro dieu kien nay", "error");
    return;
  }

  await confirmConditionTemplate(id);
}

function conditionTypeLabel(type) {
  const found = conditionTypes.find((item) => item.value_key === type);
  return found?.label || type || "";
}

function renderConditionTemplates() {
  if (!conditionTemplateListEl) return;

  const typeFilter = conditionFilterTypeEl?.value || "";
  const keyword = (conditionSearchEl?.value || "").trim().toLowerCase();

  const filteredTemplates = conditionTemplates.filter((item) => {
    const matchType = !typeFilter || item.type === typeFilter;
    const matchKeyword =
      !keyword ||
      item.name.toLowerCase().includes(keyword) ||
      (item.description || "").toLowerCase().includes(keyword);

    return matchType && matchKeyword;
  });

  const totalPages = Math.ceil(filteredTemplates.length / CONDITION_PAGE_SIZE);

  if (conditionPage > totalPages) conditionPage = Math.max(totalPages, 1);

  if (!filteredTemplates.length) {
    conditionTemplateListEl.innerHTML = `<div class="empty-users">Chưa có mẫu điều kiện</div>`;
    if (conditionPaginationEl) conditionPaginationEl.innerHTML = "";
    return;
  }

  const start = (conditionPage - 1) * CONDITION_PAGE_SIZE;
  const pageItems = filteredTemplates.slice(start, start + CONDITION_PAGE_SIZE);

  conditionTemplateListEl.innerHTML = pageItems.map((item,index) => {
    const isSupported = item.support_status === "supported";

    return `
      <div class="condition-row">
        <div>${item.id}</div>
        <div>${conditionTypeLabel(item.type)}</div>

        <div>
          <strong>${escapeHtml(item.name)}</strong>
        </div>

        <div class="logic-cell">
          ${escapeHtml(item.condition_logic || "-")}
        </div>

        <div>
          ${escapeHtml(item.description || "")}
        </div>

        <div class="condition-actions">
          <button
            type="button"
            title="Sửa"
            onclick="editConditionTemplate(${item.id})"
          >
            ✎
          </button>

          <button
            type="button"
            class="${item.status === "confirmed"
              ? "flow-confirmed"
              : "flow-unconfirmed"}"
            title="${item.status === "confirmed"
              ? "Đã xác nhận"
              : "Chưa xác nhận"}"
            ${isSupported ? "" : "disabled"}
            onclick="confirmConditionTemplateSafe(${item.id})"
          >
            ✓
          </button>

          <button
            type="button"
            title="Xóa"
            onclick="deleteConditionTemplate(${item.id})"
          >
            ×
          </button>
        </div>
      </div>
  `;
  }).join("");

  renderConditionPagination(totalPages);
}

function renderConditionPagination(totalPages) {
  if (!conditionPaginationEl) return;

  if (totalPages <= 1) {
    conditionPaginationEl.innerHTML = "";
    return;
  }

  conditionPaginationEl.innerHTML = `
    <button type="button" ${conditionPage <= 1 ? "disabled" : ""} onclick="conditionPage--; renderConditionTemplates();">‹</button>
    ${Array.from({ length: totalPages }, (_, i) => `
      <button type="button" class="${conditionPage === i + 1 ? "active" : ""}" onclick="conditionPage=${i + 1}; renderConditionTemplates();">${i + 1}</button>
    `).join("")}
    <button type="button" ${conditionPage >= totalPages ? "disabled" : ""} onclick="conditionPage++; renderConditionTemplates();">›</button>
  `;
}

/* =========================
   Load Models
========================= */

async function loadModels() {
  try {
    const res = await fetch("/meta/models");
    if (!res.ok) return;

    const data = await res.json();
    modelSelect.innerHTML = "";

    data?.models?.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      modelSelect.appendChild(opt);
    });
  } catch {
    console.warn("Cannot load models");
  }
}

/* =========================
   SSE Parser
========================= */

function parseSSEChunk(buffer) {
  const out = [];
  let idx;

  while ((idx = buffer.indexOf("\n\n")) !== -1) {
    const raw = buffer.slice(0, idx);
    buffer = buffer.slice(idx + 2);

    let event = "message";
    let dataLine = "";

    raw.split("\n").forEach((line) => {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      }
      if (line.startsWith("data:")) {
        dataLine += line.slice(5).trim();
      }
    });

    if (dataLine) {
      try {
        out.push({ event, data: JSON.parse(dataLine) });
      } catch {
        out.push({ event, data: { text: dataLine } });
      }
    }
  }

  return { out, buffer };
}

/* =========================
   Payload Builder
========================= */

function buildPayload(user_id, message) {
  return {
    user_id,
    message,
    language: langSelect?.value || "vi",
    model: modelSelect?.value || null,
    meta: {
      mode: "sales_discovery",
    },
  };
}

async function loadSalesOpening() {
  try {
    const res = await fetch("/sales-discovery/opening");
    if (!res.ok) return;

    const data = await res.json();
    if (data?.message) addBubble(data.message, "ai");
  } catch {
    console.warn("Cannot load sales opening");
  }
}

/* =========================
   SSE Event Handler
========================= */

function handleSSEEvent(evt, aiBubble) {
  if (evt.event === "delta") {
    aiBubble.textContent += evt.data?.text || "";
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  if (evt.event === "done") {
    aiBubble.textContent = repairDisplayText(aiBubble.textContent);
  }

  if (evt.event === "done" && evt.data?.sources?.length) {
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent =
      "Sources: " +
      evt.data.sources
        .map((s) => `${s.doc}#${s.chunk_id}`)
        .join(", ");

    aiBubble.appendChild(meta);
  }
}

/* =========================
   Stream Chat
========================= */

async function streamChat(payload, aiBubble) {
  let res;
  aiBubble.innerHTML = `
    <div class="typing">
      <span></span><span></span><span></span>
    </div>
  `;
  try {
    res = await fetch("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
  } catch {
    aiBubble.textContent = "Không thể kết nối server.";
    return false;
  }

  if (res.status === 403) {
    const data = await res.json().catch(() => ({}));
    aiBubble.textContent = data?.detail || "Tài khoản này chưa có quyền sử dụng chatbot.";
    return false;
  }

  if (!res.ok || !res.body) {
    aiBubble.textContent = "Server lỗi.";
    return false;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");

  let buffer = "";
  let doneReading = false;

  while (!doneReading) {
    const { done, value } = await reader.read();
    doneReading = done;

    if (!value) continue;

    buffer += decoder.decode(value, { stream: true });

    const parsed = parseSSEChunk(buffer);
    buffer = parsed.buffer;

    parsed.out.forEach((evt) => {
      if (aiBubble.querySelector(".typing")) {
        aiBubble.innerHTML = "";
      }
      handleSSEEvent(evt, aiBubble);
    });
  }

  return true;
}

/* =========================
   Main Send
========================= */

async function send() {
  const user_id = currentUserId;
  const message = msgEl?.value?.trim();

  if (!canUseChat()) {
    showPermissionDenied();
    return;
  }

  if (!user_id) {
    addBubble("Bạn cần tạo hoặc chọn một khách trước khi nhắn.", "ai");
    return;
  }

  if (!message || isChatStreaming) return;

  isChatStreaming = true;
  setChatAccessState();
  addBubble(message, "user");
  msgEl.value = "";

  const aiBubble = addBubble("", "ai");

  let streamCompleted = false;
  try {
    const payload = buildPayload(user_id, message);
    streamCompleted = await streamChat(payload, aiBubble);
    if (streamCompleted) await refreshProgress(user_id);
  } finally {
    isChatStreaming = false;
    setChatAccessState();
    if (streamCompleted) await refreshVisibleChatHistory();
    msgEl.focus();
  }
}

/* =========================
   Events
========================= */

sendBtn.addEventListener("click", send);
newUserBtn.addEventListener("click", addNewUser);
profileSubmitBtn.addEventListener("click", saveProfile);
loginOpenBtn.addEventListener("click", openLoginModal);
loginSubmitBtn.addEventListener("click", login);
guestContinueBtn.addEventListener("click", continueAsGuest);
accountTriggerEl.addEventListener("click", toggleAccountDropdown);
logoutBtn.addEventListener("click", logout);
chatViewBtn.addEventListener("click", showChatView);
salesTargetViewBtn?.addEventListener("click", showSalesTargetAdminView);
caseIdeaViewBtn?.addEventListener("click", showCaseIdeaAdminView);
conditionViewBtn?.addEventListener("click", () => {
  hideProfileForm();
  setMainView("conditions");
});
conditionStep1Btn?.addEventListener("click", () => {showConditionStep(1);});
conditionStep2Btn?.addEventListener("click", () => {showConditionStep(2);});
conditionStep3Btn?.addEventListener("click", () => {showConditionStep(3);});
accountAdminViewBtn.addEventListener("click", showAccountAdminView);
saveSalesTargetBtn?.addEventListener("click", saveSalesTarget);
cancelSalesTargetBtn?.addEventListener("click", resetSalesTargetForm);
importSalesPromptBtn?.addEventListener("click", openSalesPromptFilePicker);
salesTargetPromptFileEl?.addEventListener("change", importSalesPromptFromFile);
saveCaseIdeaBtn?.addEventListener("click", saveCaseIdea);
cancelCaseIdeaBtn?.addEventListener("click", resetCaseIdeaForm);
createAccountBtn.addEventListener("click", openCreateAccountModal);
accountCreateCloseBtn.addEventListener("click", closeCreateAccountModal);
accountCreateCancelBtn.addEventListener("click", closeCreateAccountModal);
accountCreateSubmitBtn.addEventListener("click", createAccount);
saveConditionTemplateBtn?.addEventListener("click", saveConditionTemplate);
conditionFilterTypeEl?.addEventListener("change", () => {
  conditionPage = 1;
  renderConditionTemplates();
});
activeFlowFilterTypeEl?.addEventListener("change", renderActiveFlows);
activeFlowSearchEl?.addEventListener("input", renderActiveFlows);

addConditionTypeBtn?.addEventListener("click", openConditionTypeModal);
conditionTypeModalCloseBtn?.addEventListener("click", closeConditionTypeModal);
conditionTypeCancelBtn?.addEventListener("click", closeConditionTypeModal);
conditionTypeSaveBtn?.addEventListener("click", saveNewConditionType);

conditionTypeNameEl?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") saveNewConditionType();
});

conditionTypeModalEl?.addEventListener("click", (e) => {
  if (e.target === conditionTypeModalEl) closeConditionTypeModal();
});

saveConditionFlowBtn?.addEventListener("click", saveConditionFlow);
cancelFlowEditBtn?.addEventListener("click", cancelFlowEdit);
flowSearchEl?.addEventListener("input", renderConditionFlows);
flowNameEl?.addEventListener("input", updateFlowFieldCounts);
flowPromptTemplateEl?.addEventListener("input", updateFlowFieldCounts);
clearSelectedConditionsBtn?.addEventListener("click", clearSelectedConditions);

openFlowModalBtn?.addEventListener("click", () => {
  cancelFlowEdit();
  openFlowModal();
});

flowConditionKeywordEl
?.addEventListener(
"input",
renderConfirmedConditionLibrary
);

flowModalCloseBtn?.addEventListener("click", closeFlowModal);

flowModalEl?.addEventListener("click", (e) => {
  if (e.target === flowModalEl) closeFlowModal();
});

// dropdown mới
flowConditionSearchEl?.addEventListener("change", () => {
  // giữ trống để sau nếu cần
});

addSelectedConditionBtn?.addEventListener("click", () => {
  const selectEl = document.getElementById("flowConditionSearch");
  const id = Number(selectEl?.value);

  if (!id) {
    showToast("Vui lòng chọn điều kiện", "error");
    return;
  }

  addConditionToExpression(id);

  if (selectEl) selectEl.selectedIndex = 0;
});

document.getElementById("nextOperatorAnd")?.addEventListener("click", () => {
  nextOperator = "AND";
  document.getElementById("nextOperatorAnd")?.classList.add("active");
  document.getElementById("nextOperatorOr")?.classList.remove("active");
});

document.getElementById("nextOperatorOr")?.addEventListener("click", () => {
  nextOperator = "OR";
  document.getElementById("nextOperatorOr")?.classList.add("active");
  document.getElementById("nextOperatorAnd")?.classList.remove("active");
});

conditionSearchEl?.addEventListener("input", () => {
  conditionPage = 1;
  renderConditionTemplates();
});

accountCreateModalEl.addEventListener("click", (e) => {
  if (e.target === accountCreateModalEl) closeCreateAccountModal();
});

createUsernameEl.addEventListener("input", () => {
  if (!createDisplayNameEl.value.trim()) createDisplayNameEl.value = createUsernameEl.value.trim();
});

createPasswordEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") createAccount();
});

loginPasswordEl.addEventListener("keydown", (e) => { 
  if (e.key === "Enter") login();
});

loginUsernameEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") loginPasswordEl.focus();
});

flowConditionKeywordEl?.addEventListener("input", () => {
  renderConfirmedConditionLibrary();
});

document.addEventListener("click", (e) => {
  if (!accountMenuEl.contains(e.target)) closeAccountDropdown();
});

msgEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    send();
  }
});

setInterval(() => {
  refreshVisibleChatHistory();
}, 10000);

/* =========================
   Init
========================= */

document.addEventListener("DOMContentLoaded", async () => {
  await loadConditionTypes();

  await restoreAuthSession();

  if (currentAccount) {
    guestMode = false;
    await enterApp();
  } else {
    showAuthScreen();
  }
});
