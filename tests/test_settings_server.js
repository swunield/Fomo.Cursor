const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

const saveFn = src.slice(src.indexOf("async function saveBoardSettings("), src.indexOf("function setActiveButton("));
assert(saveFn.includes("readFilterInputs("), "保存设置 should include token filters");
assert(saveFn.includes("mcapMin") || saveFn.includes("...readFilterInputs") || saveFn.includes("readFilterInputs()"), "settings POST should send filter fields");

const applyFn = src.slice(src.indexOf("async function applyFilters("), src.indexOf("function applyNameFilter("));
assert(
  applyFn.includes("/api/settings") || applyFn.includes("persistSettingsFilters("),
  "应用筛选 should persist filters on the server"
);
assert(!applyFn.includes("saveStoredFilters("), "应用筛选 should not keep filters only in localStorage");

const loadFn = src.slice(src.indexOf("async function loadSettings("), src.indexOf("async function saveBoardSettings("));
assert(loadFn.includes("writeFilterInputs") || src.includes("function applySettingsToUi"), "load settings applies UI");

const applyUi = src.slice(src.indexOf("function applySettingsToUi("), src.indexOf("function isSettingsOpen("));
assert(applyUi.includes("writeFilterInputs(") || applyUi.includes("FILTER_FIELDS"), "applySettingsToUi should fill filter inputs");

const resetFn = src.slice(src.indexOf("async function resetFilters("), src.indexOf("async function refreshAuthStatus("));
assert(
  resetFn.includes("/api/settings") || resetFn.includes("persistSettingsFilters("),
  "重置 should clear server filters"
);

console.log("ok");
