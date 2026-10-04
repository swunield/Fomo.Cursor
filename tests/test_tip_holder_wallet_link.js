const fs = require("fs");
const path = require("path");

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "web", "styles.css"), "utf8");

assert(src.includes("function debotAddressUrl("), "debotAddressUrl missing");
assert(src.includes("function debotHolderLinkButton("), "debotHolderLinkButton missing");
assert(src.includes("function loadWalletLinks("), "loadWalletLinks missing");
assert(src.includes("function refreshTipHolderWallets("), "tip wallet refresh missing");
assert(src.includes("function mergeWalletLinks("), "mergeWalletLinks missing");
assert(src.includes("function repaintTipHolderLinks("), "repaintTipHolderLinks missing");
assert(src.includes("/api/fomo-top20/wallets"), "wallets API not loaded");
assert(src.includes("/api/fomo-top20/wallets/resolve-holders"), "resolve-holders API not called");
assert(src.includes("debot.ai/address/"), "address URL format missing");
assert(src.includes("debot-holder-link-btn"), "holder link class missing");
assert(
  src.includes("renderHolderTipRow(line, { row })") || src.includes("renderHolderTipRow(line,{ row })"),
  "tip rows should pass row for wallet lookup"
);
assert(src.includes("loadWalletLinks()"), "startup should load wallet links");
assert(src.includes("refreshTipHolderWallets(row)"), "chart refresh should resolve tip wallets");

const pickStart = src.indexOf("function pickHolderWallet(");
const pickEnd = src.indexOf("function lookupHolderWallets(");
assert(pickStart >= 0 && pickEnd > pickStart, "pickHolderWallet missing");
const pickFn = src.slice(pickStart, pickEnd);
assert(!pickFn.includes("return list[0]"), "must not fall back to other-chain wallet");
assert(pickFn.includes("debotChainSlug("), "pick wallet by token chain");

const urlStart = src.indexOf("function holderDebotAddressUrl(");
const urlEnd = src.indexOf("function debotHolderLinkButton(");
assert(urlStart >= 0 && urlEnd > urlStart, "holderDebotAddressUrl missing");
const urlFn = src.slice(urlStart, urlEnd);
assert(urlFn.includes("debotAddressUrl(wallet.address, chain)"), "URL must use token chain");
assert(!urlFn.includes("wallet.network"), "URL must not use wallet.network");

const renderStart = src.indexOf("function renderHolderTipRow(");
const renderEnd = src.indexOf("function holderIdentity(");
assert(renderStart >= 0 && renderEnd > renderStart, "renderHolderTipRow block missing");
const renderFn = src.slice(renderStart, renderEnd);
assert(renderFn.includes("debotHolderLinkButton("), "holder tip row should render wallet Debot button");
assert(renderFn.indexOf("debotHolderLinkButton(") < renderFn.indexOf("tip-who-text"), "button before name");

assert(css.includes(".debot-holder-link-btn"), "holder link styles missing");
assert(css.includes(".row-tip-holder-grid .tip-who"), "tip-who flex styles missing");

console.log("ok");
