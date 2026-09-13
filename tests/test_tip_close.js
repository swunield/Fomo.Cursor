const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "web", "styles.css"), "utf8");

if (!src.includes('class="row-tip-close"')) {
  throw new Error("Tips should render a close button at the bottom");
}
if (!src.includes('closest(".row-tip-close")')) {
  throw new Error("close button should hide the tip");
}
if (!/hideRowTip\(\)/.test(src)) {
  throw new Error("close path should call hideRowTip");
}
if (!css.includes(".row-tip-close")) {
  throw new Error("close button needs styles");
}

console.log("ok");
