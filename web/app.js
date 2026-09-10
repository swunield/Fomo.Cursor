const COLUMNS = [
  "名称",
  "市值",
  "持仓市值",
  "持仓人数",
  "人均持仓市值",
  "最高市值",
  "最高市值时间",
  "最高持仓人",
  "最高持仓市值",
  "最低持仓人",
  "最低持仓市值",
  "所有持仓人",
  "发射平台",
  "合约地址",
];

const LEGACY_COL_RENAME = {
  代币名称: "名称",
  代币当前市值: "市值",
  总持仓价值: "持仓市值",
  持仓价值: "持仓市值",
  总持仓人数: "持仓人数",
  人均持仓价值: "人均持仓市值",
  代币最高市值: "最高市值",
  代币最高市值时间: "最高市值时间",
  最高持仓价值: "最高持仓市值",
  最低持仓价值: "最低持仓市值",
};

const NUM_COLS = new Set([
  "市值",
  "持仓市值",
  "持仓人数",
  "人均持仓市值",
  "最高市值",
  "最高持仓市值",
  "最低持仓市值",
]);

const FILTER_STORAGE_KEY = "fomo_full_filters_v1";
const FILTER_FIELDS = [
  { key: "mcapMin", id: "flt-mcap-min" },
  { key: "mcapMax", id: "flt-mcap-max" },
  { key: "holdMin", id: "flt-hold-min" },
  { key: "holdMax", id: "flt-hold-max" },
  { key: "countMin", id: "flt-count-min" },
  { key: "countMax", id: "flt-count-max" },
];

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
const btnApplyFilter = document.getElementById("btn-apply-filter");
const btnResetFilter = document.getElementById("btn-reset-filter");
const filterSummary = document.getElementById("filter-summary");
const rowTip = document.getElementById("row-tip");

let pollTimer = null;
let activeMode = "fast";
let lastPayload = null;
let tipRowIndex = -1;

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

/** Parse numbers like 12.1M, 887K, 12.1M(2.44%), plain ints. */
function parseNumber(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  let text = String(value).trim().replace(/\$/g, "").replace(/,/g, "").replace(/\s/g, "");
  if (!text || text === "-") return null;
  text = text.replace(/\([^)]*%\)$/, "");
  let multiplier = 1;
  const upper = text.toUpperCase();
  if (upper.endsWith("B")) {
    multiplier = 1e9;
    text = text.slice(0, -1);
  } else if (upper.endsWith("M")) {
    multiplier = 1e6;
    text = text.slice(0, -1);
  } else if (upper.endsWith("K")) {
    multiplier = 1e3;
    text = text.slice(0, -1);
  }
  const n = Number(text);
  return Number.isFinite(n) ? n * multiplier : null;
}

function readFilterInputs() {
  const out = {};
  for (const f of FILTER_FIELDS) {
    out[f.key] = document.getElementById(f.id).value.trim();
  }
  return out;
}

function writeFilterInputs(values) {
  for (const f of FILTER_FIELDS) {
    document.getElementById(f.id).value = values?.[f.key] || "";
  }
}

function loadStoredFilters() {
  try {
    const raw = localStorage.getItem(FILTER_STORAGE_KEY);
    if (!raw) return;
    writeFilterInputs(JSON.parse(raw));
  } catch {
    /* ignore */
  }
}

function saveStoredFilters(values) {
  try {
    localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(values));
  } catch {
    /* ignore */
  }
}

function getActiveFilters() {
  const raw = readFilterInputs();
  return {
    mcapMin: parseNumber(raw.mcapMin),
    mcapMax: parseNumber(raw.mcapMax),
    holdMin: parseNumber(raw.holdMin),
    holdMax: parseNumber(raw.holdMax),
    countMin: parseNumber(raw.countMin),
    countMax: parseNumber(raw.countMax),
    raw,
  };
}

function hasAnyFilter(f) {
  return [f.mcapMin, f.mcapMax, f.holdMin, f.holdMax, f.countMin, f.countMax].some((v) => v != null);
}

function inRange(value, min, max) {
  if (min == null && max == null) return true;
  if (value == null || Number.isNaN(value)) return false;
  if (min != null && value < min) return false;
  if (max != null && value > max) return false;
  return true;
}

function filterRows(rows, mode) {
  if (mode !== "full") return { rows, filtered: false, total: rows.length };
  const f = getActiveFilters();
  if (!hasAnyFilter(f)) return { rows, filtered: false, total: rows.length };
  const out = rows.filter((row) => {
    const mcap = parseNumber(row["市值"]);
    const hold = parseNumber(row["持仓市值"]);
    const count = parseNumber(row["持仓人数"]);
    return (
      inRange(mcap, f.mcapMin, f.mcapMax) &&
      inRange(hold, f.holdMin, f.holdMax) &&
      inRange(count, f.countMin, f.countMax)
    );
  });
  return { rows: out, filtered: true, total: rows.length };
}

