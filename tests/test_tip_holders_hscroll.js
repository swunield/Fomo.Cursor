const fs = require("fs");
const path = require("path");

const css = fs.readFileSync(path.join(__dirname, "..", "web", "styles.css"), "utf8");
const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

const start = css.indexOf(".row-tip-holders {");
const end = css.indexOf(".row-tip-holders::-webkit-scrollbar {");
assert(start >= 0 && end > start, ".row-tip-holders block not found");
const block = css.slice(start, end);

assert(/overflow-x:\s*auto/.test(block), "holders area should allow horizontal scroll");
assert(/min-width:\s*0/.test(block), "holders area should shrink so overflow-x can activate");
assert(/touch-action:/.test(block) && /pan-x/.test(block), "mobile swipe should allow horizontal pan");
assert(!/touch-action:\s*pan-y\s*;/.test(block), "touch-action must not lock to vertical-only");

assert(src.includes("is-scrollable-y"), "vertical scroll class should be applied when over 10 people");
assert(
  /holderLines\.length\s*>\s*10/.test(src),
  "vertical overflow should only enable when more than 10 holders"
);

const media = css.indexOf("@media (max-width: 860px)");
assert(media >= 0, "mobile media query missing");
const mobile = css.slice(media);
const tipStart = mobile.indexOf(".row-tip {");
const afterTip = mobile.indexOf(".settings-body", tipStart);
assert(tipStart >= 0 && afterTip > tipStart, "mobile .row-tip block not found");
const tipBlock = mobile.slice(tipStart, afterTip);
assert(!/max-width:\s*none/.test(tipBlock), "mobile tip must stay within viewport for horizontal holder scroll");

console.log("ok");
