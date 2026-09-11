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

const boardSettings = { allLimit: 20, dayLimit: 50, h24Limit: 50 };

const btnFast = document.getElementById("btn-top20");
const btn7d = document.getElementById("btn-7d");
const btn24h = document.getElementById("btn-24h");
const navButtons = [btnFast, btn7d, btn24h].filter(Boolean);
const jobStatus = document.getElementById("job-status");
const panelTitle = document.getElementById("panel-title");
const panelNote = document.getElementById("panel-note");
const updatedAt = document.getElementById("updated-at");
const tokenCount = document.getElementById("token-count");
const modeChip = document.getElementById("mode-chip");
const emptyState = document.getElementById("empty-state");
const tableWrap = document.getElementById("table-wrap");
const cardList = document.getElementById("card-list");
const thead = document.querySelector("#data-table thead");
const tbody = document.querySelector("#data-table tbody");
const loadingOverlay = document.getElementById("loading-overlay");
const loadingText = document.getElementById("loading-text");
const authStatus = document.getElementById("auth-status");
const authToken = document.getElementById("auth-token");
const btnSaveAuth = document.getElementById("btn-save-auth");
const btnClearAuth = document.getElementById("btn-clear-auth");
const btnGoogleAuth = document.getElementById("btn-google-auth");
const btnCancelGoogle = document.getElementById("btn-cancel-google");
const oauthGoogleLink = document.getElementById("oauth-google-link");
const btnCloseSidebar = document.getElementById("btn-close-sidebar");
const btnApplyFilter = document.getElementById("btn-apply-filter");
const btnResetFilter = document.getElementById("btn-reset-filter");
const filterSummary = document.getElementById("filter-summary");
const rowTip = document.getElementById("row-tip");
const setAllLimit = document.getElementById("set-all-limit");
const setDayLimit = document.getElementById("set-day-limit");
const setH24Limit = document.getElementById("set-h24-limit");
const btnSaveSettings = document.getElementById("btn-save-settings");
const btnOpenSettings = document.getElementById("btn-open-settings");
const btnCloseSettings = document.getElementById("btn-close-settings");
const settingsOverlay = document.getElementById("settings-overlay");
const settingsHint = document.getElementById("settings-btn-hint");
const hintAllFast = document.getElementById("hint-all-fast");
const hint7dFast = document.getElementById("hint-7d-fast");
const hint24hFast = document.getElementById("hint-24h-fast");
const btnRefreshBoard = document.getElementById("btn-refresh-board");
const btnMobileRefresh = document.getElementById("btn-mobile-refresh");
const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
const sidebarEl = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");
const mobileSort = document.getElementById("mobile-sort");
const fetchStatusEl = document.getElementById("fetch-status");

const CACHE_STALE_MS = 10 * 60 * 1000;

let pollTimer = null;
let activeMode = "fast";
let activeBoard = "all";
let lastPayload = null;
let tipRowIndex = -1;
let sortState = { col: null, dir: null }; // dir: 'asc' | 'desc'
let refreshTargetBoard = null;
let refreshSilent = false;
let refreshBusy = false;
let googlePollTimer = null;
let googleLoginBusy = false;

function setJobStatus(text, mode = "") {
  jobStatus.textContent = text;
  jobStatus.className = "job-status" + (mode ? ` ${mode}` : "");
}

function setFetchStatus(text, mode = "") {
  if (!fetchStatusEl) return;
  fetchStatusEl.textContent = text || "";
  fetchStatusEl.className = "fetch-status" + (mode ? ` ${mode}` : "");
}

function isSidebarOpen() {
  return document.body.classList.contains("sidebar-open");
}

function openSidebar() {
  document.body.classList.add("sidebar-open");
  sidebarBackdrop?.classList.remove("hidden");
  if (btnToggleSidebar) btnToggleSidebar.setAttribute("aria-label", "关闭菜单");
}

function closeSidebar() {
  document.body.classList.remove("sidebar-open");
  sidebarBackdrop?.classList.add("hidden");
  if (btnToggleSidebar) btnToggleSidebar.setAttribute("aria-label", "打开菜单");
}

function toggleSidebar() {
  if (isSidebarOpen()) closeSidebar();
  else openSidebar();
}