function updateFilterSummary(shown, total, mode, filtered) {
  if (mode !== "full") {
    filterSummary.textContent = "快速模式不应用筛选";
    return;
  }
  if (!filtered) {
    filterSummary.textContent = total ? `未筛选 · ${total} 条` : "";
    return;
  }
  filterSummary.textContent = `已筛选 · ${shown}/${total}`;
}

function renameLegacyRow(row) {
  if (!row || typeof row !== "object") return row;
  const out = {};
  for (const [k, v] of Object.entries(row)) {
    out[LEGACY_COL_RENAME[k] || k] = v;
  }
  return out;
}

function normalizePayload(payload) {
  if (!payload) return payload;
  const rows = (payload.rows || []).map(renameLegacyRow);
  return {
    ...payload,
    columns: COLUMNS.slice(),
    rows,
    tokenCount: payload.tokenCount || rows.length,
  };
}

function renderTable(payload) {
  payload = normalizePayload(payload);
  lastPayload = payload;
  const allRows = payload.rows || [];
  const mode = payload.mode || "fast";
  const { rows, filtered, total } = filterRows(allRows, mode);
  const cols = COLUMNS.slice();

  panelTitle.textContent = mode === "full" ? "Fomo总榜前20 · 全量" : "Fomo总榜前20 · 快速";
  panelNote.textContent =
    payload.note ||
    (mode === "full"
      ? "全量模式：官方 balances；市值本地缓存（单币≥10分钟）；最高市值缓存。"
      : "快速模式：spotlight 估算；市值本地缓存（单币≥10分钟）；最高市值优先缓存。");
  updatedAt.textContent = `更新 ${formatTime(payload.updatedAt)}`;
  tokenCount.textContent = filtered ? `${rows.length}/${total} tokens` : `${payload.tokenCount || rows.length} tokens`;
  modeChip.textContent = `mode ${mode}`;
  setActiveButton(mode);
  updateFilterSummary(rows.length, total, mode, filtered);

  if (!rows.length) {
    emptyState.classList.remove("hidden");
    tableWrap.classList.add("hidden");
    emptyState.querySelector("p").textContent =
      allRows.length && filtered ? "当前筛选无匹配行" : "尚未加载数据";
    return;
  }

  emptyState.classList.add("hidden");
  tableWrap.classList.remove("hidden");

  thead.innerHTML = `<tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr>`;
  hideRowTip();
  tbody.innerHTML = rows
    .map((row, idx) => {
      const tds = cols
        .map((c) => {
          let val = row[c] ?? "";
          if (c === "最高市值时间") val = shortenTime(val);
          let cls = "";
          if (NUM_COLS.has(c)) cls = "num";
          if (c === "所有持仓人") {
            cls = "holders";
            val = holdersTableText(val);
          }
          if (c === "合约地址") cls = "addr";
          const title = String(val).replace(/"/g, "&quot;");
          if (c === "名称") {
            const addr = String(row["合约地址"] || "").replace(/"/g, "&quot;");
            const nameHtml = escapeHtml(String(val));
            return `<td class="name-cell" title="${title}">
              <button type="button" class="copy-addr-btn" data-addr="${addr}" title="复制合约地址" aria-label="复制合约地址">⧉</button>
              <span class="name-text">${nameHtml}</span>
            </td>`;
          }
          return `<td class="${cls}" title="${title}">${escapeHtml(String(val))}</td>`;
        })
        .join("");
      return `<tr data-row-idx="${idx}">${tds}</tr>`;
    })
    .join("");
}

function hideRowTip() {
  tipRowIndex = -1;
  rowTip.classList.add("hidden");
  rowTip.innerHTML = "";
  tbody.querySelectorAll("tr.tip-active").forEach((tr) => tr.classList.remove("tip-active"));
}

function positionRowTip(clientX, clientY) {
  rowTip.classList.remove("hidden");
  const pad = 14;
  const rect = rowTip.getBoundingClientRect();
  let left = clientX + 14;
  let top = clientY + 14;
  if (left + rect.width > window.innerWidth - pad) {
    left = Math.max(pad, clientX - rect.width - 12);
  }
  if (top + rect.height > window.innerHeight - pad) {
    top = Math.max(pad, window.innerHeight - rect.height - pad);
  }
  rowTip.style.left = `${left}px`;
  rowTip.style.top = `${top}px`;
}

function holderTipLines(row) {
  const details = row["持仓明细"];
  if (Array.isArray(details) && details.length) {
    return details.map((x) => String(x).trim()).filter(Boolean);
  }
  if (typeof details === "string" && details.trim()) {
    return details.split(/\n+/).map((x) => x.trim()).filter(Boolean);
  }
  const all = String(row["所有持仓人"] || "").trim();
  if (!all) return ["—"];
  if (all.includes("\n")) {
    return all.split(/\n+/).map((x) => x.trim()).filter(Boolean);
  }
  // Rich single-line entries: "1.Name 6.2M(1.57%) 3.Foo 1K(0.01%)"
  const rich = [];
  const re = /(\d+)\.(.+?)\s+(\S+\([^)]*\))(?=\s+\d+\.|$)/g;
  let m;
  while ((m = re.exec(all)) !== null) {
    rich.push(`${m[1]}.${m[2].trim()} ${m[3]}`);
  }
  if (rich.length) return rich;
  return all.split(/\s+/).filter(Boolean);
}

function holdersTableText(val) {
  const text = String(val || "").trim();
  if (!text) return "";
  const lines = text.includes("\n")
    ? text.split(/\n+/).map((x) => x.trim()).filter(Boolean)
    : null;
  if (lines) {
    return lines
      .map((line) => line.replace(/\s+\S+\([^)]*\)\s*$/, "").trim())
      .filter(Boolean)
      .join(" ");
  }
  return text.replace(/(\d+\..+?)\s+\S+\([^)]*\)/g, "$1").replace(/\s+/g, " ").trim();
}

