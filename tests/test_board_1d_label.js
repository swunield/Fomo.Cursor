const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const files = [
  path.join(root, "web", "index.html"),
  path.join(root, "web", "app.js"),
  path.join(root, "app.py"),
  path.join(root, "fomo_pipeline.py"),
];

for (const file of files) {
  const leftover = fs
    .readFileSync(file, "utf8")
    .split(/\r?\n/)
    .filter(
      (line) =>
        (line.includes("24小时榜") || line.includes("24小时人数")) &&
        !line.includes("replace")
    );
  if (leftover.length) {
    throw new Error(`${path.basename(file)} still has 24小时榜 display copy: ${leftover[0].trim()}`);
  }
}

const html = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
if (!html.includes(">1日榜<")) throw new Error("sidebar should say 1日榜");
if (!html.includes("1日榜人数")) throw new Error("settings should say 1日榜人数");

const src = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");
if (!src.includes("`1日榜前${n}`")) throw new Error("boardLabel should use 1日榜");

console.log("ok");