function setRefreshBusy(busy) {
  refreshBusy = !!busy;
  if (btnRefreshBoard) btnRefreshBoard.disabled = refreshBusy;
  if (btnMobileRefresh) btnMobileRefresh.disabled = refreshBusy;
}

function showLoading(show, text = "正在拉取…") {
  // 保留 DOM，但榜单拉取改为顶部文字进度，不再用遮罩打断浏览
  if (loadingOverlay) loadingOverlay.classList.add("hidden");
  if (loadingText) loadingText.textContent = text;
}

function cacheAgeMs(iso) {
  if (!iso) return Number.POSITIVE_INFINITY;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return Number.POSITIVE_INFINITY;
  return Date.now() - t;
}

function isCacheStale(iso) {
  return cacheAgeMs(iso) > CACHE_STALE_MS;
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

function normalizeBoard(board) {
  if (board === "7d") return "7d";
  if (board === "24h") return "24h";
  return "all";
}

function boardLimit(board) {
  const b = normalizeBoard(board);
  if (b === "7d") return boardSettings.dayLimit;
  if (b === "24h") return boardSettings.h24Limit;
  return boardSettings.allLimit;
}

function boardLabel(board) {
  const b = normalizeBoard(board);
  const n = boardLimit(b);
  if (b === "7d") return `7日榜前${n}`;
  if (b === "24h") return `24小时榜前${n}`;
  return `总榜前${n}`;
}

function applySettingsToUi(s) {
  boardSettings.allLimit = Number(s.allLimit) || 20;
  boardSettings.dayLimit = Number(s.dayLimit) || 50;
  boardSettings.h24Limit = Number(s.h24Limit) || 50;
  if (setAllLimit) setAllLimit.value = String(boardSettings.allLimit);
  if (setDayLimit) setDayLimit.value = String(boardSettings.dayLimit);
  if (setH24Limit) setH24Limit.value = String(boardSettings.h24Limit);
  if (hintAllFast) hintAllFast.textContent = `前${boardSettings.allLimit}`;
  if (hint7dFast) hint7dFast.textContent = `前${boardSettings.dayLimit}`;
  if (hint24hFast) hint24hFast.textContent = `前${boardSettings.h24Limit}`;
  updateSettingsHint();
}

function isSettingsOpen() {
  return !!(settingsOverlay && !settingsOverlay.classList.contains("hidden"));
}

function openSettings() {
  if (!settingsOverlay) return;
  hideRowTip();
  closeSidebar();
  settingsOverlay.classList.remove("hidden");
  document.body.classList.add("settings-open");
  btnOpenSettings?.classList.add("is-open");
  const first = settingsOverlay.querySelector("input");
  if (first) first.focus();
}

function closeSettings() {
  if (!settingsOverlay) return;
  settingsOverlay.classList.add("hidden");
  document.body.classList.remove("settings-open");
  btnOpenSettings?.classList.remove("is-open");
}

function updateSettingsHint() {
  if (!settingsHint) return;
  const filtered = hasAnyFilter(getActiveFilters());
  settingsHint.textContent = filtered
    ? `有筛选 · 榜 ${boardSettings.allLimit}/${boardSettings.dayLimit}/${boardSettings.h24Limit}`
    : `榜 ${boardSettings.allLimit}/${boardSettings.dayLimit}/${boardSettings.h24Limit}`;
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
  const h24Limit = Number(setH24Limit?.value);
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ allLimit, dayLimit, h24Limit }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) throw new Error(data.detail || data.message || "保存设置失败");
  applySettingsToUi(data);
  setJobStatus(
    `设置已保存 · 总榜前${data.allLimit} / 7日前${data.dayLimit} / 24h前${data.h24Limit}`
  );
}

function setActiveButton(board) {
  activeBoard = normalizeBoard(board);
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
  if (filterSummary) {
    if (!filtered) {
      filterSummary.textContent = total ? `未筛选 · ${total} 条` : "";
    } else {
      filterSummary.textContent = `已筛选 · ${shown}/${total}`;
    }
  }
  updateSettingsHint();
}

