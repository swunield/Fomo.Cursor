const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const src = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "web", "styles.css"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

const showFn = src.slice(src.indexOf("function showRowTip("), src.indexOf("function escapeHtml("));
assert(showFn.includes("function showRowTip("), "showRowTip missing");
assert(showFn.includes("row-tip-name"), "tip still has name row");
assert(showFn.includes("debotLinkButton("), "tip name row should include Debot jump");
assert(
  showFn.indexOf("favButton(") < showFn.indexOf("debotLinkButton(") &&
    showFn.indexOf("debotLinkButton(") < showFn.indexOf("row-tip-name-text"),
  "tip Debot sits between favorite and token name"
);
assert(showFn.includes("row-tip-name-meta"), "name row should include market meta on the right");
assert(showFn.includes('row["市值"]'), "meta uses 市值");
assert(showFn.includes('row["成交量"]'), "meta uses 成交量");
assert(showFn.includes('row["24h涨跌"]'), "meta uses 24h涨跌");
assert(showFn.includes("chgClass("), "24h change should keep up/down color");
assert(
  showFn.indexOf("row-tip-name") < showFn.indexOf("row-tip-name-meta"),
  "name comes first, meta on the same row"
);

const nameCssStart = css.indexOf(".row-tip-name {");
const nameCssEnd = css.indexOf(".row-tip-label {");
assert(nameCssStart >= 0 && nameCssEnd > nameCssStart, ".row-tip-name block missing");
const nameCss = css.slice(nameCssStart, nameCssEnd);
assert(/display:\s*flex/.test(nameCss), "name row should be a flex line");
assert(/justify-content:\s*space-between/.test(nameCss), "meta should sit on the far right");
assert(css.includes(".row-tip-name-meta"), "name meta style missing");

console.log("ok");
