const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`);
  }
}

assert(src.includes("function fmtPercent("), "fmtPercent missing");
assert(src.includes("function fmtChange24("), "fmtChange24 missing");
assert(src.includes("function rewritePercentsInText("), "rewritePercentsInText missing");

const nStart = src.indexOf("function parseNumber(value)");
const nEnd = src.indexOf("function readFilterInputs(");
assert(nStart >= 0 && nEnd > nStart, "parseNumber/fmtPercent block missing");
eval(src.slice(nStart, nEnd));

assertEqual(fmtPercent(2.44), "2.44%", "lt 10 two decimals");
assertEqual(fmtPercent(9.99), "9.99%", "9.99 stays two decimals");
assertEqual(fmtPercent(10), "10.0%", "10 uses one decimal");
assertEqual(fmtPercent(22.3), "22.3%", "mid range one decimal");
assertEqual(fmtPercent(100), "100%", "100 has no decimal");
assertEqual(fmtPercent(150.4), "150%", "gte 100 rounds to integer");
assertEqual(fmtPercent(-5.2, true), "-5.20%", "signed small");
assertEqual(fmtPercent(21.18, true), "+21.2%", "signed mid");
assertEqual(fmtPercent(-150.7, true), "-151%", "signed large");

assertEqual(fmtChange24(-0.2118), "-21.2%", "ratio to percent");
assertEqual(fmtChange24("+5.20%"), "+5.20%", "already formatted small");
assertEqual(fmtChange24("-21.18%"), "-21.2%", "reformat existing 24h");

assertEqual(fmtHoldingWithMcapPct("2.44M", "100M"), "2.4M(2.44%)", "holding lt 10");
assertEqual(fmtHoldingWithMcapPct("12.1M", "100M"), "12.1M(12.1%)", "holding mid");
assertEqual(fmtHoldingWithMcapPct("150M", "100M"), "150.0M(150%)", "holding gte 100");

assertEqual(
  rewritePercentsInText("1.alice 12.1M(2.440%) +1.2M(+23.45%)"),
  "1.alice 12.1M(2.44%) +1.2M(+23.5%)",
  "rewrite holder line percents"
);

console.log("ok");