/** Parse numbers like 12.1M, 887K, 12.1M(2.44%), plain ints. */
function parseNumber(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  let text = String(value).trim().replace(/\$/g, "").replace(/,/g, "").replace(/\s/g, "");
  if (!text || text === "-") return null;
  text = text.replace(/\([^)]*\)$/, "");
  if (text.endsWith("%")) text = text.slice(0, -1);
  text = text.replace(/^\+/, "");
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
  else renderSortChips();
}

function clearSort() {
  sortState = { col: null, dir: null };
  if (lastPayload) renderTable(lastPayload);
  else renderSortChips();
}

function renderSortChips() {
  if (!mobileSort) return;
  const chips = [
    `<button type="button" class="sort-chip${sortState.col ? "" : " active"}" data-sort="default">默认</button>`,
  ];
  for (const col of COLUMNS) {
    const active = sortState.col === col && sortState.dir;
    const dir = active ? (sortState.dir === "asc" ? "↑" : "↓") : "";
    chips.push(
      `<button type="button" class="sort-chip${active ? " active" : ""}" data-col="${escapeHtml(col)}">${escapeHtml(col)}${dir ? `<span class="sort-chip-dir">${dir}</span>` : ""}</button>`
    );
  }
  mobileSort.innerHTML = chips.join("");
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
  modeChip.textContent = normalizeBoard(board);
  setActiveButton(board);
  updateFilterSummary(rows.length, total, filtered);
  renderSortChips();

  if (!rows.length) {
    emptyState.classList.remove("hidden");
    tableWrap.classList.add("hidden");
    cardList?.classList.add("hidden");
    if (cardList) cardList.innerHTML = "";
    emptyState.querySelector("p").textContent =
      allRows.length && filtered ? "当前筛选无匹配行" : "尚未加载数据";
    return;
  }

  emptyState.classList.add("hidden");
  tableWrap.classList.remove("hidden");
  renderCards(rows);

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
          if (c === "24h涨跌") {
            const n = parseNumber(val);
            cls = "num chg";
            if (n != null && n > 0) cls += " chg-up";
            else if (n != null && n < 0) cls += " chg-down";
            else cls += " chg-flat";
          }
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

function chgClass(val) {
  const n = parseNumber(val);
  if (n != null && n > 0) return "chg-up";
  if (n != null && n < 0) return "chg-down";
  return "chg-flat";
}

function renderCards(rows) {
  if (!cardList) return;
  if (!rows.length) {
    cardList.classList.add("hidden");
    cardList.innerHTML = "";
    return;
  }
  cardList.classList.remove("hidden");
  cardList.innerHTML = rows
    .map((row, idx) => {
      const addr = String(row["合约地址"] || "").replace(/"/g, "&quot;");
      const chg = row["24h涨跌"] ?? "";
      return `<article class="token-card" data-row-idx="${idx}">
        <div class="token-card-head">
          <button type="button" class="copy-addr-btn" data-addr="${addr}" title="复制合约地址" aria-label="复制合约地址">⧉</button>
          <div class="token-card-name">${escapeHtml(String(row["名称"] ?? ""))}</div>
          <div class="num chg ${chgClass(chg)}">${escapeHtml(String(chg))}</div>
        </div>
        <dl class="token-card-grid">
          <div class="token-card-item"><dt>市值</dt><dd>${escapeHtml(String(row["市值"] ?? "—"))}</dd></div>
          <div class="token-card-item"><dt>成交量</dt><dd>${escapeHtml(String(row["成交量"] ?? "—"))}</dd></div>
          <div class="token-card-item"><dt>持仓市值</dt><dd>${escapeHtml(String(row["持仓市值"] ?? "—"))}</dd></div>
          <div class="token-card-item"><dt>持仓人数</dt><dd>${escapeHtml(String(row["持仓人数"] ?? "—"))}</dd></div>
        </dl>
        <p class="token-card-holders">${escapeHtml(holdersTableText(row["所有持仓人"]))}</p>
        <p class="token-card-meta">${escapeHtml(String(row["发射平台"] ?? ""))} · ${escapeHtml(shortenTime(row["创建时间"]))}</p>
      </article>`;
    })
    .join("");
}

function hideRowTip() {
  tipRowIndex = -1;
  rowTip.classList.add("hidden");
  rowTip.innerHTML = "";
  tbody.querySelectorAll("tr.tip-active").forEach((tr) => tr.classList.remove("tip-active"));
  cardList?.querySelectorAll(".token-card.tip-active").forEach((el) => el.classList.remove("tip-active"));
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
      .map((line) => line.replace(/\s+\S+\([^)]*\).*$/, "").trim())
      .filter(Boolean)
      .join(" ");
  }
  return text.replace(/(\d+\..+?)\s+\S+\([^)]*\).*/g, "$1").replace(/\s+/g, " ").trim();
}

