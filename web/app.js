const COLUMNS = [
  "代币名称",
  "代币当前市值",
  "总持仓价值",
  "总持仓人数",
  "人均持仓价值",
  "代币最高市值",
  "代币最高市值时间",
  "最高持仓人",
  "最高持仓价值",
  "最低持仓人",
  "最低持仓价值",
  "所有持仓人",
  "发射平台",
  "合约地址",
];

const NUM_COLS = new Set([
  "代币当前市值",
  "总持仓价值",
  "总持仓人数",
  "人均持仓价值",
  "代币最高市值",
  "最高持仓价值",
  "最低持仓价值",
]);

const btnFast = document.getElementById("btn-top20");
const btnFull = document.getElementById("btn-top20-full");
const jobStatus = document.getElementById("job-status");
const panelTitle = document.getElementById("panel-title");
const panelNote = document.getElementById("panel-note");
const updatedAt = document.getElementById("updated-at");
const tokenCount = document.getElementById("token-count");
const modeChip = document.getElementById("mode-chip");
const emptyState = document.getElementById("empty-state");
const tableWrap = document.getElementById("table-wrap");
const thead = document.querySelector("#data-table thead");
const tbody = document.querySelector("#data-table tbody");
const loadingOverlay = document.getElementById("loading-overlay");
const loadingText = document.getElementById("loading-text");
const authStatus = document.getElementById("auth-status");
const authToken = document.getElementById("auth-token");
const btnSaveAuth = document.getElementById("btn-save-auth");
const btnClearAuth = document.getElementById("btn-clear-auth");

let pollTimer = null;
let activeMode = "fast";

function setJobStatus(text, mode = "") {
  jobStatus.textContent = text;
  jobStatus.className = "job-status" + (mode ? ` ${mode}` : "");
}

function showLoading(show, text = "正在拉取…") {
  loadingOverlay.classList.toggle("hidden", !show);
  loadingText.textContent = text;
  btnFast.disabled = show;
  btnFull.disabled = show;
}

function formatTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 19);
    return d.toLocaleString("zh-CN", { hour12: false });
  } catch {
    return String(iso).slice(0, 19);
  }
}

function shortenTime(val) {
  if (!val) return "";
  const s = String(val);
  if (s.includes("T")) return s.slice(0, 19).replace("T", " ");
  return s;
}

function setActiveButton(mode) {
  btnFast.classList.toggle("active", mode === "fast");
  btnFull.classList.toggle("active", mode === "full");
}

function renderTable(payload) {
  const rows = payload.rows || [];
  const columns = (payload.columns && payload.columns.length ? payload.columns : COLUMNS).filter(
    (c) => COLUMNS.includes(c) || (rows[0] && c in rows[0])
  );
  const cols = COLUMNS.filter((c) => columns.includes(c) || (rows[0] && c in rows[0]));
  const mode = payload.mode || "fast";

  panelTitle.textContent = mode === "full" ? "Fomo总榜前20 · 全量" : "Fomo总榜前20 · 快速";
  panelNote.textContent =
    payload.note ||
    (mode === "full"
      ? "全量模式：官方 balances；当前市值 DexScreener；最高市值缓存。"
      : "快速模式：spotlight 估算；当前市值实时；最高市值优先缓存。");
  updatedAt.textContent = `更新 ${formatTime(payload.updatedAt)}`;
  tokenCount.textContent = `${payload.tokenCount || rows.length} tokens`;
  modeChip.textContent = `mode ${mode}`;
  setActiveButton(mode);

  if (!rows.length) {
    emptyState.classList.remove("hidden");
    tableWrap.classList.add("hidden");
    return;
  }

  emptyState.classList.add("hidden");
  tableWrap.classList.remove("hidden");

  thead.innerHTML = `<tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr>`;
  tbody.innerHTML = rows
    .map((row) => {
      const tds = cols
        .map((c) => {
          let val = row[c] ?? "";
          if (c === "代币最高市值时间") val = shortenTime(val);
          let cls = "";
          if (NUM_COLS.has(c)) cls = "num";
          if (c === "所有持仓人") cls = "holders";
          if (c === "合约地址") cls = "addr";
          return `<td class="${cls}" title="${String(val).replace(/"/g, "&quot;")}">${val}</td>`;
        })
        .join("");
      return `<tr>${tds}</tr>`;
    })
    .join("");
}

