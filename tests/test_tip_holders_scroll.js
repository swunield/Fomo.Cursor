const fs = require("fs");
const path = require("path");

const css = fs.readFileSync(path.join(__dirname, "..", "web", "styles.css"), "utf8");
const start = css.indexOf(".row-tip-holders {");
const end = css.indexOf(".row-tip-holder-grid {");
if (start < 0 || end < 0 || end <= start) {
  throw new Error(".row-tip-holders block not found");
}
const block = css.slice(start, end);

if (!/max-height:/.test(block)) {
  throw new Error("holders area should cap first-screen height");
}
if (!/10/.test(block)) {
  throw new Error("holders first screen should show at most 10 people");
}
if (!css.includes(".row-tip-holders.is-scrollable-y") || !/overflow-y:\s*auto/.test(css)) {
  throw new Error("holders area should allow vertical scroll when over 10");
}
if (!/overscroll-behavior:\s*contain/.test(block)) {
  throw new Error("holders scroll should not chain to the page");
}

console.log("ok");