function parseHolderTipParts(line) {
  const text = String(line || "").trim();
  const m = text.match(
    /^(\d+\..+?)\s+(\S+\([^)]*\))(?:\s+([+\-]?[\d.]+[KMB]?\([+\-]?\d+(?:\.\d+)?%\)))?(?:\s+(\[\d+:\d{2}:\d{2}\]))?(?:\s+(\[\d{8}\s+\d{2}:\d{2}\]))?\s*$/i
  );
  if (!m) {
    return { who: text, hold: "", pnl: "", dur: "", upd: "" };
  }
  return {
    who: m[1] || "",
    hold: m[2] || "",
    pnl: m[3] || "",
    dur: m[4] || "",
    upd: m[5] || "",
  };
}

function renderHolderTipRow(line) {
  const parts = parseHolderTipParts(line);
  const n = parts.pnl ? parseNumber(parts.pnl) : null;
  let pnlCls = "tip-col tip-pnl chg-flat";
  if (n != null && n > 0) pnlCls = "tip-col tip-pnl chg-up";
  else if (n != null && n < 0) pnlCls = "tip-col tip-pnl chg-down";
  return `<div class="row-tip-holder-row">
    <span class="tip-col tip-who">${escapeHtml(parts.who)}</span>
    <span class="tip-col tip-hold">${escapeHtml(parts.hold)}</span>
    <span class="${pnlCls}">${escapeHtml(parts.pnl)}</span>
    <span class="tip-col tip-dur">${escapeHtml(parts.dur)}</span>
    <span class="tip-col tip-upd">${escapeHtml(parts.upd)}</span>
  </div>`;
}

