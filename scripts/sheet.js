#!/usr/bin/env node
// Builds one numbered review sheet from a folder written by `atlas.py search`,
// using Codixel's P.sheet (https://github.com/mankidev/codixel, MIT).
//
//   node sheet.js <folder> [--scale 6] [--cols 6] [--ref other.png] [--out sheet.png]
//
// Codixel is found at $CODIXEL_DIR or ~/.claude/skills/codixel.
"use strict";
const fs = require("fs");
const path = require("path");
const os = require("os");

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf("--" + name);
  if (i < 0) return def;
  const v = args[i + 1];
  args.splice(i, 2);
  return v;
};
const scale = +opt("scale", 6);
const cols = +opt("cols", 6);
const ref = opt("ref", null);
let out = opt("out", null);
const dir = args[0];
if (!dir) {
  console.error("usage: node sheet.js <folder> [--scale 6] [--cols 6] [--ref image.png] [--out sheet.png]");
  process.exit(1);
}

const codixel = process.env.CODIXEL_DIR || path.join(os.homedir(), ".claude", "skills", "codixel");
const core = path.join(codixel, "core", "pixel.js");
if (!fs.existsSync(core)) {
  console.error(`Codixel not found at ${core}. Install it (git clone https://github.com/mankidev/codixel ${codixel}) or set CODIXEL_DIR.`);
  process.exit(1);
}
const P = require(core);

const meta = JSON.parse(fs.readFileSync(path.join(dir, "matches.json"), "utf8"));
const items = [];
if (ref) {
  const r = P.load(ref);
  items.push({ buf: r, label: "REF", scale: Math.max(1, Math.floor((16 * scale) / Math.max(r.w, r.h))) });
}
for (const it of meta.items) {
  const buf = P.load(path.join(dir, it.file));
  items.push({ buf, label: String(it.n), scale: Math.max(1, Math.round((16 * scale) / buf.w)) });
}
// one row of 1x views so the shapes can be judged at real size too
const strip = new P.Buf(meta.items.length * 18 + 2, 18);
meta.items.forEach((it, k) => {
  const b = P.load(path.join(dir, it.file));
  const s = b.w > 16 ? P.resize(b, 16, 16, { mode: true }) : b;
  strip.sprite(s, 2 + k * 18, 1);
});

out = out || path.join(dir, "sheet.png");
const grid = P.sheet(items, { cols, gap: 8 });
P.save(P.sheet([{ buf: grid, label: "ZOOM" }, { buf: strip, label: "1X" }], { cols: 1, gap: 8 }), out);
console.log(path.resolve(out));
