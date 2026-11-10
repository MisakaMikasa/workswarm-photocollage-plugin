"""Render sample posts straight through the engine (no WorkSwarm needed).

usage: python dev/run_samples.py <photo_dir> <out_dir>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vibe-post-studio" / "tools"))
import vibepost_engine as eng  # noqa: E402

photo_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
P = sorted(str(p) for p in photo_dir.glob("*.jpg"))
out_dir.mkdir(parents=True, exist_ok=True)

# One copy with FAKE EXIF so the stats strip / date stamp paths are exercised.
fake = out_dir / "_fake_exif_resatka-03.jpg"
with Image.open(P[2]) as im:
    ex = im.getexif()
    ex[0x010F], ex[0x0110] = "FUJIFILM", "X100V"
    sub = ex.get_ifd(0x8769)
    sub.update({0x920A: 23.0, 0x829D: 2.0, 0x829A: 1 / 250, 0x8827: 400,
                0x9003: "2024:10:17 17:42:05", 0xA434: "23mm F2"})
    im.save(fake, exif=ex, quality=95)
FAKE = str(fake)

SAMPLES = {
    "01-film-roll": {
        "format": "4:5",
        "background": {"color": "#efe8dc", "texture": "paper"},
        "photos": [P[0], P[7], P[9]],
        "layout": {"template": "filmstrip", "frames": 3, "strip_width": 0.6, "tilt": -3, "offset_x": 0.14,
                   "offset_y": 0.02},
        "date_stamp": {"photos": "all", "text": "'24 10 17"},
        "texts": [
            {"text": "autumn\nroll", "box": [0.05, 0.05, 0.26, 0.14], "font": "typewriter", "size": 0.05,
             "color": "#2b2622"},
            {"text": "秋天的胶卷 · 03", "box": [0.05, 0.2, 0.26, 0.05], "font": "typewriter", "size": 0.026,
             "color": "#6b5e52"},
            {"text": "three frames\nfrom a slow\nweekend.", "box": [0.05, 0.8, 0.26, 0.15], "font": "typewriter",
             "size": 0.026, "line_height": 1.4, "color": "#6b5e52"},
        ],
    },
    "02-gallery": {
        "format": "4:5",
        "background": "#f6f5f2",
        "photos": [FAKE],
        "layout": {"template": "single", "margin": 0.1, "bottom_space": 0.12},
        "frame": {"style": "keyline", "width": 1, "color": "#d8d6d0"},
        "texts": [
            {"text": "{camera:0}", "box": [0.1, 0.835, 0.5, 0.04], "font": "sans", "weight": 600, "size": 0.024,
             "tracking": 0.12, "uppercase": True, "color": "#1d1d1f"},
            {"text": "{settings:0}", "box": [0.1, 0.875, 0.8, 0.04], "font": "mono", "size": 0.02,
             "color": "#77746e"},
            {"text": "Yosemite, 2024", "box": [0.5, 0.835, 0.4, 0.04], "font": "serif_italic", "size": 0.03,
             "align": "right", "color": "#1d1d1f"},
        ],
    },
    "03-travel-journal": {
        "format": "4:5",
        "background": {"color": "#f1e9da", "texture": "paper"},
        "photos": [
            {"path": P[1], "caption": "the castle 🏰"},
            {"path": P[6], "caption": "our cabin"},
            {"path": P[4], "caption": "sea day"},
            {"path": P[5], "caption": "foggy morning"},
        ],
        "layout": {"template": "polaroids", "margin": 0.05, "top_space": 0.1, "bottom_space": 0.06},
        "frame": {"style": "polaroid", "shadow": True},
        "decorations": [
            {"type": "tape", "photo": 0}, {"type": "tape", "photo": 3},
            {"type": "postmark", "at": [0.86, 0.075], "lines": ["BAVARIA", "OCT 2024"], "size": 0.065},
            {"type": "swatches", "colors": "auto", "box": [0.06, 0.935, 0.3, 0.035], "count": 5, "labels": False},
            {"type": "sticker", "shape": "sparkle", "at": [0.92, 0.93], "size": 0.03, "color": "#e0a84c"},
        ],
        "texts": [
            {"text": "Two weeks, no plans ✈️", "box": [0.06, 0.03, 0.66, 0.07], "font": "hand", "size": 0.065,
             "color": "#3b2f2a"},
        ],
    },
    "04-magazine": {
        "format": "4:5",
        "background": "#fbfaf7",
        "photos": [P[8], P[3], P[2]],
        "layout": {"template": "magazine", "hero": 0.63, "margin": 0.06},
        "texts": [
            {"text": "Into\nthe Wild", "box": [0.06, 0.66, 0.38, 0.22], "font": "serif", "weight": 700, "size": 0.085,
             "line_height": 1.0, "color": "#141414"},
            {"text": "ISSUE 07 — AUTUMN EDITION", "box": [0.06, 0.9, 0.34, 0.04], "font": "sans", "weight": 600,
             "size": 0.018, "tracking": 0.25, "color": "#9a6b3c"},
            {"text": "VOL.07", "box": [0.72, 0.03, 0.24, 0.05], "font": "sans", "weight": 800, "size": 0.03,
             "tracking": 0.2, "align": "right", "color": "#ffffff",
             "effects": {"shadow": {"opacity": 0.5}}},
        ],
    },
    "05-moody-grid": {
        "format": "4:5",
        "background": "#121212",
        "photos": [P[5], P[8], P[2], P[9], P[4], P[7]],
        "layout": {"template": "grid", "cols": 2, "margin": 0.05, "gap": 0.012, "top_space": 0.1},
        "texts": [
            {"text": "QUIET PLACES", "box": [0.05, 0.035, 0.6, 0.06], "font": "sans", "weight": 800, "size": 0.045,
             "tracking": 0.18, "color": "#f2f2f2"},
            {"text": "安静的地方", "box": [0.6, 0.045, 0.35, 0.05], "font": "sans", "weight": 300, "size": 0.032,
             "align": "right", "color": "#bdbdbd"},
        ],
    },
    "06-carousel": {
        "format": "4:5",
        "slides": 3,
        "background": {"color": "#e9e4da", "texture": "paper"},
        "photos": [P[0], P[2], P[3], P[9], P[6]],
        "layout": {"template": "carousel", "tilt": 2},
        "frame": {"style": "matte", "shadow": True},
        "texts": [
            {"text": "swipe →", "box": [0.06, 0.92, 0.3, 0.05], "font": "hand", "size": 0.05, "color": "#5a4a3c"},
            {"text": "fin.", "box": [2.7, 0.9, 0.25, 0.06], "font": "serif_italic", "size": 0.05, "align": "right",
             "color": "#5a4a3c"},
        ],
    },
}

t0 = time.time()
ins = eng.inspect_photos(P + [FAKE], contact_sheet_dir=str(out_dir))
print("inspect:", len(ins["photos"]), "photos, errors:", ins["errors"])
print(json.dumps(ins["photos"][-1], ensure_ascii=False)[:600])
for name, spec in SAMPLES.items():
    t = time.time()
    res = eng.render_post(spec, str(out_dir), name)
    print(f"{name}: {time.time() - t:.2f}s files={[Path(f['path']).name for f in res['files']]} warnings={res['warnings']}")
print(f"total {time.time() - t0:.1f}s")
