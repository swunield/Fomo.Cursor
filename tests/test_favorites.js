const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "web", "styles.css"), "utf8");
const src = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

assert(html.includes('id="btn-fav-filter"'), "toolbar should have favorite filter button");
assert(
  html.indexOf('id="btn-fav-filter"') < html.indexOf('id="flt-name"'),
  "favorite filter sits left of the name input"
);
assert(src.includes("/api/favorites"), "favorites should load from server");
assert(src.includes("/api/favorites/toggle"), "favorite clicks should persist on server");
assert(src.includes("function favButton("), "shared favorite button helper");
assert(src.includes('class="fav-btn'), "star button class");

const nameFn = src.slice(src.indexOf("function nameActionButtons("), src.indexOf("function renderTable("));
assert(nameFn.includes("favButton("), "name column should include favorite before Debot");
const nameReturn = nameFn.slice(nameFn.lastIndexOf("return"));
assert(
  nameReturn.includes("favButton(") && nameReturn.indexOf("favButton(") < nameReturn.indexOf("debot"),
  "favorite button should sit before Debot jump"
);

const showFn = src.slice(src.indexOf("function showRowTip("), src.indexOf("function escapeHtml("));
assert(showFn.includes("favButton("), "tip name row should include favorite");
assert(
  showFn.indexOf("favButton(") < showFn.indexOf("row-tip-name-text"),
  "tip favorite sits left of token name"
);

assert(css.includes(".fav-btn"), "favorite button styles");
assert(css.includes(".fav-btn.is-on") || css.includes(".fav-btn.is-on,"), "lit favorite style");
assert(css.includes(".fav-filter-btn"), "toolbar favorite filter style");

assert(src.includes("favOnly"), "name filter can combine with favorite-only");

const start = src.indexOf("function parseNumber(value)");
const end = src.indexOf("function compareSortValues(");
assert(start >= 0 && end > start, "filter helpers missing");
eval(src.slice(start, end));

const ember = { 名称: "EMBER", 合约地址: "SoFav", 市值: "10M", 持仓市值: "1M", 持仓人数: "3", 天数: "8.8" };
const pepe = { 名称: "pepe", 合约地址: "SoNope", 市值: "10M", 持仓市值: "1M", 持仓人数: "3", 天数: "8.8" };
assert(matchesTokenFilters(ember, { favOnly: true, favorites: ["sofav"] }), "favorited token kept");
assert(!matchesTokenFilters(pepe, { favOnly: true, favorites: ["sofav"] }), "unfavorited token dropped");
assert(hasAnyFilter({ favOnly: true }), "favorite-only counts as a filter");

console.log("ok");