function showRowTip(row, tr, clientX, clientY) {
  const name = row["名称"] || "—";
  const hiPerson = row["最高持仓人"] || "—";
  const hiVal = row["最高持仓市值"] || "—";
  const loPerson = row["最低持仓人"] || "—";
  const loVal = row["最低持仓市值"] || "—";
  const holderLines = holderTipLines(row);

  tbody.querySelectorAll("tr.tip-active").forEach((el) => el.classList.remove("tip-active"));
  tr.classList.add("tip-active");
  tipRowIndex = Number(tr.dataset.rowIdx);

  const holdersHtml = holderLines
    .map((line) => `<div class="row-tip-holder">${escapeHtml(line)}</div>`)
    .join("");

  rowTip.innerHTML = `
    <div class="row-tip-line row-tip-name">${escapeHtml(String(name))}</div>
    <div class="row-tip-line"><span class="row-tip-label">最高</span>${escapeHtml(`${hiPerson}  ${hiVal}`)}</div>
    <div class="row-tip-line"><span class="row-tip-label">最低</span>${escapeHtml(`${loPerson}  ${loVal}`)}</div>
    <div class="row-tip-line">
      <span class="row-tip-label">全部</span>
      <div class="row-tip-holders">${holdersHtml}</div>
    </div>
  `;
  positionRowTip(clientX, clientY);
}

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function copyText(text) {
  if (!text) return false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fallback below */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  ta.remove();
  return ok;
}

function applyFilters() {
  const values = readFilterInputs();
  saveStoredFilters(values);
  if (lastPayload) renderTable(lastPayload);
  else updateFilterSummary(0, 0, activeMode, hasAnyFilter(getActiveFilters()));
}

function resetFilters() {
  writeFilterInputs({});
  saveStoredFilters({});
  if (lastPayload) renderTable(lastPayload);
  else filterSummary.textContent = "";
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
btnApplyFilter.addEventListener("click", applyFilters);
btnResetFilter.addEventListener("click", resetFilters);
for (const f of FILTER_FIELDS) {
  document.getElementById(f.id).addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyFilters();
  });
}

tbody.addEventListener("click", async (e) => {
  const btn = e.target.closest(".copy-addr-btn");
  if (btn) {
    e.preventDefault();
    e.stopPropagation();
    const addr = btn.getAttribute("data-addr") || "";
    const ok = await copyText(addr);
    if (!ok) {
      setJobStatus("复制失败", "error");
      return;
    }
    const prev = btn.textContent;
    btn.textContent = "✓";
    btn.classList.add("copied");
    setJobStatus(`已复制合约 · ${addr.slice(0, 8)}…${addr.slice(-4)}`);
    setTimeout(() => {
      btn.textContent = prev;
      btn.classList.remove("copied");
    }, 1200);
    return;
  }

  const tr = e.target.closest("tr[data-row-idx]");
  if (!tr || !lastPayload) return;
  const idx = Number(tr.dataset.rowIdx);
  const mode = lastPayload.mode || "fast";
  const { rows } = filterRows(lastPayload.rows || [], mode);
  const row = rows[idx];
  if (!row) return;

  if (tipRowIndex === idx && !rowTip.classList.contains("hidden")) {
    hideRowTip();
    return;
  }
  showRowTip(row, tr, e.clientX, e.clientY);
});

document.addEventListener("click", (e) => {
  if (e.target.closest("#data-table tbody") || e.target.closest("#row-tip")) return;
  hideRowTip();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") hideRowTip();
});

loadStoredFilters();
refreshAuthStatus();
loadCached();