function showRowTip(row, tr, clientX, clientY) {
  const name = row["名称"] || "—";
  const platform = row["发射平台"] || "—";
  const createdAt = shortenTime(row["创建时间"]) || "—";
  const holderLines = holderTipLines(row);

  tbody.querySelectorAll("tr.tip-active").forEach((el) => el.classList.remove("tip-active"));
  cardList?.querySelectorAll(".token-card.tip-active").forEach((el) => el.classList.remove("tip-active"));
  tr.classList.add("tip-active");
  tipRowIndex = Number(tr.dataset.rowIdx);

  const holdersHtml = holderLines.length
    ? `<div class="row-tip-holder-grid">${holderLines.map(renderHolderTipRow).join("")}</div>`
    : `<div class="row-tip-holder">—</div>`;

  rowTip.innerHTML = `
    <div class="row-tip-line row-tip-name">${escapeHtml(String(name))}</div>
    <div class="row-tip-line"><span class="row-tip-label">平台</span>${escapeHtml(String(platform))}</div>
    <div class="row-tip-line"><span class="row-tip-label">创建时间</span>${escapeHtml(String(createdAt))}</div>
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
  else {
    updateFilterSummary(0, 0, false);
    updateSettingsHint();
  }
}

async function refreshAuthStatus() {
  try {
    const res = await fetch("/api/auth/status");
    const data = await res.json();
    if (data.configured) {
      const expired = data.tokenExpired ? "（已过期，将尝试自动续期）" : "";
      const refresh = data.hasRefresh ? " · 可自动续期" : "";
      authStatus.textContent = `已配置 · ${data.tokenPreview}${expired}${refresh}`;
      authStatus.className = data.tokenExpired ? "auth-status bad" : "auth-status ok";
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
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = Array.isArray(detail) ? detail.map((x) => x.msg || x).join("; ") : detail || data.message || "保存失败";
    authStatus.textContent = String(msg);
    authStatus.className = "auth-status bad";
    return;
  }
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

function hideOauthGoogleLink() {
  if (!oauthGoogleLink) return;
  oauthGoogleLink.classList.add("hidden");
  oauthGoogleLink.removeAttribute("href");
  oauthGoogleLink.textContent = "打开 Google 授权";
}

function isMobileBrowser() {
  return (
    window.matchMedia("(max-width: 860px)").matches ||
    /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || "")
  );
}

function setGoogleLoginBusy(busy) {
  googleLoginBusy = !!busy;
  if (btnGoogleAuth) {
    btnGoogleAuth.disabled = googleLoginBusy;
    btnGoogleAuth.textContent = googleLoginBusy ? "等待登录…" : "用 Google 登录";
  }
  if (btnCancelGoogle) {
    btnCancelGoogle.classList.toggle("hidden", !googleLoginBusy);
  }
}

function stopGooglePoll() {
  if (googlePollTimer) {
    clearTimeout(googlePollTimer);
    googlePollTimer = null;
  }
}

async function startGoogleLogin() {
  stopGooglePoll();
  hideOauthGoogleLink();
  setGoogleLoginBusy(true);
  authStatus.textContent = "正在准备 Google 授权…";
  authStatus.className = "auth-status pending";
  const mobile = isMobileBrowser();
  let popup = null;
  if (!mobile) {
    try {
      popup = window.open("about:blank", "fomo-google-oauth");
    } catch {
      popup = null;
    }
  }
  try {
    const res = await fetch("/api/auth/google/start", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || "无法启动 Google 登录");
    const url = data.url;
    if (!url) throw new Error("未返回授权地址");
    if (popup && !popup.closed) {
      popup.location.href = url;
    } else if (popup) {
      popup.close();
    }
    if (oauthGoogleLink) {
      oauthGoogleLink.href = url;
      oauthGoogleLink.classList.remove("hidden");
      oauthGoogleLink.textContent = mobile
        ? "打开 Google 授权（请留在浏览器）"
        : "打开 Google 授权";
    }
    authStatus.textContent =
      data.progress ||
      "请用 Google 登录。完成后留在浏览器，复制地址栏完整链接贴回保存；不要打开 FOMO App";
    authStatus.className = "auth-status pending";
    setGoogleLoginBusy(false);
    if (authToken) {
      authToken.placeholder = "粘贴浏览器地址栏完整链接（含 privy_oauth_code）";
      if (!mobile) authToken.focus();
    }
  } catch (e) {
    if (popup && !popup.closed) popup.close();
    hideOauthGoogleLink();
    setGoogleLoginBusy(false);
    authStatus.textContent = e.message || String(e);
    authStatus.className = "auth-status bad";
  }
}

async function cancelGoogleLogin() {
  stopGooglePoll();
  hideOauthGoogleLink();
  setGoogleLoginBusy(false);
  await refreshAuthStatus();
}

async function loadCached(board = activeBoard) {
  try {
    const res = await fetch(`/api/fomo-top20/cached?board=${encodeURIComponent(board)}`);
    const data = await res.json();
    if (data.ok && data.rows && data.rows.length) {
      renderTable(data);
      setJobStatus(`缓存 · ${formatTime(data.updatedAt)}`);
      return data;
    }
    return null;
  } catch (e) {
    setJobStatus("缓存读取失败", "error");
    return null;
  }
}

async function pollUntilDone() {
  const res = await fetch("/api/fomo-top20/status");
  const st = await res.json();
  const jobBoard = normalizeBoard(st.board || refreshTargetBoard || activeBoard);
  const progress = st.progress || st.status || "";
  setJobStatus(progress, st.status === "error" ? "error" : "running");

  if (st.status === "running") {
    setRefreshBusy(true);
    if (jobBoard === activeBoard) {
      setFetchStatus(progress, "running");
    } else {
      setFetchStatus(
        `${boardLabel(jobBoard)} 更新中（当前看${boardLabel(activeBoard)}）…`,
        "running"
      );
    }
    pollTimer = setTimeout(pollUntilDone, 900);
    return;
  }

  setRefreshBusy(false);

  if (st.status === "error") {
    const err = st.error || "失败";
    setJobStatus(err, "error");
    if (jobBoard === activeBoard) {
      setFetchStatus(err, "error");
    } else {
      setFetchStatus(`${boardLabel(jobBoard)} 失败：${err}`, "error");
    }
    setActiveButton(activeBoard);
    return;
  }

  // 仅当当前仍停留在该榜单时刷新表格
  if (jobBoard !== activeBoard) {
    setJobStatus(`完成 · ${boardLabel(jobBoard)}（后台）`);
    setFetchStatus("");
    return;
  }

  const resultRes = await fetch(`/api/fomo-top20/result?board=${encodeURIComponent(jobBoard)}`);
  if (!resultRes.ok) {
    const err = await resultRes.json().catch(() => ({}));
    const msg = err.detail || "获取结果失败";
    setJobStatus(msg, "error");
    setFetchStatus(msg, "error");
    return;
  }
  const payload = await resultRes.json();
  renderTable(payload);
  const fail = payload.stats?.tradersFail ? ` · fail ${payload.stats.tradersFail}` : "";
  const doneMsg = `完成 · ${payload.elapsedSec ?? "?"}s${fail}`;
  setJobStatus(doneMsg);
  setFetchStatus(refreshSilent ? `后台已更新 · ${formatTime(payload.updatedAt)}` : doneMsg);
  if (refreshSilent) {
    setTimeout(() => {
      if (fetchStatusEl && fetchStatusEl.textContent.includes("后台已更新")) {
        setFetchStatus("");
      }
    }, 4000);
  }
}

function ensurePolling() {
  if (pollTimer) return;
  pollUntilDone();
}

async function startRefresh({ silent = false } = {}) {
  const board = activeBoard;
  const limit = boardLimit(board);
  const label = boardLabel(board);
  refreshSilent = !!silent;

  setRefreshBusy(true);
  const startMsg = silent ? `${label} 后台更新中…` : `${label} 拉取中…`;
  setJobStatus(startMsg, "running");
  setFetchStatus(startMsg, "running");
  showLoading(false);

  try {
    const res = await fetch("/api/fomo-top20/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "fast", board, limit }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || "无法启动刷新");
    if (!data.ok) throw new Error(data.message || "无法启动刷新");

    if (data.started === false) {
      const runningBoard = normalizeBoard(data.board || "");
      if (runningBoard && runningBoard !== board) {
        // 其他榜单任务进行中：保持禁用刷新，继续轮询，勿清掉已有轮询
        refreshTargetBoard = runningBoard;
        const msg = `${boardLabel(runningBoard)} 更新中，请稍后再刷新当前榜`;
        setJobStatus(msg, "running");
        setFetchStatus(msg, "running");
        setRefreshBusy(true);
        ensurePolling();
        return;
      }
      // 同榜单任务已在跑
      refreshTargetBoard = board;
      setFetchStatus(`${label} 更新中…`, "running");
      ensurePolling();
      return;
    }

    refreshTargetBoard = board;
    // 新任务：若已有轮询则复用，否则启动
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    pollUntilDone();
  } catch (e) {
    setRefreshBusy(false);
    const msg = e.message || String(e);
    setJobStatus(msg, "error");
    setFetchStatus(msg, "error");
  }
}

async function selectBoard(board) {
  closeSettings();
  closeSidebar();
  activeBoard = normalizeBoard(board);
  activeMode = "fast";
  setActiveButton(activeBoard);
  hideRowTip();

  const cached = await loadCached(activeBoard);
  if (!cached) {
    setFetchStatus(`${boardLabel(activeBoard)} 无缓存，正在拉取…`, "running");
    await startRefresh({ silent: false });
    return;
  }

  if (isCacheStale(cached.updatedAt)) {
    const ageMin = Math.round(cacheAgeMs(cached.updatedAt) / 60000);
    setFetchStatus(`缓存约 ${ageMin} 分钟前，后台更新中…`, "running");
    setJobStatus(`缓存 · ${formatTime(cached.updatedAt)} · 后台更新`, "running");
    await startRefresh({ silent: true });
    return;
  }

  // 有新鲜缓存：若别处仍在拉榜，刷新按钮保持禁用并继续轮询
  try {
    const stRes = await fetch("/api/fomo-top20/status");
    const st = await stRes.json();
    if (st.status === "running") {
      const runningBoard = normalizeBoard(st.board || "");
      refreshTargetBoard = runningBoard || refreshTargetBoard;
      setRefreshBusy(true);
      setFetchStatus(
        `${boardLabel(runningBoard || "all")} 更新中（当前看${boardLabel(activeBoard)}）…`,
        "running"
      );
      ensurePolling();
      return;
    }
  } catch {
    /* ignore */
  }

  setRefreshBusy(false);
  setFetchStatus("");
  setJobStatus(`缓存 · ${formatTime(cached.updatedAt)}`);
}

async function forceRefreshBoard() {
  if (refreshBusy) return;
  activeMode = "fast";
  setActiveButton(activeBoard);
  await startRefresh({ silent: false });
}

btnFast?.addEventListener("click", () => selectBoard("all"));
btn7d?.addEventListener("click", () => selectBoard("7d"));
btn24h?.addEventListener("click", () => selectBoard("24h"));
btnRefreshBoard?.addEventListener("click", () =>
  forceRefreshBoard().catch((e) => {
    setJobStatus(String(e), "error");
    setFetchStatus(String(e), "error");
  })
);
btnMobileRefresh?.addEventListener("click", () =>
  forceRefreshBoard().catch((e) => {
    setJobStatus(String(e), "error");
    setFetchStatus(String(e), "error");
  })
);
btnToggleSidebar?.addEventListener("click", toggleSidebar);
btnCloseSidebar?.addEventListener("click", closeSidebar);
sidebarBackdrop?.addEventListener("click", closeSidebar);
btnSaveAuth.addEventListener("click", () => saveAuth().catch((e) => setJobStatus(String(e), "error")));
btnClearAuth.addEventListener("click", () => clearAuth().catch((e) => setJobStatus(String(e), "error")));
btnGoogleAuth?.addEventListener("click", () =>
  startGoogleLogin().catch((e) => {
    setGoogleLoginBusy(false);
    setJobStatus(String(e), "error");
  })
);
btnCancelGoogle?.addEventListener("click", () =>
  cancelGoogleLogin().catch((e) => setJobStatus(String(e), "error"))
);
btnSaveSettings?.addEventListener("click", () =>
  saveBoardSettings().catch((e) => setJobStatus(String(e), "error"))
);
btnApplyFilter?.addEventListener("click", applyFilters);
btnResetFilter?.addEventListener("click", resetFilters);
btnOpenSettings?.addEventListener("click", openSettings);
btnCloseSettings?.addEventListener("click", closeSettings);
mobileSort?.addEventListener("click", (e) => {
  const chip = e.target.closest(".sort-chip");
  if (!chip) return;
  if (chip.dataset.sort === "default") {
    clearSort();
    return;
  }
  const col = chip.getAttribute("data-col");
  if (col) onHeaderClick(col);
});
settingsOverlay?.addEventListener("click", (e) => {
  if (e.target === settingsOverlay) closeSettings();
});
for (const f of FILTER_FIELDS) {
  document.getElementById(f.id)?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyFilters();
  });
}
[setAllLimit, setDayLimit, setH24Limit].forEach((el) => {
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

cardList?.addEventListener("click", async (e) => {
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
  const card = e.target.closest(".token-card[data-row-idx]");
  if (!card || !lastPayload) return;
  const idx = Number(card.dataset.rowIdx);
  const rows = getDisplayRows(lastPayload);
  const row = rows[idx];
  if (!row) return;
  if (tipRowIndex === idx && !rowTip.classList.contains("hidden")) {
    hideRowTip();
    return;
  }
  cardList.querySelectorAll(".token-card.tip-active").forEach((el) => el.classList.remove("tip-active"));
  card.classList.add("tip-active");
  showRowTip(row, card, e.clientX, e.clientY);
});

thead.addEventListener("click", (e) => {
  const th = e.target.closest("th.sortable[data-col]");
  if (!th) return;
  onHeaderClick(th.getAttribute("data-col"));
});

document.addEventListener("click", (e) => {
  if (
    e.target.closest("#data-table tbody") ||
    e.target.closest("#card-list") ||
    e.target.closest("#row-tip")
  ) {
    return;
  }
  hideRowTip();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (isSettingsOpen()) {
      closeSettings();
      return;
    }
    if (isSidebarOpen()) {
      closeSidebar();
      return;
    }
    hideRowTip();
  }
});

loadStoredFilters();
renderSortChips();
loadSettings().then(() => {
  refreshAuthStatus();
  selectBoard(activeBoard);
});
