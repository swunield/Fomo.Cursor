const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const colsMatch = src.match(/const COLUMNS = \[([\s\S]*?)\];/);
if (!colsMatch) throw new Error("COLUMNS not found");
const cols = [...colsMatch[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
if (cols[cols.indexOf("持仓人数") + 1] !== "持仓市值") {
  throw new Error(`持仓人数 should precede 持仓市值, got ${JSON.stringify(cols)}`);
}
if (cols[cols.indexOf("持仓市值") + 1] !== "持仓盈亏") {
  throw new Error(`持仓盈亏 should follow 持仓市值, got ${JSON.stringify(cols)}`);
}
if (!src.includes('c === "持仓盈亏"') && !src.includes('c === "24h涨跌" || c === "持仓盈亏"')) {
  throw new Error("table render should color 持仓盈亏 like 24h涨跌");
}

console.log("ok");
