---
name: pixel-atlas
description: Looks up small pixel art references, palettes and quality benchmarks from the Pixel Art Atlas (1.4M AI-generated 16x16 sprites, CC0) for use with the codixel skill. Use only when the user asks for atlas references, atlas palettes or an atlas benchmark, or says yes after you offer it — never as an unasked web search for references.
license: MIT
---

# Pixel Atlas

A companion to **codixel** (`~/.claude/skills/codixel`). Codixel turns a reference image into pixel art. This skill gives it references when the user has none, and data to check the result against. It works offline from a local copy of the [Pixel Art Atlas](https://huggingface.co/datasets/Angais/pixel-art-atlas-1.4m) dataset.

Follow codixel for everything about drawing, rigging, animating and showing. This file only covers the atlas.

## When to use it

Codixel says not to search for references the user did not ask for. That still holds: the atlas is a source of references, so use it only when

- the user asks for it ("use the atlas", "find me some atlas slimes", "what colors do atlas potions use"), or
- codixel's section 1 asks the user for a reference, the user has none, and you offer: "I can show you a sheet of similar sprites from the Pixel Art Atlas to pick from. Want that?" and they say yes.

## Setup (once)

All commands run from this skill's folder. Use `python -I`.

```
python -I scripts/atlas.py info      # is the data there?
python -I scripts/atlas.py setup     # downloads 260 MB, extracts ~800 MB to ~/.cache/pixel-atlas
```

Ask the user before running `setup` the first time: it downloads 260 MB. `PIXEL_ATLAS_DIR` moves the cache. Needs Python with numpy and Pillow, and Node for the sheet.

## What the data is

- 1,409,404 sprites, every one **16x16** with a transparent background, about 6,200 subjects (`slime`, `rapier`, `female knight`, ...).
- Every sprite was **made by an AI model** (Krea 2 Turbo with a pixel art LoRA). The captions describe the prompt, not a checked image: a caption may say "unlit candle" over a lit one. Always look at the sprites; never trust a caption alone.
- Rights: CC0 from Angais, to the extent Angais can waive rights. Krea's own license terms (commercial use, §2.3) and acceptable use policy are not overridden. If the user will ship atlas sprites in a game they sell, say so once and point them to the dataset card; using the atlas only for shape, pose and palette is the safer path.

## 1. References: search and pick

```
python -I scripts/atlas.py subjects slime              # subject labels that match, with counts
python -I scripts/atlas.py search "ice slime" --n 12 --out <folder>
node scripts/sheet.js <folder> [--cols 6] [--ref <user image>]
```

`search` matches the subject label first (exact, then all words), and falls back to caption words only when no subject matches (`--wide` merges all three). It saves a random sample (`--seed` for another one) as native 16x16 PNGs plus `matches.json` with row ids and captions. `sheet.js` uses codixel's `P.sheet` to make one numbered sheet with a zoomed grid and a 1x row; save it over the same file each round, as codixel asks.

Put the preview folder where codixel previews go in the user's project. Show the sheet (Read it, give the path) and ask which one, or which parts of several, are closest. Never pick for the user.

What to do with the pick depends on the target size:

- **16x16 target.** The sprite is already pixel art. Use it as the base and change what the user asks (colors, a hat, a pose), with codixel's tools. Say once that it is an AI-made atlas sprite (see Rights).
- **Bigger target (32, 64, more).** Do not scale the 16x16 sprite up and call it done: it gives blocky art with no detail. Use it as a guide for silhouette, proportions, pose and palette. Draw at the target size with codixel (`P.solid`, `P.band`, `P.hueRamp` and so on), and keep the atlas sprite on every preview sheet as `--ref` so each round is compared with it. Still ask the user for a real reference first when the subject is complex, as codixel says; a 16x16 sprite is a weak reference for a detailed character.

`python -I scripts/atlas.py get ROW [ROW ...] --out <folder>` saves sprites by row id again later (for example at `--scale 8`).

## 2. Palettes

```
python -I scripts/atlas.py palette "green slime" --k 8 --out <folder>
```

Gives the main colors used by sprites of that subject (each sprite counts the same), sorted dark to light, with their share, and the usual number of colors per sprite. Writes `palette.json` and a `palette.png` swatch. Use them in codixel:

```js
const pal = JSON.parse(fs.readFileSync("<folder>/palette.json")).colors;
P.quantize(buf, pal.length, { palette: pal.map(P.col) });   // map to these colors
const ramp = P.hueRampFrom(pal, 6);                           // or build a hue-shifted ramp from them
```

Make the query specific about color: `slime` mixes green, blue, red and black slimes into mud; `green slime` gives a clean ramp. The darkest color is usually the outline color. The palette is a starting point; codixel's style rules (hue shifting, muted real colors when the user says "realistic") still win, and a color the user names wins over the atlas.

## 3. Benchmark

```
python -I scripts/atlas.py bench <sprite.png> --like slime
```

Compares a finished sprite with up to 1,000 atlas sprites of the subject. Bigger sprites are trimmed and shrunk to 16 first (`--at 0` compares as is, `--at 32` at another size). For each stat it prints yours next to the atlas 10th percentile, median and 90th percentile, and marks what is outside:

| stat | what it measures | low means | high means |
|---|---|---|---|
| `colors` | distinct colors | too few tones, flat | noisy, too many near-duplicates |
| `top_share` | share of the most used color | | one flat color covers the body |
| `fill` | opaque share of the bounding box | thin or spiky | a block with no shape |
| `value_range` | lightness spread p5..p95 | flat shading, no ramp | |
| `saturation` | mean saturation | washed out | candy colors |
| `dark_edge` | silhouette pixels in the darkest quarter | no outline | |

Use it as one more line in codixel's "Check before you show", not as the judge. The atlas is one style (outlined, saturated, game icon). If the user asked for something else (no outline, muted, realistic), a flag on that stat is expected: say so instead of "fixing" it. A flag is a question to look at the sprite again, then fix it with codixel the way codixel says (change by about half, one thing at a time).

## Files

- `scripts/atlas.py` — setup, subjects, search, get, palette, bench. numpy + Pillow only.
- `scripts/sheet.js` — numbered review sheet with codixel's `P.sheet`. Finds codixel at `$CODIXEL_DIR` or `~/.claude/skills/codixel`.
