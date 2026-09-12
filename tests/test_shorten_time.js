const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const start = src.indexOf("function shortenTime(val)");
const end = src.indexOf("function normalizeBoard(");
if (start < 0 || end < 0 || end <= start) {
  throw new Error("shortenTime block not found in web/app.js");
}
eval(src.slice(start, end));

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
assertEqual(
  shortenTime("2026-09-01T16:15:50"),
  "2026-09-02 00:15:50",
  "naive utc iso to asia/shanghai",
);
assertEqual(
  shortenTime("2026-09-01T16:15:50.123456+00:00"),
  "2026-09-02 00:15:50",
  "utc iso microseconds to asia/shanghai",
);
assertEqual(
  shortenTime("2026-09-02 00:15:50"),
  "2026-09-02 00:15:50",
  "already shanghai display stays",
);

console.log("ok");
