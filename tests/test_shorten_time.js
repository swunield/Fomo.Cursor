const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const match = src.match(/function shortenTime\(val\) \{[\s\S]*?\n\}/);
if (!match) {
  throw new Error("shortenTime not found in web/app.js");
}
eval(match[0]);

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`);
  }
}

assertEqual(shortenTime(""), "", "empty");
assertEqual(
  shortenTime("2026-09-01T16:15:50+00:00"),
  "2026-09-02 00:15:50",
  "utc iso to asia/shanghai",
);
assertEqual(
  shortenTime("2026-09-01T16:15:50.000Z"),
  "2026-09-02 00:15:50",
  "utc z to asia/shanghai",
);

console.log("ok");
