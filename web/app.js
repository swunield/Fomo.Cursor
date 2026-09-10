const COLUMNS = [
  "名称",
  "市值",
  "成交量",
  "24h涨跌",
  "持仓市值",
  "持仓人数",
  "人均持仓市值",
  "创建时间",
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
  "成交量",
  "24h涨跌",
  "持仓市值",
  "持仓人数",
  "人均持仓市值",
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

const boardSettings = { allLimit: 20, dayLimit: 50 };

const btnFast = document.getElementById("btn-top20");
const btn7d = document.getElementById("btn-7d");
const navButtons = [btnFast, btn7d].filter(Boolean);
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
const setAllLimit = document.getElementById("set-all-limit");
const setDayLimit = document.getElementById("set-day-limit");
const btnSaveSettings = document.getElementById("btn-save-settings");
const hintAllFast = document.getElementById("hint-all-fast");
const hint7dFast = document.getElementById("hint-7d-fast");

let pollTimer = null;
let activeMode = "fast";
let activeBoard = "all";
let lastPayload = null;
let tipRowIndex = -1;
let sortState = { col: null, dir: null }; // dir: 'asc' | 'desc'

function setJobStatus(text, mode = "") {
  jobStatus.textContent = text;
  jobStatus.className = "job-status" + (mode ? ` ${mode}` : "");
}

function showLoading(show, text = "正在拉取…") {
  loadingOverlay.classList.toggle("hidden", !show);
  loadingText.textContent = text;
  navButtons.forEach((btn) => {
    if (btn) btn.disabled = show;
  });
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

function boardLimit(board) {
  return board === "7d" ? boardSettings.dayLimit : boardSettings.allLimit;
}

function boardLabel(board) {
  const n = boardLimit(board);
  return board === "7d" ? `7日榜前${n}` : `总榜前${n}`;
}

function applySettingsToUi(s) {
  boardSettings.allLimit = Number(s.allLimit) || 20;
  boardSettings.dayLimit = Number(s.dayLimit) || 50;
  if (setAllLimit) setAllLimit.value = String(boardSettings.allLimit);
  if (setDayLimit) setDayLimit.value = String(boardSettings.dayLimit);
  if (hintAllFast) hintAllFast.textContent = `前${boardSettings.allLimit}`;
  if (hint7dFast) hint7dFast.textContent = `前${boardSettings.dayLimit}`;
}

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    if (data && data.ok) applySettingsToUi(data);
  } catch {
    applySettingsToUi(boardSettings);
  }
}

async function saveBoardSettings() {
  const allLimit = Number(setAllLimit?.value);
  const dayLimit = Number(setDayLimit?.value);
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ allLimit, dayLimit }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) throw new Error(data.detail || data.message || "保存设置失败");
  applySettingsToUi(data);
  setJobStatus(`设置已保存 · 总榜前${data.allLimit} / 日榜前${data.dayLimit}`);
}

function setActiveButton(board) {
  activeBoard = board === "7d" ? "7d" : "all";
  activeMode = "fast";
  navButtons.forEach((btn) => {
    if (!btn) return;
    const b = btn.dataset.board || "all";
    btn.classList.toggle("active", b === activeBoard);
  });
}

