const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "web", "styles.css"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

const renderStart = src.indexOf("function renderTable(");
const renderEnd = src.indexOf("function chgClass(");
assert(renderStart >= 0 && renderEnd > renderStart, "renderTable block missing");
const renderFn = src.slice(renderStart, renderEnd);

const nameStart = renderFn.indexOf('if (c === "名称")');
const nameEnd = renderFn.indexOf("return `<td class=\"${cls}\"");
assert(nameStart >= 0 && nameEnd > nameStart, "name cell block missing");
const nameBlock = renderFn.slice(nameStart, nameEnd);
assert(!nameBlock.includes("copy-addr-btn"), "copy button must leave the 名称 column");

assert(renderFn.includes('if (c === "合约地址")'), "addr column branch missing");
const addrBlock = renderFn.slice(renderFn.lastIndexOf('if (c === "合约地址")'));
assert(addrBlock.includes("copy-addr-btn") || addrBlock.includes("copyAddrButton"), "copy button belongs in 合约地址 column");
assert(
  addrBlock.indexOf("copy-addr") < addrBlock.indexOf("addr-text") ||
    addrBlock.indexOf("copyAddrButton") < addrBlock.indexOf("escapeHtml(String(val))"),
  "copy button should sit before the address string"
);

assert(/td\.addr[\s\S]{0,180}display:\s*flex/.test(css), "addr cell should align copy button before the string");

console.log("ok");