async function refreshAuthStatus() {
  try {
    const res = await fetch("/api/auth/status");
    const data = await res.json();
    if (data.configured) {
      authStatus.textContent = `已配置 · ${data.tokenPreview}`;
      authStatus.className = "auth-status ok";
    } else {
      authStatus.textContent = "未配置 Token";
      authStatus.className = "auth-status bad";
    }
  } catch {
    authStatus.textContent = "状态读取失败";
    authStatus.className = "auth-status bad";
  }
}

async function saveAuth() {
  const token = authToken.value.trim();
  if (!token) {
    authStatus.textContent = "请先粘贴 Token";
    authStatus.className = "auth-status bad";
    return;
  }
  const res = await fetch("/api/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accessToken: token }),
  });
  const data = await res.json();
  authToken.value = "";
  await refreshAuthStatus();
  if (data.test && data.test.ok === false) {
    const hint = data.test.hint ? ` ${data.test.hint}` : "";
    authStatus.textContent = `已保存，但校验失败：${data.test.error || "unknown"} (HTTP ${data.test.statusCode || "?"}).${hint}`;
    authStatus.className = "auth-status bad";
  } else if (data.test && data.test.ok) {
    authStatus.textContent = `已保存并校验通过 · ${data.tokenPreview}`;
    authStatus.className = "auth-status ok";
  }
}

async function clearAuth() {
  await fetch("/api/auth/clear", { method: "POST" });
  authToken.value = "";
  await refreshAuthStatus();
}

async function loadCached() {
  try {
    const res = await fetch("/api/fomo-top20/cached");
    const data = await res.json();
    if (data.ok && data.rows && data.rows.length) {
      renderTable(data);
      setJobStatus(`缓存 · ${formatTime(data.updatedAt)}`);
    }
  } catch (e) {
    setJobStatus("缓存读取失败", "error");
  }
}

async function pollUntilDone() {
  const res = await fetch("/api/fomo-top20/status");
  const st = await res.json();
  setJobStatus(st.progress || st.status, st.status === "error" ? "error" : "running");
  loadingText.textContent = st.progress || "正在拉取…";

  if (st.status === "running") {
    pollTimer = setTimeout(pollUntilDone, 900);
    return;
  }

  showLoading(false);
  if (st.status === "error") {
    setJobStatus(st.error || "失败", "error");
    setActiveButton(activeMode);
    return;
  }

  const resultRes = await fetch("/api/fomo-top20/result");
  if (!resultRes.ok) {
    const err = await resultRes.json().catch(() => ({}));
    setJobStatus(err.detail || "获取结果失败", "error");
    return;
  }
  const payload = await resultRes.json();
  renderTable(payload);
  const fail = payload.stats?.tradersFail ? ` · fail ${payload.stats.tradersFail}` : "";
  setJobStatus(`完成 · ${payload.elapsedSec ?? "?"}s${fail}`);
}

async function refreshTop20(mode) {
  activeMode = mode;
  setActiveButton(mode);
  showLoading(true, mode === "full" ? "全量拉取中…" : "快速拉取中…");
  setJobStatus(mode === "full" ? "全量刷新…" : "快速刷新…", "running");
  if (pollTimer) clearTimeout(pollTimer);

  try {
    const res = await fetch("/api/fomo-top20/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || "无法启动刷新");
    if (!data.ok) throw new Error(data.message || "无法启动刷新");
    pollUntilDone();
  } catch (e) {
    showLoading(false);
    setJobStatus(e.message || String(e), "error");
  }
}

btnFast.addEventListener("click", () => refreshTop20("fast"));
btnFull.addEventListener("click", () => refreshTop20("full"));
btnSaveAuth.addEventListener("click", () => saveAuth().catch((e) => setJobStatus(String(e), "error")));
btnClearAuth.addEventListener("click", () => clearAuth().catch((e) => setJobStatus(String(e), "error")));

refreshAuthStatus();
loadCached();