function filterRows(rows) {
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

function updateFilterSummary(shown, total, filtered) {
  if (!filtered) {
    filterSummary.textContent = total ? `未筛选 · ${total} 条` : "";
    return;
  }
  filterSummary.textContent = `已筛选 · ${shown}/${total}`;
}

/** Parse numbers like 12.1M, 887K, 12.1M(2.44%), plain ints. */
function parseNumber(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  let text = String(value).trim().replace(/\$/g, "").replace(/,/g, "").replace(/\s/g, "");
  if (!text || text === "-") return null;
  text = text.replace(/\([^)]*\)$/, "");
  if (text.endsWith("%")) text = text.slice(0, -1);
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

function compareSortValues(a, b, col, dir) {
  const mul = dir === "asc" ? 1 : -1;
  const av = a?.[col];
  const bv = b?.[col];
  if (NUM_COLS.has(col) || col === "创建时间") {
    const an = col === "创建时间" ? Date.parse(String(av || "")) || 0 : parseNumber(av);
    const bn = col === "创建时间" ? Date.parse(String(bv || "")) || 0 : parseNumber(bv);
    const aEmpty = an == null;
    const bEmpty = bn == null;
    if (aEmpty && bEmpty) return 0;
    if (aEmpty) return 1;
    if (bEmpty) return -1;
    if (an === bn) return 0;
    return an < bn ? -1 * mul : 1 * mul;
  }
  const as = String(av ?? "").trim();
  const bs = String(bv ?? "").trim();
  if (!as && !bs) return 0;
  if (!as) return 1;
  if (!bs) return -1;
  return as.localeCompare(bs, "zh-CN", { numeric: true, sensitivity: "base" }) * mul;
}

function sortRows(rows) {
  if (!sortState.col || !sortState.dir) return rows;
  const col = sortState.col;
  const dir = sortState.dir;
  return rows
    .map((row, i) => ({ row, i }))
    .sort((x, y) => {
      const c = compareSortValues(x.row, y.row, col, dir);
      return c !== 0 ? c : x.i - y.i;
    })
    .map((x) => x.row);
}

function sortIndicator(col) {
  if (sortState.col !== col || !sortState.dir) return "";
  return sortState.dir === "asc" ? " ↑" : " ↓";
}

function onHeaderClick(col) {
  if (sortState.col !== col) {
    sortState = {
      col,
      dir: NUM_COLS.has(col) || col === "创建时间" ? "desc" : "asc",
    };
  } else if (sortState.dir === "desc") {
    sortState = { col, dir: "asc" };
  } else if (sortState.dir === "asc") {
    sortState = { col: null, dir: null };
  } else {
    sortState = { col, dir: "desc" };
  }
  if (lastPayload) renderTable(lastPayload);
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
  const board = payload.board || activeBoard || "all";
  const label = payload.boardLabel || boardLabel(board);
  const filteredResult = filterRows(allRows);
  const rows = sortRows(filteredResult.rows);
  const filtered = filteredResult.filtered;
  const total = filteredResult.total;
  const cols = COLUMNS.slice();

  panelTitle.textContent = label;
  panelNote.textContent =
    payload.note ||
    `${label}：登录态用 balances 实时开仓；未登录才用 spotlight（可能滞后）。`;
  updatedAt.textContent = `更新 ${formatTime(payload.updatedAt)}`;
  tokenCount.textContent = filtered ? `${rows.length}/${total} tokens` : `${payload.tokenCount || rows.length} tokens`;
  modeChip.textContent = board === "7d" ? "7d" : "all";
  setActiveButton(board);
  updateFilterSummary(rows.length, total, filtered);

  if (!rows.length) {
    emptyState.classList.remove("hidden");
    tableWrap.classList.add("hidden");
    emptyState.querySelector("p").textContent =
      allRows.length && filtered ? "当前筛选无匹配行" : "尚未加载数据";
    return;
  }

  emptyState.classList.add("hidden");
  tableWrap.classList.remove("hidden");

  thead.innerHTML = `<tr>${cols
    .map((c) => {
      const active = sortState.col === c && sortState.dir ? " sorted" : "";
      const aria =
        sortState.col === c && sortState.dir
          ? ` aria-sort="${sortState.dir === "asc" ? "ascending" : "descending"}"`
          : ' aria-sort="none"';
      return `<th class="sortable${active}" data-col="${escapeHtml(c)}"${aria} title="点击排序"><span class="th-label">${escapeHtml(c)}</span><span class="th-sort">${sortIndicator(c)}</span></th>`;
    })
    .join("")}</tr>`;
  hideRowTip();
  tbody.innerHTML = rows
    .map((row, idx) => {
      const tds = cols
        .map((c) => {
          let val = row[c] ?? "";
          if (c === "创建时间") val = shortenTime(val);
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
  const platform = row["发射平台"] || "—";
  const createdAt = shortenTime(row["创建时间"]) || "—";
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
    <div class="row-tip-line"><span class="row-tip-label">平台</span>${escapeHtml(String(platform))}</div>
    <div class="row-tip-line"><span class="row-tip-label">创建时间</span>${escapeHtml(String(createdAt))}</div>
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
  else updateFilterSummary(0, 0, hasAnyFilter(getActiveFilters()));
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

async function loadCached(board = activeBoard) {
  try {
    const res = await fetch(`/api/fomo-top20/cached?board=${encodeURIComponent(board)}`);
    const data = await res.json();
    if (data.ok && data.rows && data.rows.length) {
      renderTable(data);
      setJobStatus(`缓存 · ${formatTime(data.updatedAt)}`);
      return true;
    }
    return false;
  } catch (e) {
    setJobStatus("缓存读取失败", "error");
    return false;
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
    setActiveButton(activeBoard);
    return;
  }

  const board = st.board || activeBoard;
  const resultRes = await fetch(`/api/fomo-top20/result?board=${encodeURIComponent(board)}`);
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

async function refreshBoard(board) {
  activeBoard = board === "7d" ? "7d" : "all";
  activeMode = "fast";
  setActiveButton(activeBoard);
  const limit = boardLimit(activeBoard);
  const label = boardLabel(activeBoard);
  showLoading(true, `${label} 拉取中…`);
  setJobStatus(`${label} 刷新…`, "running");
  if (pollTimer) clearTimeout(pollTimer);

  try {
    const res = await fetch("/api/fomo-top20/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "fast", board: activeBoard, limit }),
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

btnFast.addEventListener("click", () => refreshBoard("all"));
btn7d.addEventListener("click", () => refreshBoard("7d"));
btnSaveAuth.addEventListener("click", () => saveAuth().catch((e) => setJobStatus(String(e), "error")));
btnClearAuth.addEventListener("click", () => clearAuth().catch((e) => setJobStatus(String(e), "error")));
btnSaveSettings.addEventListener("click", () =>
  saveBoardSettings().catch((e) => setJobStatus(String(e), "error"))
);
btnApplyFilter.addEventListener("click", applyFilters);
btnResetFilter.addEventListener("click", resetFilters);
for (const f of FILTER_FIELDS) {
  document.getElementById(f.id).addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyFilters();
  });
}
[setAllLimit, setDayLimit].forEach((el) => {
  if (!el) return;
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      saveBoardSettings().catch((err) => setJobStatus(String(err), "error"));
    }
  });
});

function getDisplayRows(payload = lastPayload) {
  if (!payload) return [];
  const { rows } = filterRows(payload.rows || []);
  return sortRows(rows);
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
  const rows = getDisplayRows(lastPayload);
  const row = rows[idx];
  if (!row) return;

  if (tipRowIndex === idx && !rowTip.classList.contains("hidden")) {
    hideRowTip();
    return;
  }
  showRowTip(row, tr, e.clientX, e.clientY);
});

thead.addEventListener("click", (e) => {
  const th = e.target.closest("th.sortable[data-col]");
  if (!th) return;
  onHeaderClick(th.getAttribute("data-col"));
});

document.addEventListener("click", (e) => {
  if (e.target.closest("#data-table tbody") || e.target.closest("#row-tip")) return;
  hideRowTip();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") hideRowTip();
});

loadStoredFilters();
loadSettings().then(() => {
  refreshAuthStatus();
  loadCached();
});
