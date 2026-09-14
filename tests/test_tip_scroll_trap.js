const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "web", "styles.css"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

const tipCssStart = css.indexOf(".row-tip {");
const tipCssEnd = css.indexOf(".row-tip.hidden");
assert(tipCssStart >= 0 && tipCssEnd > tipCssStart, ".row-tip block not found");
const tipCss = css.slice(tipCssStart, tipCssEnd);
assert(/overscroll-behavior:\s*contain/.test(tipCss), "tip panel should contain overscroll");

assert(src.includes("function trapTipScroll("), "trapTipScroll helper missing");
const trapFn = src.slice(
  src.indexOf("function trapTipScroll("),
  src.indexOf('rowTip.addEventListener("wheel"')
);
assert(trapFn.includes("stopPropagation"), "tip scroll trap must stop bubbling");
assert(trapFn.includes("preventDefault"), "tip scroll trap must not scroll the page");
assert(
  trapFn.indexOf("stopPropagation") >= 0 &&
    trapFn.indexOf("stopPropagation") < trapFn.indexOf(".row-tip-holders"),
  "whole tip must stop bubbling; holders are only exempt from preventDefault"
);

assert(/rowTip\.addEventListener\(\s*"wheel"\s*,\s*trapTipScroll/.test(src), "rowTip must listen for wheel");
assert(/rowTip\.addEventListener\(\s*"touchmove"\s*,\s*trapTipScroll/.test(src), "rowTip must listen for touchmove");
assert(
  /addEventListener\(\s*"wheel"\s*,\s*trapTipScroll\s*,\s*\{\s*passive:\s*false/.test(src),
  "wheel trap cannot be passive if it preventDefault"
);
assert(
  /addEventListener\(\s*"touchmove"\s*,\s*trapTipScroll\s*,\s*\{\s*passive:\s*false/.test(src),
  "touchmove trap cannot be passive if it preventDefault"
);

console.log("ok");
