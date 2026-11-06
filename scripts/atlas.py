#!/usr/bin/env python3
"""Pixel Atlas: search, palettes and benchmarks from the Pixel Art Atlas dataset.

Dataset: https://huggingface.co/datasets/Angais/pixel-art-atlas-1.4m
(1.4M AI-generated 16x16 sprites, CC0 by Angais, made with Krea 2 Turbo; see README).

Commands:
  setup                       download (260 MB) and extract the dataset into the cache
  info                        show cache location and dataset size
  subjects QUERY              list subject labels that match, with sprite counts
  search QUERY [--n 12]       save matching sprites as PNGs plus matches.json
  get ROW [ROW ...]           save sprites by row id
  palette QUERY [--k 10]      main colors used by sprites of a subject (JSON + swatch PNG)
  bench IMAGE --like QUERY    compare a sprite's stats with atlas sprites of a subject

Only numpy and Pillow are needed. Run with `python -I`.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import zipfile

import numpy as np
from PIL import Image

URL = "https://huggingface.co/datasets/Angais/pixel-art-atlas-1.4m/resolve/main/pixel-art-16x16-1.4m.zip"
ZIP_SIZE = 259319416
ROWS = 1409404
FILES = ["tokens.npy", "palette.npy", "captions.json", "objects.json", "split.npy", "LICENSE", "README.md"]


def cache_dir():
    d = os.environ.get("PIXEL_ATLAS_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "pixel-atlas")
    return os.path.abspath(d)


def data_dir():
    return os.path.join(cache_dir(), "data")


def fail(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- setup

def download(zip_path):
    have = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
    if have == ZIP_SIZE:
        return
    if have > ZIP_SIZE:
        os.remove(zip_path)
        have = 0
    print(f"downloading {URL}\n  -> {zip_path} ({ZIP_SIZE / 1e6:.0f} MB)")
    req = urllib.request.Request(URL, headers={"User-Agent": "pixel-atlas-skill", "Range": f"bytes={have}-"})
    with urllib.request.urlopen(req) as r, open(zip_path, "ab" if have else "wb") as f:
        if have and r.status != 206:  # server ignored the range: start over
            f.seek(0)
            f.truncate()
            have = 0
        done = have
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if done % (20 << 20) < (1 << 20):
                print(f"  {done / ZIP_SIZE:5.1%}", flush=True)
    if os.path.getsize(zip_path) != ZIP_SIZE:
        fail(f"download incomplete ({os.path.getsize(zip_path)} of {ZIP_SIZE} bytes); run setup again to resume")


def cmd_setup(a):
    os.makedirs(data_dir(), exist_ok=True)
    zip_path = os.path.join(cache_dir(), "atlas.zip")
    if not all(os.path.exists(os.path.join(data_dir(), f)) for f in FILES):
        download(zip_path)
        with zipfile.ZipFile(zip_path) as z:
            names = set(z.namelist())
            for f in FILES:  # extract only the known flat names, never paths from the archive
                if f not in names:
                    fail(f"{f} missing from the archive")
                with z.open(f) as src, open(os.path.join(data_dir(), f), "wb") as dst:
                    while True:
                        b = src.read(1 << 20)
                        if not b:
                            break
                        dst.write(b)
    A = Atlas()
    t = A.tokens
    if t.shape != (ROWS, 256) or len(A.captions) != ROWS or len(A.objects) != ROWS:
        fail(f"unexpected data shape {t.shape}, {len(A.captions)} captions, {len(A.objects)} subjects")
    if a.keep_zip is False and os.path.exists(zip_path):
        os.remove(zip_path)
    print(f"ok: {ROWS} sprites, {len(set(A.objects))} subjects, {len(A.palette) - 1} colors in {data_dir()}")


def cmd_info(a):
    d = data_dir()
    ready = all(os.path.exists(os.path.join(d, f)) for f in FILES)
    size = sum(os.path.getsize(os.path.join(d, f)) for f in FILES if os.path.exists(os.path.join(d, f)))
    print(json.dumps({"cache": cache_dir(), "ready": ready, "bytes": size}, indent=2))


# ---------------------------------------------------------------- data

class Atlas:
    def __init__(self):
        d = data_dir()
        if not os.path.exists(os.path.join(d, "tokens.npy")):
            fail(f"dataset not found in {d}; run: python -I atlas.py setup")
        self.tokens = np.load(os.path.join(d, "tokens.npy"), mmap_mode="r", allow_pickle=False)
        self.palette = np.load(os.path.join(d, "palette.npy"), allow_pickle=False)
        with open(os.path.join(d, "objects.json"), encoding="utf-8") as f:
            self.objects = json.load(f)
        self._captions = None

    @property
    def captions(self):
        if self._captions is None:
            with open(os.path.join(data_dir(), "captions.json"), encoding="utf-8") as f:
                self._captions = json.load(f)
        return self._captions

    def rgba(self, row):
        px = np.asarray(self.tokens[row], dtype=np.int64).reshape(16, 16)
        a = np.where(px != 0, 255, 0).astype(np.uint8)
        return np.dstack((self.palette[px], a))

    def image(self, row, scale=1):
        im = Image.fromarray(self.rgba(row), "RGBA")
        return im.resize((16 * scale, 16 * scale), Image.NEAREST) if scale > 1 else im


def words(q):
    return [w for w in re.split(r"[^a-z0-9]+", q.lower()) if w]


def has_all(text, ws):
    t = " " + re.sub(r"[^a-z0-9]+", " ", text.lower()) + " "
    return all((" " + w + " ") in t or (" " + w + "s ") in t or (w.endswith("s") and (" " + w[:-1] + " ") in t) for w in ws)


def match(A, query, wide=False):
    """Rows that match, best tier first: 0 exact subject, 1 subject has all words, 2 caption has all words."""
    ws = words(query)
    if not ws:
        fail("empty query")
    q = " ".join(ws)
    subs = {}
    for i, s in enumerate(A.objects):
        subs.setdefault(s, []).append(i)
    tiers = [[], [], []]
    for s, rows in subs.items():
        if " ".join(words(s)) == q:
            tiers[0] += rows
        elif has_all(s, ws):
            tiers[1] += rows
    if wide or not (tiers[0] or tiers[1]):
        seen = set(tiers[0]) | set(tiers[1])
        tiers[2] = [i for i, c in enumerate(A.captions) if i not in seen and has_all(c, ws)]
    if wide:
        return [r for t in tiers for r in t], "all"
    for k, t in enumerate(tiers):
        if t:
            return t, ["subject", "subject words", "caption words"][k]
    return [], "none"


def sample(rows, n, seed):
    rows = np.array(rows)
    if len(rows) <= n:
        return rows.tolist()
    return np.sort(np.random.default_rng(seed).choice(rows, n, replace=False)).tolist()


# ---------------------------------------------------------------- commands

def cmd_subjects(a):
    A = Atlas()
    ws = words(a.query)
    counts = {}
    for s in A.objects:
        counts[s] = counts.get(s, 0) + 1
    hits = sorted(((c, s) for s, c in counts.items() if has_all(s, ws)), reverse=True)
    for c, s in hits[: a.limit]:
        print(f"{c:6d}  {s}")
    if not hits:
        print("no subject matches; `search` will fall back to captions")


def save_rows(A, rows, out, scale, query, how):
    os.makedirs(out, exist_ok=True)
    items = []
    for k, r in enumerate(rows, 1):
        name = f"{k:02d}_row{r}.png"
        A.image(r, scale).save(os.path.join(out, name))
        items.append({"n": k, "row": int(r), "file": name, "subject": A.objects[r], "caption": A.captions[r]})
    meta = {"query": query, "matched_by": how, "scale": scale, "source": "Angais/pixel-art-atlas-1.4m (CC0, AI-generated; see README)", "items": items}
    with open(os.path.join(out, "matches.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return meta


def cmd_search(a):
    A = Atlas()
    rows, how = match(A, a.query, a.wide)
    if not rows:
        fail(f"nothing matches '{a.query}'; try `subjects` with one word")
    pick = sample(rows, a.n, a.seed)
    out = a.out or os.path.join("atlas-refs", "-".join(words(a.query)))
    meta = save_rows(A, pick, out, a.scale, a.query, how)
    print(f"{len(rows)} sprites match '{a.query}' (by {how}); saved {len(pick)} to {os.path.abspath(out)}")
    for it in meta["items"]:
        print(f"  {it['n']:2d}  row {it['row']:7d}  [{it['subject']}]  {it['caption']}")


def cmd_get(a):
    A = Atlas()
    for r in a.rows:
        if not 0 <= r < ROWS:
            fail(f"row {r} out of range")
    out = a.out or "atlas-refs"
    save_rows(A, a.rows, out, a.scale, "rows", "row id")
    print(f"saved {len(a.rows)} sprites to {os.path.abspath(out)}")


def lightness(rgb):
    rgb = np.asarray(rgb, dtype=np.float64) / 255
    return (rgb.max(-1) + rgb.min(-1)) / 2


def saturation(rgb):
    rgb = np.asarray(rgb, dtype=np.float64) / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    l = (mx + mn) / 2
    d = mx - mn
    den = 1 - np.abs(2 * l - 1)
    return np.where(den > 1e-6, d / np.maximum(den, 1e-6), 0)


def kmeans(x, w, k, seed=0, iters=30):
    rng = np.random.default_rng(seed)
    k = min(k, len(x))
    # weighted k-means++ start
    c = [x[rng.choice(len(x), p=w / w.sum())]]
    for _ in range(1, k):
        d = np.min(((x[:, None] - np.array(c)[None]) ** 2).sum(-1), 1) * w
        if d.sum() == 0:
            break
        c.append(x[rng.choice(len(x), p=d / d.sum())])
    c = np.array(c)
    for _ in range(iters):
        lab = np.argmin(((x[:, None] - c[None]) ** 2).sum(-1), 1)
        for j in range(len(c)):
            m = lab == j
            if m.any():
                c[j] = (x[m] * w[m, None]).sum(0) / w[m].sum()
    lab = np.argmin(((x[:, None] - c[None]) ** 2).sum(-1), 1)
    share = np.array([w[lab == j].sum() for j in range(len(c))]) / w.sum()
    return c, share


def cmd_palette(a):
    A = Atlas()
    rows, how = match(A, a.query, a.wide)
    if not rows:
        fail(f"nothing matches '{a.query}'")
    rows = sample(rows, a.max, a.seed)
    t = np.asarray(A.tokens[np.array(rows)], dtype=np.int64)
    w = np.zeros(len(A.palette))
    for r in t:  # each sprite counts the same, whatever its size
        r = r[r != 0]
        if len(r):
            np.add.at(w, r, 1.0 / len(r))
    idx = np.nonzero(w)[0]
    cols, share = kmeans(A.palette[idx].astype(np.float64), w[idx], a.k, a.seed)
    order = np.argsort(lightness(cols))
    cols, share = np.rint(cols[order]).astype(int), share[order]
    per = [len(np.unique(r[r != 0])) for r in t]
    meta = {
        "query": a.query, "matched_by": how, "sprites": len(rows),
        "colors": cols.tolist(), "share": [round(float(s), 4) for s in share],
        "colors_per_sprite": {"p10": int(np.percentile(per, 10)), "median": int(np.median(per)), "p90": int(np.percentile(per, 90))},
        "use": "P.quantize(buf, n, { palette: colors.map(P.col) }) or P.hueRampFrom(colors, n)",
    }
    out = a.out or os.path.join("atlas-refs", "-".join(words(a.query)))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "palette.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    sw = Image.new("RGBA", (len(cols) * 24, 24))
    for j, c in enumerate(cols):
        sw.paste(tuple(int(v) for v in c) + (255,), (j * 24, 0, j * 24 + 24, 24))
    sw.save(os.path.join(out, "palette.png"))
    print(f"{len(rows)} sprites of '{a.query}' (by {how}); colors per sprite p10/median/p90: "
          f"{meta['colors_per_sprite']['p10']}/{meta['colors_per_sprite']['median']}/{meta['colors_per_sprite']['p90']}")
    for c, sh in zip(meta["colors"], meta["share"]):
        print(f"  #{c[0]:02x}{c[1]:02x}{c[2]:02x}  {sh:6.1%}")
    print(f"saved palette.json and palette.png to {os.path.abspath(out)}")


# ---------------------------------------------------------------- bench

def sprite_stats(rgba):
    """Stats of one sprite. rgba: HxWx4 uint8. Alpha below 128 counts as clear."""
    op = rgba[..., 3] >= 128
    n = int(op.sum())
    if n == 0:
        return None
    ys, xs = np.nonzero(op)
    box = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
    rgb = rgba[..., :3][op]
    key = (rgb[:, 0].astype(np.int64) << 16) | (rgb[:, 1].astype(np.int64) << 8) | rgb[:, 2]
    _, cnt = np.unique(key, return_counts=True)
    L = lightness(rgb)
    # silhouette edge: opaque pixels with a clear 4-neighbor (or the canvas edge)
    pad = np.pad(op, 1)
    inner = pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    edge = op & ~inner
    Lmap = np.zeros(op.shape)
    Lmap[op] = L
    dark_cut = min(np.percentile(L, 25), np.median(L) - 0.05)  # a flat sprite has no dark edge
    return {
        "colors": int(len(cnt)),
        "top_share": float(cnt.max() / n),
        "fill": float(n / box),
        "value_range": float(np.percentile(L, 95) - np.percentile(L, 5)),
        "saturation": float(np.mean(saturation(rgb))),
        "dark_edge": float((Lmap[edge] <= dark_cut).mean()) if edge.any() else 0.0,
    }


NOTES = {
    "colors": "distinct colors",
    "top_share": "share of the most used color (high = flat)",
    "fill": "opaque share of the bounding box (low = thin or spiky shape)",
    "value_range": "lightness spread p5..p95 (low = flat shading)",
    "saturation": "mean saturation",
    "dark_edge": "share of silhouette pixels in the darkest quarter (high = dark outline)",
}


def cmd_bench(a):
    im = Image.open(a.image).convert("RGBA")
    arr = np.array(im)
    note = None
    if a.at and (im.width > a.at or im.height > a.at):
        # shrink the trimmed sprite to fit a.at, keeping the most common color per cell
        op = arr[..., 3] >= 128
        ys, xs = np.nonzero(op)
        arr = arr[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]
        s = max(arr.shape[0], arr.shape[1]) / a.at
        h, w = max(1, round(arr.shape[0] / s)), max(1, round(arr.shape[1] / s))
        arr = np.array(Image.fromarray(arr, "RGBA").resize((w, h), Image.NEAREST))
        note = f"shrunk from {im.width}x{im.height} to {w}x{h} (nearest) to compare at atlas scale"
    mine = sprite_stats(arr)
    if mine is None:
        fail("the image has no opaque pixels")
    A = Atlas()
    rows, how = match(A, a.like, a.wide)
    if not rows:
        fail(f"nothing matches '{a.like}'")
    rows = sample(rows, a.max, a.seed)
    ref = [s for s in (sprite_stats(A.rgba(r)) for r in rows) if s]
    report = {"image": os.path.abspath(a.image), "like": a.like, "matched_by": how, "atlas_sprites": len(ref), "note": note, "stats": {}}
    flags = []
    for k in mine:
        v = np.array([s[k] for s in ref])
        p10, p50, p90 = np.percentile(v, [10, 50, 90])
        where = "low" if mine[k] < p10 else "high" if mine[k] > p90 else "ok"
        report["stats"][k] = {"yours": round(mine[k], 3), "p10": round(p10, 3), "median": round(p50, 3), "p90": round(p90, 3), "verdict": where}
        if where != "ok":
            flags.append(f"{k} is {where}: {mine[k]:.3g} vs atlas {p10:.3g}..{p90:.3g} ({NOTES[k]})")
    report["flags"] = flags
    if a.json:
        print(json.dumps(report, indent=2))
        return
    print(f"{os.path.basename(a.image)} vs {len(ref)} atlas sprites of '{a.like}' (by {how})")
    if note:
        print("  " + note)
    print(f"  {'stat':12s} {'yours':>7s} {'p10':>7s} {'median':>7s} {'p90':>7s}")
    for k, s in report["stats"].items():
        mark = "" if s["verdict"] == "ok" else "  <- " + s["verdict"]
        print(f"  {k:12s} {s['yours']:7.3f} {s['p10']:7.3f} {s['median']:7.3f} {s['p90']:7.3f}{mark}")
    print("  all inside the atlas range" if not flags else "  outside the 10-90% range: " + "; ".join(f.split(':')[0] for f in flags))


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup")
    s.add_argument("--keep-zip", action="store_true", help="keep the downloaded zip after extracting")
    s.set_defaults(fn=cmd_setup)
    sub.add_parser("info").set_defaults(fn=cmd_info)

    s = sub.add_parser("subjects")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(fn=cmd_subjects)

    def common(s, n_default):
        s.add_argument("--seed", type=int, default=0, help="change to get a different sample")
        s.add_argument("--wide", action="store_true", help="also match captions, not only the best tier")
        s.add_argument("--out", help="output folder (default atlas-refs/<query>)")
        return s

    s = common(sub.add_parser("search"), 12)
    s.add_argument("query")
    s.add_argument("--n", type=int, default=12)
    s.add_argument("--scale", type=int, default=1, help="save PNGs this many times bigger (1 = native 16x16)")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("get")
    s.add_argument("rows", type=int, nargs="+")
    s.add_argument("--scale", type=int, default=1)
    s.add_argument("--out")
    s.set_defaults(fn=cmd_get)

    s = common(sub.add_parser("palette"), 0)
    s.add_argument("query")
    s.add_argument("--k", type=int, default=10, help="number of colors")
    s.add_argument("--max", type=int, default=2000, help="most sprites to sample")
    s.set_defaults(fn=cmd_palette)

    s = common(sub.add_parser("bench"), 0)
    s.add_argument("image")
    s.add_argument("--like", required=True, help="subject to compare with")
    s.add_argument("--at", type=int, default=16, help="shrink bigger sprites to this size first (0 = compare as is)")
    s.add_argument("--max", type=int, default=1000)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_bench)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
