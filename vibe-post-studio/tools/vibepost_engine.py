"""Vibe Post Studio rendering engine (Pillow only).

Shared by photo_inspect_tool.py and post_render_tool.py. Photos are opened
read-only; their pixels are only colour-managed to sRGB, cropped, resized and
(optionally) rotated as a whole tile. Output always goes to a caller-given
directory.
"""

from __future__ import annotations

import io
import json
import math
import os
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageCms, ImageDraw, ImageFilter, ImageFont, ImageOps

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONT_DIR = ASSETS / "fonts"
DEFAULT_WIDTH = 1080
FORMATS = {"1:1": (1, 1), "4:5": (4, 5), "3:4": (3, 4), "9:16": (9, 16), "2:3": (2, 3)}
SRGB = ImageCms.createProfile("sRGB")


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------


def _system_font_dirs() -> list[Path]:
    dirs: list[Path] = []
    if sys.platform.startswith("win"):
        dirs.append(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        dirs += [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts")]
    else:
        dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]
    return [d for d in dirs if d.is_dir()]


_SYSTEM_CANDIDATES = {
    "cjk_sans": ["NotoSansSC-VF.ttf", "msyh.ttc", "simhei.ttf", "PingFang.ttc", "Hiragino Sans GB.ttc",
                 "NotoSansCJK-Regular.ttc", "wqy-microhei.ttc"],
    "cjk_sans_bold": ["msyhbd.ttc", "simhei.ttf", "NotoSansCJK-Bold.ttc"],
    "cjk_serif": ["NotoSerifSC-VF.ttf", "simsun.ttc", "Songti.ttc", "NotoSerifCJK-Regular.ttc"],
    "cjk_kai": ["simkai.ttf", "STKAITI.TTF", "Kaiti.ttc"],
    "emoji": ["seguiemj.ttf"],
}
_system_cache: dict[str, str | None] = {}


def _find_system_font(kind: str) -> str | None:
    if kind in _system_cache:
        return _system_cache[kind]
    found = None
    for name in _SYSTEM_CANDIDATES.get(kind, []):
        for d in _system_font_dirs():
            hits = [d / name] if (d / name).exists() else list(d.rglob(name))[:1]
            if hits:
                found = str(hits[0])
                break
        if found:
            break
    _system_cache[kind] = found
    return found


ROLE_FONTS = {
    "sans": ["Inter.ttf"],
    "serif": ["PlayfairDisplay.ttf"],
    "serif_italic": ["PlayfairDisplay-Italic.ttf"],
    "hand": ["Caveat.ttf"],
    "script": ["DancingScript.ttf"],
    "marker": ["PermanentMarker.ttf"],
    "scrawl": ["ReenieBeanie.ttf"],
    "typewriter": ["SpecialElite.ttf"],
    "mono": ["SpaceMono.ttf"],
    "mono_bold": ["SpaceMono-Bold.ttf"],
    "digital": ["DSEG7Classic-BoldItalic.ttf", "SpaceMono-Bold.ttf"],
}
ROLE_CJK = {"serif": "cjk_serif", "serif_italic": "cjk_serif", "hand": "cjk_kai", "script": "cjk_kai",
            "scrawl": "cjk_kai", "marker": "cjk_sans_bold", "typewriter": "cjk_serif"}


def font_chain(role: str, weight: int) -> list[str]:
    """Ordered font files for a role: bundled Latin font, CJK fallback, emoji, generic fallback."""
    if role not in ROLE_FONTS:
        role = "sans"
    chain = [str(FONT_DIR / f) for f in ROLE_FONTS[role] if (FONT_DIR / f).exists()]
    cjk_kinds = [ROLE_CJK.get(role, "cjk_sans"), "cjk_sans"]
    if weight >= 600 and cjk_kinds[0] == "cjk_sans":
        cjk_kinds.insert(0, "cjk_sans_bold")
    for kind in [*cjk_kinds, "emoji"]:
        path = _find_system_font(kind)
        if path and path not in chain:
            chain.append(path)
    inter = str(FONT_DIR / "Inter.ttf")
    if inter not in chain:
        chain.append(inter)
    return chain


_cmap_cache: dict[str, set[int]] = {}
_font_cache: dict[tuple[str, int, int], ImageFont.FreeTypeFont] = {}


def _covers(path: str, ch: str) -> bool:
    if path not in _cmap_cache:
        try:
            _cmap_cache[path] = set(TTFont(path, fontNumber=0, lazy=True).getBestCmap() or {})
        except Exception:  # noqa: BLE001
            _cmap_cache[path] = set()
    return ord(ch) in _cmap_cache[path]


def get_font(path: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    """Load a font at a pixel size, applying the weight axis when the font is variable."""
    key = (path, size, weight)
    if key in _font_cache:
        return _font_cache[key]
    font = ImageFont.truetype(path, size, index=0)
    try:
        axes = font.get_variation_axes()
    except Exception:  # noqa: BLE001
        axes = []
    if axes:
        values = []
        for axis in axes:
            name = axis.get("name", b"")
            name = name.decode("utf-8", "ignore") if isinstance(name, bytes) else str(name)
            if name.lower().startswith("weight"):
                values.append(max(axis["minimum"], min(axis["maximum"], weight)))
            elif name.lower().startswith("optical"):
                values.append(max(axis["minimum"], min(axis["maximum"], size * 0.75)))
            else:
                values.append(axis["default"])
        try:
            font.set_variation_by_axes(values)
        except Exception:  # noqa: BLE001
            pass
    _font_cache[key] = font
    return font


def _is_emoji_font(path: str) -> bool:
    return "emoji" in Path(path).name.lower() or Path(path).name.lower().startswith("seguiemj")


class RichFont:
    """A role's font chain at one size/weight, with per-character fallback."""

    def __init__(self, role: str, size: int, weight: int = 400) -> None:
        self.size = max(6, int(size))
        self.weight = weight
        self.chain = font_chain(role, weight)
        self.primary = get_font(self.chain[0], self.size, weight)

    def runs(self, text: str) -> list[tuple[str, str]]:
        out: list[list[str]] = []
        for ch in text:
            if out and (ch.isspace() or ch in "\u200d\ufe0f"):
                out[-1][1] += ch
                continue
            path = next((p for p in self.chain if _covers(p, ch)), self.chain[0])
            if out and out[-1][0] == path:
                out[-1][1] += ch
            else:
                out.append([path, ch])
        return [(p, s) for p, s in out]

    def font_for(self, path: str) -> ImageFont.FreeTypeFont:
        return get_font(path, self.size, 400 if _is_emoji_font(path) else self.weight)

    def measure(self, draw: ImageDraw.ImageDraw, text: str, tracking: float = 0) -> float:
        total = 0.0
        for path, s in self.runs(text):
            f = self.font_for(path)
            emoji = _is_emoji_font(path)
            if tracking:
                total += sum(draw.textlength(c, font=f, embedded_color=emoji) + tracking for c in s)
            else:
                total += draw.textlength(s, font=f, embedded_color=emoji)
        return total

    def draw(self, draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fill: Any,
             tracking: float = 0, stroke: int = 0, stroke_fill: Any = None, color_emoji: bool = True) -> None:
        x, y = xy
        for path, s in self.runs(text):
            f = self.font_for(path)
            emoji = _is_emoji_font(path)
            pieces = list(s) if tracking else [s]
            for piece in pieces:
                kwargs: dict[str, Any] = {"font": f, "fill": fill, "anchor": "ls"}
                if emoji and color_emoji:
                    kwargs["embedded_color"] = True
                elif stroke:
                    kwargs.update(stroke_width=stroke, stroke_fill=stroke_fill)
                draw.text((x, y), piece, **kwargs)
                x += draw.textlength(piece, font=f, embedded_color=emoji and color_emoji) + (tracking or 0)


# ---------------------------------------------------------------------------
# Text layout
# ---------------------------------------------------------------------------

_NO_LINE_START = set("，。、！？；：）」』】》,.!?;:)%")


def _is_cjk(ch: str) -> bool:
    return "\u2e80" <= ch <= "\u9fff" or "\uf900" <= ch <= "\ufaff" or "\uff00" <= ch <= "\uffef" or "\u3000" <= ch <= "\u303f"


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if _is_cjk(ch) or ch in _NO_LINE_START:
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        elif ch == " ":
            tokens.append(buf + ch)
            buf = ""
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    return tokens


def wrap_text(text: str, measure, width: float) -> list[str]:
    """Wrap Latin at spaces and CJK at any character; never start a line with closing punctuation."""
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for tok in _tokens(para):
            if not cur or measure(cur + tok) <= width or tok in _NO_LINE_START:
                cur += tok
            else:
                lines.append(cur.rstrip())
                cur = tok.lstrip()
                while measure(cur) > width and len(cur) > 1:  # break over-long words
                    i = len(cur) - 1
                    while i > 1 and measure(cur[:i]) > width:
                        i -= 1
                    lines.append(cur[:i])
                    cur = cur[i:]
        lines.append(cur.rstrip())
    return lines


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------


def parse_color(value: Any, default: tuple[int, ...] = (0, 0, 0, 255)) -> tuple[int, int, int, int]:
    """Accept '#rgb', '#rrggbb', '#rrggbbaa', [r,g,b(,a)] or a few names."""
    names = {"white": "#ffffff", "black": "#000000", "cream": "#f4efe6", "paper": "#f3eee4",
             "ink": "#1d1d1f", "orange": "#ff8a2a", "transparent": "#00000000"}
    if value is None:
        return tuple(default) if len(default) == 4 else (*default, 255)  # type: ignore[return-value]
    if isinstance(value, (list, tuple)):
        vals = [int(v) for v in value]
        return (*vals[:3], vals[3] if len(vals) > 3 else 255)  # type: ignore[return-value]
    s = str(value).strip().lower()
    s = names.get(s, s)
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) in (6, 8):
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            a = int(h[6:8], 16) if len(h) == 8 else 255
            return (r, g, b, a)
    raise ValueError(f"unrecognised colour: {value!r}")


def with_alpha(color: tuple[int, int, int, int], alpha: float) -> tuple[int, int, int, int]:
    return (color[0], color[1], color[2], int(color[3] * alpha))


# ---------------------------------------------------------------------------
# Photos: load, EXIF, analysis
# ---------------------------------------------------------------------------


def load_photo(path: str | Path) -> Image.Image:
    """Open read-only, apply EXIF orientation and convert to sRGB using the embedded profile."""
    with Image.open(path) as src:
        img = ImageOps.exif_transpose(src)
        icc = src.info.get("icc_profile")
        img.load()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    if icc:
        try:
            in_prof = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            img = ImageCms.profileToProfile(img.convert("RGB"), in_prof, SRGB, outputMode="RGB")
        except Exception:  # noqa: BLE001
            img = img.convert("RGB")
    return img.convert("RGB")


def _ratio(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:  # noqa: BLE001
        try:
            return float(v[0]) / float(v[1])
        except Exception:  # noqa: BLE001
            return None


def _fmt_num(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def read_exif(path: str | Path) -> dict[str, Any]:
    """Camera facts from EXIF. Missing values are left out, never guessed."""
    out: dict[str, Any] = {}
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            sub = exif.get_ifd(0x8769)
            gps = exif.get_ifd(0x8825)
    except Exception:  # noqa: BLE001
        return out
    make = str(exif.get(0x010F, "") or "").strip().strip("\x00")
    model = str(exif.get(0x0110, "") or "").strip().strip("\x00")
    if model:
        out["camera"] = model if make and make.split()[0].lower() in model.lower() else f"{make} {model}".strip()
    elif make:
        out["camera"] = make
    lens = str(sub.get(0xA434, "") or "").strip().strip("\x00")
    if lens:
        out["lens"] = lens
    focal = _ratio(sub.get(0x920A))
    if focal:
        out["focal_length"] = f"{_fmt_num(focal)}mm"
    f35 = sub.get(0xA405)
    if f35:
        out["focal_length_35mm"] = f"{int(f35)}mm"
    fnum = _ratio(sub.get(0x829D))
    if fnum:
        out["aperture"] = f"f/{_fmt_num(fnum)}"
    exp = _ratio(sub.get(0x829A))
    if exp:
        out["shutter"] = f"1/{round(1 / exp)}s" if exp < 1 else f"{_fmt_num(exp)}s"
    iso = sub.get(0x8827)
    if isinstance(iso, (tuple, list)):
        iso = iso[0] if iso else None
    if iso:
        out["iso"] = f"ISO {int(iso)}"
    dt = sub.get(0x9003) or exif.get(0x0132)
    if dt:
        m = re.match(r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2})", str(dt))
        if m:
            out["datetime"] = f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}"
    try:
        if gps and 2 in gps and 4 in gps:
            def deg(v: Any) -> float:
                return float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            lat = deg(gps[2]) * (-1 if gps.get(1) == "S" else 1)
            lon = deg(gps[4]) * (-1 if gps.get(3) == "W" else 1)
            out["gps"] = {"lat": round(lat, 5), "lon": round(lon, 5)}
    except Exception:  # noqa: BLE001
        pass
    settings = [out[k] for k in ("focal_length", "aperture", "shutter", "iso") if k in out]
    if settings:
        out["settings"] = "  ".join(settings)
    return out


def analyse(img: Image.Image) -> dict[str, Any]:
    """Palette, brightness, warmth and a rough focus point (where the detail is)."""
    small = img.copy()
    small.thumbnail((160, 160))
    q = small.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors() or [], reverse=True)
    palette = []
    for count, idx in counts[:5]:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        palette.append({"hex": f"#{r:02x}{g:02x}{b:02x}", "share": round(count / (small.width * small.height), 2)})
    arr = np.asarray(small.convert("RGB"), dtype=np.float32)
    lum = arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    brightness = float(lum.mean() / 255)
    warmth = float((arr[..., 0].mean() - arr[..., 2].mean()) / 255)
    gx = np.abs(np.diff(lum, axis=1))[:-1, :]
    gy = np.abs(np.diff(lum, axis=0))[:, :-1]
    mag = (gx + gy) ** 2
    if mag.sum() > 0:
        ys, xs = np.mgrid[0:mag.shape[0], 0:mag.shape[1]]
        fx = float((xs * mag).sum() / mag.sum() / mag.shape[1])
        fy = float((ys * mag).sum() / mag.sum() / mag.shape[0])
    else:
        fx = fy = 0.5
    fx, fy = 0.5 + (fx - 0.5) * 0.6, 0.5 + (fy - 0.5) * 0.6  # stay conservative
    return {
        "palette": palette,
        "brightness": round(brightness, 2),
        "tone": "dark" if brightness < 0.35 else "bright" if brightness > 0.65 else "mid",
        "warmth": "warm" if warmth > 0.06 else "cool" if warmth < -0.04 else "neutral",
        "focus": [round(fx, 2), round(fy, 2)],
    }


def _dhash(img: Image.Image) -> int:
    g = np.asarray(img.convert("L").resize((9, 8), Image.Resampling.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def _km(a: dict[str, float], b: dict[str, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, h)))


def suggest_groups(photos: list[dict[str, Any]], gap_hours: float = 3.0, gap_km: float = 3.0) -> dict[str, Any]:
    """Group photos by shooting time, GPS distance and folder. Content grouping is left to the agent."""

    def ts(p: dict[str, Any]) -> datetime | None:
        dt = p["exif"].get("datetime")
        return datetime.strptime(dt, "%Y-%m-%d %H:%M") if dt else None

    timed = sorted((p for p in photos if ts(p)), key=lambda p: ts(p))  # type: ignore[arg-type,return-value]
    untimed = [p for p in photos if not ts(p)]
    groups: list[list[dict[str, Any]]] = []
    for p in timed:
        prev = groups[-1][-1] if groups else None
        new = prev is None or (ts(p) - ts(prev)).total_seconds() > gap_hours * 3600  # type: ignore[operator]
        if not new and prev and p["exif"].get("gps") and prev["exif"].get("gps"):
            new = _km(p["exif"]["gps"], prev["exif"]["gps"]) > gap_km
        if new:
            groups.append([p])
        else:
            groups[-1].append(p)
    basis = ["time"] if timed else []
    if any(p["exif"].get("gps") for p in photos):
        basis.append("gps")
    if untimed:
        geo = [p for p in untimed if p["exif"].get("gps")]
        rest = [p for p in untimed if not p["exif"].get("gps")]
        for p in geo:
            for g in groups:
                if g[0]["exif"].get("gps") and _km(g[0]["exif"]["gps"], p["exif"]["gps"]) <= gap_km and not ts(g[0]):
                    g.append(p)
                    break
            else:
                groups.append([p])
        folders: dict[str, list[dict[str, Any]]] = {}
        for p in rest:
            folders.setdefault(str(Path(p["path"]).parent), []).append(p)
        if len(folders) > 1 or (folders and groups):
            basis.append("folder")
        groups.extend(folders.values())

    out = []
    for g in groups:
        item: dict[str, Any] = {"photos": [p["index"] for p in g]}
        times = [ts(p) for p in g if ts(p)]
        if times:
            item["time"] = f"{min(times):%Y-%m-%d %H:%M} – {max(times):%H:%M}" if min(times).date() == max(times).date() \
                else f"{min(times):%Y-%m-%d} – {max(times):%Y-%m-%d}"
        gps = [p["exif"]["gps"] for p in g if p["exif"].get("gps")]
        if gps:
            item["gps_center"] = {"lat": round(sum(x["lat"] for x in gps) / len(gps), 4),
                                  "lon": round(sum(x["lon"] for x in gps) / len(gps), 4)}
        if not times and not gps:
            item["folder"] = Path(g[0]["path"]).parent.name
        out.append(item)

    similar = []
    for a in range(len(photos)):
        for b in range(a + 1, len(photos)):
            if bin(photos[a]["_dhash"] ^ photos[b]["_dhash"]).count("1") <= 8:
                similar.append([photos[a]["index"], photos[b]["index"]])
    note = ("No time/GPS metadata: these groups are by folder only. Group by content using the contact sheet "
            "if you can see images; otherwise ask the user.") if not basis or basis == ["folder"] else \
        "Groups are by shooting time / location. Refine by content if you can see images; user direction overrides."
    return {"basis": basis or ["none"], "groups": out, "near_duplicates": similar, "note": note}


def inspect_photos(paths: list[str], contact_sheet_dir: str | None = None) -> dict[str, Any]:
    """Facts about each photo, suggested groups and an optional numbered contact sheet."""
    photos: list[dict[str, Any]] = []
    errors: list[str] = []
    thumbs: list[Image.Image] = []
    for i, p in enumerate(paths):
        path = Path(p).expanduser()
        if not path.is_file():
            errors.append(f"photo {i}: not found: {p}")
            continue
        try:
            img = load_photo(path)
        except Exception as e:  # noqa: BLE001
            errors.append(f"photo {i}: cannot open {p}: {e}")
            continue
        w, h = img.size
        info: dict[str, Any] = {
            "index": i,
            "path": str(path.resolve()),
            "width": w,
            "height": h,
            "orientation": "landscape" if w > h * 1.05 else "portrait" if h > w * 1.05 else "square",
            "aspect": round(w / h, 3),
            "exif": read_exif(path),
        }
        info.update(analyse(img))
        info["_dhash"] = _dhash(img)
        photos.append(info)
        t = img.copy()
        t.thumbnail((360, 360))
        thumbs.append(t)
    result: dict[str, Any] = {"success": bool(photos), "photos": photos, "errors": errors}
    if photos:
        result["grouping"] = suggest_groups(photos)
    for p in photos:
        p.pop("_dhash", None)
    if contact_sheet_dir and thumbs:
        out_dir = Path(contact_sheet_dir).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        cols = min(5, len(thumbs))
        rows = math.ceil(len(thumbs) / cols)
        cell_w, cell_h = 370, 410
        sheet = Image.new("RGB", (cols * cell_w + 10, rows * cell_h + 10), (250, 250, 250))
        d = ImageDraw.Draw(sheet)
        badge = RichFont("mono_bold", 30)
        label = RichFont("mono", 18)
        for k, (t, info) in enumerate(zip(thumbs, photos)):
            x, y = 10 + (k % cols) * cell_w, 10 + (k // cols) * cell_h
            sheet.paste(t, (x + (360 - t.width) // 2, y + (360 - t.height) // 2))
            d.rounded_rectangle((x + 4, y + 4, x + 74, y + 48), radius=8, fill=(20, 20, 20))
            badge.draw(d, (x + 12, y + 38), f"#{info['index']}", (255, 255, 255, 255))
            sub = info["exif"].get("datetime", "") or Path(info["path"]).name
            label.draw(d, (x + 4, y + 390), f"{info['orientation'][:4]}  {sub}"[:34], (60, 60, 60, 255))
        sheet_path = out_dir / "contact_sheet.jpg"
        sheet.save(sheet_path, quality=88)
        result["contact_sheet"] = str(sheet_path.resolve())
    return result


def crop_to(img: Image.Image, w: int, h: int, focus: tuple[float, float] = (0.5, 0.5)) -> tuple[Image.Image, float]:
    """Crop to w:h around the focus point, resize with LANCZOS. Returns image and upscale factor."""
    sw, sh = img.size
    target = w / h
    if sw / sh > target:
        cw, ch = sh * target, sh
    else:
        cw, ch = sw, sw / target
    cx = min(max(focus[0] * sw, cw / 2), sw - cw / 2)
    cy = min(max(focus[1] * sh, ch / 2), sh - ch / 2)
    box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    scale = w / cw
    return img.resize((max(1, w), max(1, h)), Image.Resampling.LANCZOS, box=box), scale


# ---------------------------------------------------------------------------
# Spec model
# ---------------------------------------------------------------------------


@dataclass
class Slot:
    x: float
    y: float
    w: float
    h: float
    rotate: float = 0.0


@dataclass
class Ctx:
    W: int
    H: int
    slides: int
    canvas: Image.Image
    spec: dict[str, Any]
    photos: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    photo_rects: dict[int, tuple[float, float, float, float, float]] = field(default_factory=dict)
    rng: random.Random = field(default_factory=lambda: random.Random(7))
    theme: dict[str, Any] = field(default_factory=dict)
    boxes: list[dict[str, Any]] = field(default_factory=list)  # drawn elements, for overlap checks
    photo_boxes: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)  # photo area
    tile_boxes: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)  # photo + frame

    def px(self, box: list[float]) -> tuple[float, float, float, float]:
        x, y, w, h = box
        return x * self.W, y * self.H, w * self.W, h * self.H


def _canvas_size(spec: dict[str, Any]) -> tuple[int, int]:
    width = int(spec.get("width", DEFAULT_WIDTH))
    fmt = spec.get("format", "4:5")
    if isinstance(fmt, dict):
        return int(fmt["w"]), int(fmt["h"])
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; use one of {sorted(FORMATS)} or {{'w':..,'h':..}}")
    a, b = FORMATS[fmt]
    return width, round(width * b / a)


def _norm_photos(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for p in spec.get("photos", []):
        item = {"path": p} if isinstance(p, str) else dict(p)
        if not Path(item["path"]).expanduser().is_file():
            raise FileNotFoundError(f"photo not found: {item['path']}")
        out.append(item)
    if not out:
        raise ValueError("spec.photos is empty")
    return out


# ---------------------------------------------------------------------------
# Layout templates -> slots (x,w in slide widths; y,h in slide heights)
# ---------------------------------------------------------------------------


def _grid_shape(n: int, aspect: float) -> tuple[int, int]:
    best = (1, n)
    best_score = 1e9
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        empty = rows * cols - n
        cell = (aspect / cols) / (1 / rows)
        score = abs(math.log(cell / 0.85)) + empty * 0.7
        if score < best_score:
            best, best_score = (cols, rows), score
    return best


def layout_slots(ctx: Ctx) -> list[Slot]:
    lay = ctx.spec.get("layout", {"template": "grid"})
    if isinstance(lay, str):
        lay = {"template": lay}
    t = lay.get("template", "grid")
    n = len(ctx.photos)
    m = float(lay.get("margin", 0.06))
    g = float(lay.get("gap", 0.02))
    aspect = ctx.W / ctx.H  # slide aspect (w/h)
    mx, my = m, m * aspect  # equal pixel margins
    gx, gy = g, g * aspect
    slots: list[Slot] = []

    if t == "free":
        for s in lay.get("slots", []):
            slots.append(Slot(s["x"], s["y"], s["w"], s["h"], float(s.get("rotate", 0))))
    elif t == "single":
        bottom = float(lay.get("bottom_space", 0.0))
        slots.append(Slot(mx, my, 1 - 2 * mx, 1 - 2 * my - bottom))
    elif t == "grid":
        top = float(lay.get("top_space", 0.0))
        bottom = float(lay.get("bottom_space", 0.0))
        cols = int(lay.get("cols", 0)) or _grid_shape(n, aspect * (1 - 2 * my - top - bottom) / (1 - 2 * mx))[0]
        rows = math.ceil(n / cols)
        cw = (1 - 2 * mx - gx * (cols - 1)) / cols
        ch = (1 - 2 * my - top - bottom - gy * (rows - 1)) / rows
        for i in range(n):
            r, c = divmod(i, cols)
            slots.append(Slot(mx + c * (cw + gx), my + top + r * (ch + gy), cw, ch))
    elif t in ("hero", "hero-side"):
        frac = float(lay.get("hero", 0.62))
        rest = max(0, n - 1)
        top = float(lay.get("top_space", 0.0))
        bottom = float(lay.get("bottom_space", 0.0))
        avail_h = 1 - 2 * my - top - bottom
        if t == "hero":
            hh = avail_h * frac if rest else avail_h
            slots.append(Slot(mx, my + top, 1 - 2 * mx, hh))
            if rest:
                cw = (1 - 2 * mx - gx * (rest - 1)) / rest
                for i in range(rest):
                    slots.append(Slot(mx + i * (cw + gx), my + top + hh + gy, cw, avail_h - hh - gy))
        else:
            hw = (1 - 2 * mx) * frac if rest else 1 - 2 * mx
            slots.append(Slot(mx, my + top, hw, avail_h))
            if rest:
                ch = (avail_h - gy * (rest - 1)) / rest
                for i in range(rest):
                    slots.append(Slot(mx + hw + gx, my + top + i * (ch + gy), 1 - 2 * mx - hw - gx, ch))
    elif t == "filmstrip":
        k = min(n, int(lay.get("frames", 3)))
        if n > k:
            ctx.warnings.append(f"filmstrip shows {k} frames; photos {k}..{n - 1} were not used")
        strip_w = float(lay.get("strip_width", 0.7))
        frame_ratio = float(lay.get("frame_ratio", 1.5))
        tilt = float(lay.get("tilt", 0))
        sx = (1 - strip_w) / 2 + float(lay.get("offset_x", 0))
        fw = strip_w * 0.8
        fh = fw * ctx.W / frame_ratio / ctx.H
        fgap = 0.035 * aspect
        total = k * fh + (k - 1) * fgap
        y0 = (1 - total) / 2 + float(lay.get("offset_y", 0))
        ctx.spec.setdefault("_underlays", []).append(
            {"type": "film_strip", "box": [sx, -0.1, strip_w, 1.2], "rotate": tilt})
        ccx, ccy = (sx + strip_w / 2) * ctx.W, 0.5 * ctx.H  # strip centre in px
        th = math.radians(tilt)
        for i in range(k):
            px_, py_ = (sx + strip_w / 2) * ctx.W, (y0 + i * (fh + fgap) + fh / 2) * ctx.H
            dx, dy = px_ - ccx, py_ - ccy
            rx = ccx + dx * math.cos(th) + dy * math.sin(th)
            ry = ccy - dx * math.sin(th) + dy * math.cos(th)
            slots.append(Slot(rx / ctx.W - fw / 2, ry / ctx.H - fh / 2, fw, fh, tilt))
        ctx.spec.setdefault("frame", {"style": "none"})
        ctx.photos[:] = ctx.photos[:k]
    elif t == "polaroids":
        top = float(lay.get("top_space", 0.0))
        bottom = float(lay.get("bottom_space", 0.0))
        avail_h = 1 - 2 * my - top - bottom
        cols, rows = _grid_shape(n, aspect * avail_h / (1 - 2 * mx))
        cell_w, cell_h = (1 - 2 * mx) / cols, avail_h / rows
        fit = min(cell_w * 0.92, cell_h * 0.92 / (aspect * 1.18))
        pw = float(lay.get("size", fit))
        ph = pw * aspect * 1.18
        for i in range(n):
            r, c = divmod(i, cols)
            cx = mx + (c + 0.5) * cell_w + ctx.rng.uniform(-0.03, 0.03)
            cy = my + top + (r + 0.5) * cell_h + ctx.rng.uniform(-0.02, 0.02)
            slots.append(Slot(cx - pw / 2, cy - ph / 2, pw, ph, ctx.rng.uniform(-9, 9)))
        ctx.spec.setdefault("frame", {"style": "polaroid", "shadow": True})
    elif t == "scatter":
        # loose, tilted, optionally overlapping arrangement (scrapbook / moodboard)
        overlap = max(0.0, min(0.45, float(lay.get("overlap", 0.12))))
        tilt = abs(float(lay.get("tilt", 6)))
        variety = max(0.0, min(0.5, float(lay.get("variety", 0.25))))
        top = float(lay.get("top_space", 0.0))
        bottom = float(lay.get("bottom_space", 0.0))
        area_w, area_h = 1 - 2 * mx, 1 - 2 * my - top - bottom
        hints = [float(p.get("_aspect_hint", 1.25)) for p in ctx.photos[:n]]  # photo h / w
        avg_hint = sum(hints) / len(hints) if hints else 1.25

        def fit_w(cols: int) -> float:  # photo width that fits a cell, in slide widths
            rows_ = math.ceil(n / cols)
            cw_, ch_ = area_w / cols, area_h / rows_
            return min(cw_, ch_ / (avg_hint * aspect))

        cols = max(range(1, n + 1), key=lambda k: (round(fit_w(k), 3), -abs(k - math.sqrt(n))))
        rows = math.ceil(n / cols)
        cw, ch = area_w / cols, area_h / rows
        spread = 0.12 + overlap * 0.6  # how far photos wander from their cell centre
        for i in range(n):
            r, c = divmod(i, cols)
            in_row = min(cols, n - r * cols)
            grow = (1 + overlap * 1.3) * (1 + (variety if i == 0 else ctx.rng.uniform(-variety, variety * 0.6)))
            w = fit_w(cols) * (0.88 if overlap == 0 else 1.0) * grow
            h = w * hints[i] * aspect
            if h > ch * (1 + overlap * 1.3):
                w, h = w * ch * (1 + overlap * 1.3) / h, ch * (1 + overlap * 1.3)
            row_shift = (cols - in_row) * cw / 2 + (cw * 0.18 if r % 2 else -cw * 0.18) * (overlap > 0)
            cx = mx + (c + 0.5) * cw + row_shift + ctx.rng.uniform(-1, 1) * cw * spread * 0.5
            cy = my + top + (r + 0.5) * ch + ctx.rng.uniform(-1, 1) * ch * spread * 0.5
            cx = min(max(cx, mx + w * 0.42), 1 - mx - w * 0.42)
            cy = min(max(cy, my + top + h * 0.45), 1 - my - bottom - h * 0.45)
            sign = 1 if (i + r) % 2 else -1
            rot = sign * ctx.rng.uniform(tilt * 0.35, tilt) if tilt else 0.0
            slots.append(Slot(cx - w / 2, cy - h / 2, w, h, rot))
    elif t == "magazine":
        bleed = float(lay.get("hero", 0.64))
        slots.append(Slot(0, 0, 1, bleed))
        rest = n - 1
        if rest:
            sw = 0.26
            sh = sw * aspect * 1.2
            for i in range(min(rest, 2)):
                slots.append(Slot(1 - mx - (i + 1) * sw - i * gx, bleed + (1 - bleed - sh) / 2, sw, sh))
            if rest > 2:
                ctx.warnings.append("magazine uses at most 3 photos; extra photos were not used")
                ctx.photos[:] = ctx.photos[:3]
    elif t == "carousel":
        k = ctx.slides
        x = 0.1
        span = k - 0.2
        # widths chosen so neighbours overlap by at most ~15%
        base = min(0.8, span / (n * 0.87 + 0.13)) if n else 0.8
        sizes = [base, base * 0.82]
        step = (span - sizes[0]) / max(1, n - 1) if n > 1 else 0
        for i in range(n):
            w = sizes[i % 2]
            h = w * aspect * float(ctx.photos[i].get("_aspect_hint", 1.25))
            h = min(h, 0.78)
            y = 0.1 if i % 2 == 0 else 0.9 - h
            slots.append(Slot(x + i * step, y, w, h, float(lay.get("tilt", 0)) * (1 if i % 2 else -1)))
    else:
        raise ValueError(f"unknown layout template {t!r}")
    return slots


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _shadow(canvas: Image.Image, tile: Image.Image, pos: tuple[int, int], strength: float = 0.35,
            blur: int = 14, offset: tuple[int, int] = (0, 10)) -> None:
    alpha = tile.getchannel("A")
    pad = blur * 3
    sh = Image.new("L", (alpha.width + pad * 2, alpha.height + pad * 2), 0)
    sh.paste(alpha.point(lambda a: int(a * strength)), (pad, pad))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    black = Image.new("RGBA", sh.size, (0, 0, 0, 255))
    black.putalpha(sh)
    canvas.alpha_composite(black, (pos[0] - pad + offset[0], pos[1] - pad + offset[1]))


def _paste(canvas: Image.Image, img: Image.Image, x: float, y: float) -> None:
    """alpha_composite that tolerates negative / out-of-canvas positions."""
    x, y = int(round(x)), int(round(y))
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(img.width, canvas.width - x), min(img.height, canvas.height - y)
    if right <= left or bottom <= top:
        return
    canvas.alpha_composite(img.crop((left, top, right, bottom)), (x + left, y + top))


def _draw_date_stamp(tile: Image.Image, rect: tuple[int, int, int, int], text: str, color: Any) -> None:
    x0, y0, x1, y1 = rect
    pw = x1 - x0
    size = max(12, int(pw * 0.07))
    font = RichFont("digital", size)
    layer = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    tw = font.measure(d, text)
    pos = (x1 - tw - pw * 0.05, y1 - pw * 0.05)
    col = parse_color(color or "#ff8a2a")
    font.draw(d, pos, text, col)
    glow = layer.filter(ImageFilter.GaussianBlur(max(2, size // 6)))
    tile.alpha_composite(glow)
    tile.alpha_composite(glow)
    tile.alpha_composite(layer)


def _stamp_text(photo: dict[str, Any], fmt: str) -> str:
    dt = photo.get("_exif", {}).get("datetime")
    if not dt:
        return ""
    y, mo, d = dt[2:4], dt[5:7], dt[8:10]
    return {"film": f"'{y} {mo} {d}", "dots": f"{d}.{mo}.{dt[:4]}", "iso": dt[:10]}.get(fmt, f"'{y} {mo} {d}")


def build_tile(ctx: Ctx, idx: int, slot: Slot) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Photo + frame as an RGBA tile of the slot's pixel size. Returns tile and photo rect inside it."""
    frame = dict(ctx.spec.get("frame") or {})
    frame.update(ctx.photos[idx].get("frame") or {})
    style = frame.get("style", "none")
    w, h = max(2, int(round(slot.w * ctx.W))), max(2, int(round(slot.h * ctx.H)))
    bw = int(frame.get("width", 0) or {"matte": 0.045, "polaroid": 0.06, "film": 0.05, "keyline": 0, "rounded": 0,
                                         "none": 0}.get(style, 0) * min(w, h) / 0.9)
    color = parse_color(frame.get("color", "#000000" if style == "film" else "#ffffff"))
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if style == "matte":
        rect = (bw, bw, w - bw, h - bw)
    elif style == "polaroid":
        rect = (bw, bw, w - bw, h - int(bw * 3.6))
    elif style == "film":
        rect = (int(bw * 0.5), int(bw * 1.6), w - int(bw * 0.5), h - int(bw * 1.6))
    else:
        rect = (0, 0, w, h)
    if style in ("matte", "polaroid", "film"):
        ImageDraw.Draw(tile).rectangle((0, 0, w, h), fill=color)
    pw, ph = rect[2] - rect[0], rect[3] - rect[1]
    photo = ctx.photos[idx]
    img = photo["_img"]
    focus = tuple(photo.get("focus") or photo.get("_focus") or (0.5, 0.5))
    crop, scale = crop_to(img, pw, ph, focus)  # type: ignore[arg-type]
    if scale > 1.3:
        ctx.warnings.append(f"photo {photo['_index']} is enlarged {scale:.1f}x beyond its resolution; it may look soft")
    crop = crop.convert("RGBA")
    radius = int(frame.get("radius", 0.04 * min(pw, ph) if style == "rounded" else 0))
    if radius:
        crop.putalpha(_rounded_mask(crop.size, radius))
    tile.alpha_composite(crop, (rect[0], rect[1]))
    d = ImageDraw.Draw(tile)
    if style == "keyline":
        lw = max(1, int(frame.get("width", 2)))
        d.rectangle((0, 0, w - 1, h - 1), outline=parse_color(frame.get("color", "#1d1d1f")), width=lw)
    if style == "film":
        hole_w, hole_h = max(4, int(bw * 0.55)), max(4, int(bw * 0.8))
        step = hole_w * 2.2
        hc = parse_color(frame.get("hole_color", ctx.spec.get("background", {}).get("color", "#f3eee4")
                                   if isinstance(ctx.spec.get("background"), dict) else "#f3eee4"))
        for yy in (int(bw * 0.4), h - int(bw * 0.4) - hole_h):
            x = hole_w * 0.6
            while x + hole_w < w:
                d.rounded_rectangle((x, yy, x + hole_w, yy + hole_h), radius=max(1, hole_w // 4), fill=hc)
                x += step
        edge = RichFont("mono_bold", max(9, int(bw * 0.45)))
        edge.draw(d, (bw * 0.7, h - int(bw * 1.6) + bw * 0.9), f"{idx + 12}  ▸  {idx + 12}A", (255, 150, 60, 230))
    cap = photo.get("caption")
    if style == "polaroid" and cap:
        f = RichFont(frame.get("caption_font", "hand"), max(12, int(bw * 1.5)))
        tw = f.measure(d, cap)
        f.draw(d, ((w - tw) / 2, h - bw * 1.35), cap, parse_color(frame.get("caption_color", "#2a2a2a")))
    stamp = photo.get("date_stamp") or ctx.spec.get("date_stamp")
    if stamp:
        cfg = stamp if isinstance(stamp, dict) else {}
        applies = cfg.get("photos", "all")
        if applies == "all" or idx in applies:
            text = cfg.get("text") or _stamp_text(photo, cfg.get("format", "film"))
            if text:
                _draw_date_stamp(tile, rect, text, cfg.get("color"))
            elif not cfg.get("text"):
                ctx.warnings.append(f"photo {photo['_index']}: no EXIF date, date stamp skipped (pass date_stamp.text)")
    return tile, rect


# ---------------------------------------------------------------------------
# Theme helpers
# ---------------------------------------------------------------------------

THEME_FONT_DEFAULTS = {"title": "serif", "body": "sans", "note": "hand"}
_COLOR_KEYS = ("color", "text_color", "outline", "label_color", "hole_color", "caption_color")


def _font_role(ctx: Ctx, role: str | None) -> str:
    fonts = ctx.theme.get("fonts", {}) or {}
    role = role or "body"
    return fonts.get(role) or THEME_FONT_DEFAULTS.get(role, role)


def _theme_color(ctx: Ctx, value: Any) -> Any:
    colors = ctx.theme.get("colors", {}) or {}
    return colors.get(value, value) if isinstance(value, str) else value


def _resolve_colors(ctx: Ctx, d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    for k, v in d.items():
        if k in _COLOR_KEYS:
            out[k] = _theme_color(ctx, v)
        elif k == "colors" and isinstance(v, list):
            out[k] = [_theme_color(ctx, c) for c in v]
    return out


def _register(ctx: Ctx, kind: str, label: str, box: tuple[float, float, float, float] | None, **extra: Any) -> None:
    if box and box[2] > box[0] and box[3] > box[1]:
        ctx.boxes.append({"kind": kind, "label": label, "box": box, **extra})


def _paste_rotated(ctx: Ctx, layer: Image.Image, cx: float, cy: float, rot: float) -> tuple[float, float, float, float] | None:
    """Rotate a layer about its centre, paste it centred at (cx, cy) and return the ink bounding box."""
    if rot:
        layer = layer.rotate(rot, expand=True, resample=Image.Resampling.BICUBIC)
    x, y = cx - layer.width / 2, cy - layer.height / 2
    _paste(ctx.canvas, layer, x, y)
    bb = layer.getchannel("A").getbbox()
    return (x + bb[0], y + bb[1], x + bb[2], y + bb[3]) if bb else None


# ---------------------------------------------------------------------------
# Decorations
# ---------------------------------------------------------------------------


def _star(cx: float, cy: float, r: float, points: int = 5, inner: float = 0.45) -> list[tuple[float, float]]:
    pts = []
    for k in range(points * 2):
        rad = r if k % 2 == 0 else r * inner
        a = math.pi * k / points - math.pi / 2
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


def _heart(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    pts = []
    for k in range(60):
        t = 2 * math.pi * k / 60
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * r / 17, cy - y * r / 17))
    return pts


def _torn_polygon(w: int, h: int, rng: random.Random, amp: float) -> list[tuple[float, float]]:
    """Rectangle outline with ragged edges (torn paper)."""
    pts: list[tuple[float, float]] = []
    step = max(6, int(min(w, h) * 0.03))
    for x in range(0, w + 1, step):
        pts.append((x, amp + rng.uniform(-amp, amp)))
    for y in range(0, h + 1, step):
        pts.append((w - amp + rng.uniform(-amp, amp), y))
    for x in range(w, -1, -step):
        pts.append((x, h - amp + rng.uniform(-amp, amp)))
    for y in range(h, -1, -step):
        pts.append((amp + rng.uniform(-amp, amp), y))
    return pts


def draw_decoration(ctx: Ctx, deco: dict[str, Any]) -> None:
    deco = _resolve_colors(ctx, deco)
    t = deco.get("type")
    c = ctx.canvas
    if t == "rect":
        x, y, w, h = ctx.px(deco["box"])
        layer = Image.new("RGBA", c.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle((x, y, x + w, y + h), radius=int(deco.get("radius", 0)),
                                                fill=parse_color(deco.get("color", "#111111")),
                                                outline=parse_color(deco["outline"]) if deco.get("outline") else None,
                                                width=int(deco.get("outline_width", 0)))
        c.alpha_composite(layer)
    elif t == "line":
        (x0, y0), (x1, y1) = deco["from"], deco["to"]
        ImageDraw.Draw(c).line((x0 * ctx.W, y0 * ctx.H, x1 * ctx.W, y1 * ctx.H),
                               fill=parse_color(deco.get("color", "#1d1d1f")), width=int(deco.get("width", 2)))
    elif t == "block":
        x, y, w, h = ctx.px(deco["box"])
        col = with_alpha(parse_color(deco.get("color", "#e8d9c4")), float(deco.get("opacity", 1)))
        layer = Image.new("RGBA", (max(1, int(w)), max(1, int(h))), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle((0, 0, layer.width - 1, layer.height - 1),
                                                radius=int(deco.get("radius", 0)), fill=col)
        _paste_rotated(ctx, layer, x + w / 2, y + h / 2, float(deco.get("rotate", 0)))
    elif t == "scrap":
        x, y, w, h = ctx.px(deco["box"])
        w_i, h_i = max(8, int(w)), max(8, int(h))
        amp = min(w_i, h_i) * 0.02
        mask = Image.new("L", (w_i, h_i), 0)
        ImageDraw.Draw(mask).polygon(_torn_polygon(w_i, h_i, ctx.rng, amp), fill=255)
        layer = Image.new("RGBA", (w_i, h_i), parse_color(deco.get("color", "#fbf8f1")))
        if deco.get("ruled"):
            ld = ImageDraw.Draw(layer)
            gap = max(10, int(h_i / 9))
            for yy in range(gap, h_i, gap):
                ld.line((0, yy, w_i, yy), fill=parse_color(deco.get("rule_color", "#9fb7d633")), width=2)
        layer.putalpha(mask)
        rot = float(deco.get("rotate", 0))
        rotated = layer.rotate(rot, expand=True, resample=Image.Resampling.BICUBIC) if rot else layer
        pos = (int(x + w / 2 - rotated.width / 2), int(y + h / 2 - rotated.height / 2))
        if deco.get("shadow", True):
            _shadow(c, rotated, pos, strength=0.22, blur=max(4, int(min(w_i, h_i) * 0.025)), offset=(0, 4))
        _paste(c, rotated, *pos)
    elif t == "label":
        x, y, w, h = ctx.px(deco["box"])
        rot = float(deco.get("rotate", 0))
        layer = Image.new("RGBA", (max(1, int(w)), max(1, int(h))), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        bg = parse_color(deco.get("color", "#fbf3df"))
        shape = deco.get("shape", "rect")
        lw, lh = layer.width - 1, layer.height - 1
        if shape == "pill":
            d.rounded_rectangle((0, 0, lw, lh), radius=lh // 2, fill=bg)
        elif shape == "tag":
            notch = lh * 0.45
            d.polygon([(notch, 0), (lw, 0), (lw, lh), (notch, lh), (0, lh / 2)], fill=bg)
            r = lh * 0.09
            d.ellipse((notch * 0.55 - r, lh / 2 - r, notch * 0.55 + r, lh / 2 + r), fill=(0, 0, 0, 0))
        else:
            d.rectangle((0, 0, lw, lh), fill=bg)
        _paste_rotated(ctx, layer, x + w / 2, y + h / 2, rot)
        pad_x = w * (0.18 if shape == "tag" else 0.08)
        draw_text(ctx, {"text": deco.get("text", ""), "box": [(x + pad_x) / ctx.W, y / ctx.H, (w - pad_x * 1.4) / ctx.W, h / ctx.H],
                        "font": deco.get("font", "note"), "size": deco.get("size", h / ctx.W * 0.5),
                        "weight": deco.get("weight", 400), "color": deco.get("text_color", "#2b2622"),
                        "align": "center", "valign": "middle", "rotate": rot, "tracking": deco.get("tracking", 0),
                        "uppercase": deco.get("uppercase", False)}, kind="label", on_photo=True)
    elif t == "film_strip":
        x, y, w, h = ctx.px(deco["box"])
        strip = Image.new("RGBA", (int(w), int(h)), parse_color(deco.get("color", "#141210")))
        d = ImageDraw.Draw(strip)
        hole_w, hole_h = int(w * 0.045), int(w * 0.03)
        bg = c.getpixel((min(c.width - 1, int(x + w / 2)), min(c.height - 1, max(0, int(y) + 1))))
        yy = hole_h
        while yy < h:
            for xx in (w * 0.035, w - w * 0.035 - hole_w):
                d.rounded_rectangle((xx, yy, xx + hole_w, yy + hole_h), radius=3, fill=bg)
            yy += hole_h * 2.4
        edge = RichFont("mono_bold", max(10, int(w * 0.024)))
        ex = Image.new("RGBA", (int(h), int(w * 0.07)), (0, 0, 0, 0))
        edge.draw(ImageDraw.Draw(ex), (10, ex.height * 0.75),
                  "   ".join([deco.get("edge_text", "FILM 400")] * 12), (255, 150, 60, 220))
        strip.alpha_composite(ex.rotate(90, expand=True), (int(w * 0.088), 0))
        bb = _paste_rotated(ctx, strip, x + w / 2, y + h / 2, float(deco.get("rotate", 0)))
        _register(ctx, "film", "film strip", bb)
    elif t == "tape":
        rect = ctx.photo_rects.get(int(deco.get("photo", 0)))
        if not rect:
            return
        cx, top, tw, _, rot = rect
        w_px = int(deco.get("length", 0.3) * tw)
        h_px = int(w_px * 0.28)
        tape = Image.new("RGBA", (w_px, h_px), with_alpha(parse_color(deco.get("color", "#efe6c8")), 0.82))
        td = ImageDraw.Draw(tape)
        for xx in range(0, w_px, max(3, w_px // 40)):  # ragged ends
            td.rectangle((xx, 0, xx + 1, ctx.rng.randint(0, 3)), fill=(0, 0, 0, 0))
        _paste_rotated(ctx, tape, cx, top, rot + deco.get("angle", ctx.rng.uniform(-6, 6)))
    elif t == "swatches":
        x, y, w, h = ctx.px(deco["box"])
        colors = deco.get("colors", "auto")
        if colors == "auto" or isinstance(colors, int):
            src = ctx.photos if colors == "auto" else [ctx.photos[int(colors)]]
            seen: list[str] = []
            for p in src:
                for e in p.get("_palette", []):
                    if e["hex"] not in seen:
                        seen.append(e["hex"])
            colors = seen[: int(deco.get("count", 5))]
        n = max(1, len(colors))
        gap = w * 0.03
        sw = min((w - gap * (n - 1)) / n, h)
        d = ImageDraw.Draw(c)
        lab = RichFont("mono", max(9, int(sw * 0.16)))
        for i, col in enumerate(colors):
            sx = x + i * (sw + gap)
            if deco.get("shape", "circle") == "circle":
                d.ellipse((sx, y, sx + sw, y + sw), fill=parse_color(col))
            else:
                d.rectangle((sx, y, sx + sw, y + sw), fill=parse_color(col))
            if deco.get("labels", True):
                lab.draw(d, (sx, y + sw + lab.size * 1.3), str(col).upper(), parse_color(deco.get("label_color", "#555555")))
    elif t == "sticker":
        x, y = deco["at"][0] * ctx.W, deco["at"][1] * ctx.H
        r = deco.get("size", 0.05) * ctx.W
        col = parse_color(deco.get("color", "#ffd34d"))
        size = int(r * 2.4) + 4
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        cx = cy = size / 2
        shape = deco.get("shape", "star")
        if shape == "star":
            d.polygon(_star(cx, cy, r), fill=col)
        elif shape == "sparkle":
            d.polygon(_star(cx, cy, r, 4, 0.22), fill=col)
        elif shape == "heart":
            d.polygon(_heart(cx, cy, r), fill=col)
        elif shape == "circle":
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=max(2, int(r * 0.08)))
        elif shape == "arrow":
            lw = max(3, int(r * 0.12))
            d.line((cx - r, cy + r * 0.3, cx + r * 0.8, cy - r * 0.2), fill=col, width=lw)
            d.polygon([(cx + r, cy - r * 0.25), (cx + r * 0.45, cy - r * 0.5), (cx + r * 0.62, cy + r * 0.08)], fill=col)
        _paste_rotated(ctx, layer, x, y, float(deco.get("rotate", 0)))
    elif t == "postmark":
        x, y = deco["at"][0] * ctx.W, deco["at"][1] * ctx.H
        r = deco.get("size", 0.09) * ctx.W
        col = with_alpha(parse_color(deco.get("color", "#8a2b2b")), float(deco.get("opacity", 0.8)))
        size = int(r * 2.6)
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        cx = cy = size / 2
        lw = max(2, int(r * 0.05))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=lw)
        d.ellipse((cx - r * 0.82, cy - r * 0.82, cx + r * 0.82, cy + r * 0.82), outline=col, width=max(1, lw // 2))
        lines = [s for s in deco.get("lines", []) if s]
        f = RichFont(_font_role(ctx, deco.get("font", "typewriter")), int(r * 0.26))
        for k, s in enumerate(lines[:3]):
            tw = f.measure(d, s)
            f.draw(d, (cx - tw / 2, cy + (k - (len(lines[:3]) - 1) / 2) * r * 0.34 + r * 0.09), s, col)
        for k in range(4):  # wavy cancellation lines
            yy = cy - r * 0.45 + k * r * 0.3
            pts = [(cx + r * 1.05 + i * 4, yy + math.sin(i / 3) * r * 0.06) for i in range(int(r * 0.25))]
            d.line(pts, fill=col, width=max(1, lw // 2))
        bb = _paste_rotated(ctx, layer, x, y, float(deco.get("rotate", -12)))
        _register(ctx, "postmark", "postmark", bb)
        if deco.get("size", 0.09) < 0.08:
            ctx.warnings.append("postmark is smaller than 0.08 of the width; it will be hard to read on a phone")
    else:
        ctx.warnings.append(f"unknown decoration type {t!r} skipped")


# ---------------------------------------------------------------------------
# Text blocks
# ---------------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"\{(camera|lens|settings|date|datetime|iso|aperture|shutter|focal_length|gps):(\d+)\}")
MIN_TEXT_FRACTION = 0.022  # below this (≈24 px at 1080) text is hard to read on a phone


def _fill_placeholders(ctx: Ctx, text: str) -> str:
    def sub(m: re.Match[str]) -> str:
        key, idx = m[1], int(m[2])
        if idx >= len(ctx.photos):
            ctx.warnings.append(f"text placeholder {m[0]} refers to a missing photo")
            return ""
        ex = ctx.photos[idx].get("_exif", {})
        if key == "date":
            return ex.get("datetime", "")[:10]
        if key == "gps":
            g = ex.get("gps")
            return f"{abs(g['lat']):.4f}°{'N' if g['lat'] >= 0 else 'S'} {abs(g['lon']):.4f}°{'E' if g['lon'] >= 0 else 'W'}" if g else ""
        val = ex.get(key, "")
        if not val:
            ctx.warnings.append(f"photo {idx} has no EXIF {key}; {m[0]} left empty")
        return val

    lines = [_PLACEHOLDER.sub(sub, ln) for ln in text.split("\n")]
    return "\n".join(ln for ln, orig in zip(lines, text.split("\n")) if ln.strip() or not _PLACEHOLDER.search(orig))


def _size_px(ctx: Ctx, value: Any, default: float = 0.045) -> float:
    v = float(value if value is not None else default)
    return v * ctx.W if v < 1 else v


def draw_text(ctx: Ctx, spec: dict[str, Any], kind: str = "text", on_photo: bool = False, photo: int | None = None) -> None:
    spec = _resolve_colors(ctx, spec)
    text = _fill_placeholders(ctx, str(spec.get("text", "")))
    if not text.strip():
        return
    if spec.get("uppercase"):
        text = text.upper()
    x, y, bw, bh = ctx.px(spec["box"])
    short = text.replace("\n", " ")[:24]
    if int(x // ctx.W) != int((x + bw - 1) // ctx.W) and ctx.slides > 1:
        ctx.warnings.append(f"text {short!r} crosses a carousel seam")
    role = _font_role(ctx, spec.get("font"))
    weight = int(spec.get("weight", 400))
    wanted = _size_px(ctx, spec.get("size"))
    size = wanted
    tracking_em = float(spec.get("tracking", 0))
    lh = float(spec.get("line_height", 1.25))
    pad = int(max(bw, bh) * 0.1) + 20
    layer = Image.new("RGBA", (int(bw) + pad * 2, int(bh) + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    while True:
        font = RichFont(role, int(size), weight)
        tracking = tracking_em * font.size
        lines = wrap_text(text, lambda s, f=font, t=tracking: f.measure(d, s, t), bw)
        total_h = font.size * lh * (len(lines) - 1) + font.size
        if total_h <= bh * 1.02 or font.size <= 10:
            break
        size *= 0.92
    if total_h > bh * 1.02:
        ctx.warnings.append(f"{kind} {short!r} does not fit its box")
    elif size < wanted * 0.999:
        ctx.warnings.append(f"{kind} {short!r} was shrunk to {int(size)}px to fit its box")
    if font.size < MIN_TEXT_FRACTION * ctx.W:
        ctx.warnings.append(f"{kind} {short!r} is only {font.size}px: too small to read on a phone "
                            f"(use size >= {MIN_TEXT_FRACTION + 0.003:.3f})")
    align = spec.get("align", "left")
    valign = spec.get("valign", "top")
    asc = font.size * 0.8
    oy = {"top": 0, "middle": (bh - total_h) / 2, "bottom": bh - total_h}.get(valign, 0)
    color = parse_color(spec.get("color", "#1d1d1f"))
    fx = spec.get("effects", {}) or {}
    positions = []
    for k, line in enumerate(lines):
        lw = font.measure(d, line, tracking)
        lx = {"left": 0, "center": (bw - lw) / 2, "right": bw - lw}.get(align, 0)
        positions.append((pad + lx, pad + oy + asc + k * font.size * lh, line))

    def render(fill: Any, stroke: int = 0, stroke_fill: Any = None, color_emoji: bool = True) -> Image.Image:
        lay = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        dd = ImageDraw.Draw(lay)
        for px_, py_, ln in positions:
            font.draw(dd, (px_, py_), ln, fill, tracking, stroke, stroke_fill, color_emoji)
        return lay

    if fx.get("background"):
        bg = fx["background"]
        cfg = _resolve_colors(ctx, bg if isinstance(bg, dict) else {"color": bg})
        p = cfg.get("padding", 0.35) * font.size
        bd = ImageDraw.Draw(layer)
        if cfg.get("per_line", True):
            for px_, py_, ln in positions:
                lw = font.measure(d, ln, tracking)
                bd.rounded_rectangle((px_ - p, py_ - asc - p * 0.6, px_ + lw + p, py_ + font.size * 0.25 + p * 0.6),
                                     radius=int(cfg.get("radius", 0)), fill=parse_color(cfg.get("color", "#ffffff")))
        else:
            left = min(px_ for px_, _, _ in positions)
            right = max(px_ + font.measure(d, ln, tracking) for px_, _, ln in positions)
            top = positions[0][1] - asc
            bottom = positions[-1][1] + font.size * 0.25
            bd.rounded_rectangle((left - p, top - p * 0.6, right + p, bottom + p * 0.6), radius=int(cfg.get("radius", 0)),
                                 fill=parse_color(cfg.get("color", "#ffffff")))
    if fx.get("marker"):
        mk = parse_color(_theme_color(ctx, fx["marker"]) if isinstance(fx["marker"], str) else "#ffd86b")
        md = ImageDraw.Draw(layer)
        for px_, py_, ln in positions:
            lw = font.measure(d, ln, tracking)
            md.rectangle((px_ - 4, py_ - font.size * 0.28, px_ + lw + 4, py_ + font.size * 0.12), fill=mk)
    if fx.get("shadow"):
        cfg = fx["shadow"] if isinstance(fx["shadow"], dict) else {}
        sh = render(with_alpha(parse_color(cfg.get("color", "#000000")), float(cfg.get("opacity", 0.45))), color_emoji=False)
        sh = sh.filter(ImageFilter.GaussianBlur(cfg.get("blur", font.size * 0.08)))
        off = cfg.get("offset", [0.03, 0.05])
        layer.alpha_composite(sh, (int(off[0] * font.size), int(off[1] * font.size)))
    if fx.get("glow"):
        cfg = fx["glow"] if isinstance(fx["glow"], dict) else {"color": fx["glow"] if isinstance(fx["glow"], str) else None}
        gl = render(parse_color(_theme_color(ctx, cfg.get("color")) or spec.get("color", "#ffffff")), color_emoji=False)
        gl = gl.filter(ImageFilter.GaussianBlur(cfg.get("blur", font.size * 0.18)))
        for _ in range(int(cfg.get("strength", 2))):
            layer.alpha_composite(gl)
    stroke = fx.get("stroke")
    if stroke:
        cfg = _resolve_colors(ctx, stroke if isinstance(stroke, dict) else {"color": stroke})
        layer.alpha_composite(render(color, int(cfg.get("width", max(2, font.size * 0.06))), parse_color(cfg.get("color", "#000000"))))
    else:
        layer.alpha_composite(render(color))
    if spec.get("opacity") is not None:
        a = layer.getchannel("A").point(lambda v: int(v * float(spec["opacity"])))
        layer.putalpha(a)
    bb = _paste_rotated(ctx, layer, x - pad + layer.width / 2, y - pad + layer.height / 2, float(spec.get("rotate", 0)))
    _register(ctx, kind, short, bb, on_photo=on_photo or bool(spec.get("on_photo")), photo=photo)


# ---------------------------------------------------------------------------
# Photo notes
# ---------------------------------------------------------------------------

NOTE_STYLES: dict[str, dict[str, Any]] = {
    "handwritten": {"font": "hand", "size": 0.04, "tilt": 2.5},
    "typewriter": {"font": "typewriter", "size": 0.028},
    "minimal": {"font": "sans", "weight": 600, "size": 0.025, "tracking": 0.14, "uppercase": True},
    "label": {"font": "typewriter", "size": 0.026,
              "effects": {"background": {"color": "#fbf3df", "padding": 0.5, "per_line": False}}},
    "stamp": {"font": "digital", "size": 0.032, "color": "#ff8a2a", "effects": {"glow": True}},
    "magazine": {"font": "serif_italic", "size": 0.03},
}


def draw_note(ctx: Ctx, idx: int) -> None:
    """Text attached to a photo, positioned from where the photo actually landed."""
    raw = ctx.photos[idx].get("note")
    if not raw or idx not in ctx.photo_boxes:
        return
    note = {"text": raw} if isinstance(raw, str) else dict(raw)
    style_name = note.get("style") or ctx.theme.get("note_style") or "minimal"
    style = NOTE_STYLES.get(style_name)
    if style is None:
        ctx.warnings.append(f"photo {idx}: unknown note style {style_name!r}; using 'minimal'")
        style = NOTE_STYLES["minimal"]
    spec = {**json.loads(json.dumps(style)), **{k: v for k, v in note.items() if k not in ("style", "position")}}
    if "font" not in note and style_name == "handwritten":
        spec["font"] = _font_role(ctx, "note") if ctx.theme.get("fonts", {}).get("note") else "hand"
    pos = note.get("position", "below")
    px0, py0, px1, py1 = ctx.photo_boxes[idx]
    tx0, ty0, tx1, ty1 = ctx.tile_boxes[idx]
    size = _size_px(ctx, spec.get("size"))
    n_lines = str(spec.get("text", "")).count("\n") + 1
    h = size * 1.3 * n_lines + size * 0.35
    on_photo = pos in ("top-left", "top-right", "bottom-left", "bottom-right")
    if on_photo:
        inset = 0.045 * min(px1 - px0, py1 - py0)
        w = (px1 - px0) * 0.75
        bx = px0 + inset if pos.endswith("left") else px1 - inset - w
        by = py0 + inset if pos.startswith("top") else py1 - inset - h
        spec.setdefault("align", "left" if pos.endswith("left") else "right")
    elif pos in ("left", "right"):
        w = 0.26 * ctx.W
        bx = tx0 - w - 0.02 * ctx.W if pos == "left" else tx1 + 0.02 * ctx.W
        by = (ty0 + ty1) / 2 - h / 2
        spec.setdefault("align", "right" if pos == "left" else "left")
    else:  # below / above
        w = max(tx1 - tx0, 0.3 * ctx.W)
        bx = tx0
        by = ty1 + 0.012 * ctx.H if pos == "below" else ty0 - h - 0.012 * ctx.H
        spec.setdefault("align", note.get("align", "left"))
    if spec.get("color", "auto") == "auto" or "color" not in spec:
        if on_photo:
            region = ctx.canvas.crop((int(bx), int(by), int(bx + w), int(by + h))).convert("L")
            bright = float(np.asarray(region, dtype=np.float32).mean() / 255) if region.width and region.height else 0.5
            has_bg = bool((spec.get("effects") or {}).get("background"))
            if has_bg or bright > 0.6:
                spec["color"] = "#1d1d1f"
            else:
                spec["color"] = "#ffffff"
                spec.setdefault("effects", {})
                spec["effects"] = {**spec["effects"], "shadow": {"opacity": 0.6}}
        else:
            spec["color"] = ctx.theme.get("colors", {}).get("text", "#2b2622")
    tilt = float(note.get("rotate", 0)) or (ctx.rng.uniform(-1, 1) * style.get("tilt", 0))
    if on_photo:
        tilt += ctx.photo_rects.get(idx, (0, 0, 0, 0, 0))[4]
    spec.update({"box": [bx / ctx.W, by / ctx.H, w / ctx.W, h / ctx.H], "rotate": tilt, "valign": "top"})
    spec.pop("tilt", None)
    draw_text(ctx, spec, kind="note", on_photo=on_photo, photo=idx)


# ---------------------------------------------------------------------------
# Overlap checks
# ---------------------------------------------------------------------------


def _overlap(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def check_overlaps(ctx: Ctx) -> None:
    def area(b: tuple[float, ...]) -> float:
        return max(1.0, (b[2] - b[0]) * (b[3] - b[1]))

    texts = [b for b in ctx.boxes if b["kind"] in ("text", "note", "label")]
    photos = [b for b in ctx.boxes if b["kind"] == "photo"]
    obstacles = [b for b in ctx.boxes if b["kind"] in ("postmark", "film")]
    for i, t in enumerate(texts):
        ta = area(t["box"])
        if not t.get("on_photo"):
            for p in photos:
                if p.get("photo") == t.get("photo") and t["kind"] == "note":
                    continue
                if _overlap(t["box"], p["box"]) / ta > 0.1:
                    ctx.warnings.append(f"{t['kind']} {t['label']!r} overlaps photo {p['photo']} "
                                        "(move it, or set on_photo with a shadow/background if intended)")
        for o in obstacles:
            if _overlap(t["box"], o["box"]) / ta > 0.1:
                ctx.warnings.append(f"{t['kind']} {t['label']!r} overlaps the {o['label']}")
        for u in texts[i + 1:]:
            if _overlap(t["box"], u["box"]) / min(ta, area(u["box"])) > 0.05:
                ctx.warnings.append(f"{t['kind']} {t['label']!r} overlaps {u['kind']} {u['label']!r}")


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------


def _gradient(W: int, H: int, cfg: dict[str, Any]) -> Image.Image:
    cols = np.array([parse_color(c) for c in cfg.get("colors", ["#ffffff", "#000000"])], dtype=np.float32)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    if cfg.get("type", "linear") == "radial":
        cx, cy = cfg.get("center", [0.5, 0.5])
        d = np.sqrt((xs - cx * W) ** 2 + (ys - cy * H) ** 2)
        t = d / (d.max() * float(cfg.get("radius", 1.0)) or 1)
    else:
        a = math.radians(float(cfg.get("angle", 90)))
        proj = xs * math.cos(a) + ys * math.sin(a)
        t = (proj - proj.min()) / ((proj.max() - proj.min()) or 1)
    t = np.clip(t, 0, 1)
    stops = np.linspace(0, 1, len(cols))
    out = np.stack([np.interp(t, stops, cols[:, ch]) for ch in range(4)], axis=-1)
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def _pattern(W: int, H: int, cfg: dict[str, Any], slide_w: int) -> Image.Image:
    kind = cfg.get("type", "grid")
    col = parse_color(cfg.get("color", "#0000001a"))
    sp = max(6, int(float(cfg.get("spacing", 0.04)) * slide_w))
    lw = max(1, int(cfg.get("width", 2 if kind == "stripes" else 1)))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if kind == "grid":
        for x in range(0, W, sp):
            d.line((x, 0, x, H), fill=col, width=lw)
        for y in range(0, H, sp):
            d.line((0, y, W, y), fill=col, width=lw)
    elif kind == "dots":
        r = max(1.5, float(cfg.get("dot_size", 0.0035)) * slide_w)
        for y in range(sp // 2, H, sp):
            for x in range(sp // 2, W, sp):
                d.ellipse((x - r, y - r, x + r, y + r), fill=col)
    elif kind == "lines":
        top = int(float(cfg.get("top", 0.06)) * H)
        for y in range(top, H, sp):
            d.line((0, y, W, y), fill=col, width=lw)
        if cfg.get("margin_color"):
            mc = parse_color(cfg["margin_color"])
            for k in range(max(1, W // slide_w)):
                mx = k * slide_w + int(0.09 * slide_w)
                d.line((mx, 0, mx, H), fill=mc, width=max(1, lw))
    elif kind == "checks":
        for yi, y in enumerate(range(0, H, sp)):
            for xi, x in enumerate(range(0, W, sp)):
                if (xi + yi) % 2 == 0:
                    d.rectangle((x, y, x + sp - 1, y + sp - 1), fill=col)
    elif kind == "stripes":
        diag = int(math.hypot(W, H)) + sp * 2
        big = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
        bd = ImageDraw.Draw(big)
        stripe = max(lw, int(sp * float(cfg.get("ratio", 0.5))))
        for x in range(0, diag, sp):
            bd.rectangle((x, 0, x + stripe - 1, diag), fill=col)
        big = big.rotate(float(cfg.get("angle", 45)), resample=Image.Resampling.BICUBIC)
        left, top = (diag - W) // 2, (diag - H) // 2
        layer = big.crop((left, top, left + W, top + H))
    else:
        raise ValueError(f"unknown background pattern {kind!r}; use grid, dots, lines, checks or stripes")
    return layer


def make_background(W: int, H: int, bg: Any, seed: int = 3, slide_w: int | None = None) -> Image.Image:
    """Layered background: flat colour → gradient → pattern → texture (paper / grain / kraft)."""
    cfg = bg if isinstance(bg, dict) else {"color": bg or "#ffffff"}
    slide_w = slide_w or W
    canvas = Image.new("RGBA", (W, H), parse_color(cfg.get("color", "#ffffff")))
    if cfg.get("gradient"):
        canvas.alpha_composite(_gradient(W, H, cfg["gradient"]))
    if cfg.get("pattern"):
        canvas.alpha_composite(_pattern(W, H, cfg["pattern"], slide_w))
    texture = cfg.get("texture", "none")
    if texture in ("paper", "grain", "kraft"):
        rng = np.random.default_rng(seed)
        amt = float(cfg.get("texture_strength", 1.0)) * {"paper": 6, "grain": 10, "kraft": 8}[texture]
        noise = rng.normal(0, amt, (H // 2, W // 2)).astype(np.float32)
        if texture in ("paper", "kraft"):
            fibres = rng.normal(0, amt * (0.8 if texture == "paper" else 1.4), (H // 8, W // 8)).astype(np.float32)
            noise += np.asarray(Image.fromarray(fibres).resize((W // 2, H // 2), Image.Resampling.BICUBIC))
        if texture == "kraft":
            specks = rng.random((H // 2, W // 2)) > 0.997
            noise[specks] -= amt * 5
        n = Image.fromarray(noise).resize((W, H), Image.Resampling.BILINEAR)
        arr = np.asarray(canvas, dtype=np.float32)
        arr[..., :3] += np.asarray(n, dtype=np.float32)[..., None]
        canvas = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    return canvas


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def _merge(a: Any, b: Any) -> Any:
    """Shallow merge for theme/page values: dicts merge, otherwise the page value wins."""
    if isinstance(a, dict) and isinstance(b, dict):
        return {**a, **b}
    if isinstance(a, str) and isinstance(b, dict):
        return {"color": a, **b}
    return a if b is None else b


def _render_page(spec: dict[str, Any], theme: dict[str, Any]) -> tuple[Image.Image, Ctx, list[Slot]]:
    """Render one canvas (a single post, a carousel strip or one page of a series)."""
    W, H = _canvas_size(spec)
    slides = max(1, int(spec.get("slides", 1)))
    photos = _norm_photos(spec)
    for i, p in enumerate(photos):
        p["_index"] = i
        p["_img"] = load_photo(p["path"])
        p["_exif"] = read_exif(p["path"])
        a = analyse(p["_img"])
        p["_focus"], p["_palette"] = a["focus"], a["palette"]
        p["_aspect_hint"] = p["_img"].height / p["_img"].width
    canvas = make_background(W * slides, H, spec.get("background", "#ffffff"), seed=int(spec.get("seed", 3)), slide_w=W)
    ctx = Ctx(W=W, H=H, slides=slides, canvas=canvas, spec=spec, photos=photos,
              rng=random.Random(int(spec.get("seed", 7))), theme=theme)
    slots = layout_slots(ctx)
    if len(slots) < len(ctx.photos):
        ctx.warnings.append(f"layout has {len(slots)} slots for {len(ctx.photos)} photos; extra photos were not used")
    for deco in spec.get("_underlays", []) + [d for d in spec.get("decorations", []) if d.get("layer") == "under"]:
        draw_decoration(ctx, deco)
    frame = spec.get("frame") or {}
    for i, slot in enumerate(slots[: len(ctx.photos)]):
        tile, rect = build_tile(ctx, i, slot)
        rot = slot.rotate + float((ctx.photos[i].get("frame") or {}).get("tilt", frame.get("tilt", 0)) or 0)
        if rot:
            tile = tile.rotate(rot, expand=True, resample=Image.Resampling.BICUBIC)
        sx, sy = slot.x * W + slot.w * W / 2 - tile.width / 2, slot.y * H + slot.h * H / 2 - tile.height / 2
        if frame.get("shadow") or (ctx.photos[i].get("frame") or {}).get("shadow"):
            _shadow(canvas, tile, (int(sx), int(sy)), blur=max(6, int(min(tile.size) * 0.03)),
                    offset=(0, max(4, int(min(tile.size) * 0.02))))
        _paste(canvas, tile, sx, sy)
        ox, oy = slot.x * W, slot.y * H
        ctx.photo_rects[i] = (ox + slot.w * W / 2, oy, slot.w * W, slot.h * H, rot)
        ctx.tile_boxes[i] = (ox, oy, ox + slot.w * W, oy + slot.h * H)
        ctx.photo_boxes[i] = (ox + rect[0], oy + rect[1], ox + rect[2], oy + rect[3])
        _register(ctx, "photo", f"photo {i}", ctx.tile_boxes[i], photo=i)
    for deco in [d for d in spec.get("decorations", []) if d.get("layer") != "under"]:
        draw_decoration(ctx, deco)
    for i in range(min(len(slots), len(ctx.photos))):
        draw_note(ctx, i)
    for t in spec.get("texts", []):
        draw_text(ctx, t)
    check_overlaps(ctx)
    return canvas, ctx, slots


def _save(img: Image.Image, path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    icc = ImageCms.ImageCmsProfile(SRGB).tobytes()
    if path.suffix == ".jpg":
        img.save(path, quality=int(spec.get("quality", 95)), subsampling=0, icc_profile=icc)
    else:
        img.save(path, icc_profile=icc)
    return {"path": str(path.resolve()), "width": img.width, "height": img.height, "size_bytes": path.stat().st_size}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [w for w in items if not (w in seen or seen.add(w))]


def _slot_info(slots: list[Slot], n: int) -> list[dict[str, Any]]:
    return [{"photo": i, "x": round(s.x, 3), "y": round(s.y, 3), "w": round(s.w, 3), "h": round(s.h, 3),
             "rotate": round(s.rotate, 1)} for i, s in enumerate(slots[:n])]


def render_post(spec: dict[str, Any], output_dir: str, name: str = "post") -> dict[str, Any]:
    """Render a post spec (single post, panorama carousel, or a themed series of pages)."""
    spec = json.loads(json.dumps(spec))  # private copy; templates may add defaults
    if not str(output_dir).strip():
        raise ValueError("output_dir is required")
    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "png" if str(spec.get("output_format", "jpg")).lower() == "png" else "jpg"
    theme = spec.get("theme", {}) or {}
    spec_path = out_dir / f"{name}.spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    if "pages" in spec:
        base = {k: v for k, v in spec.items() if k not in ("pages", "theme")}
        pages_out, files, all_warn, thumbs = [], [], [], []
        for k, page in enumerate(spec["pages"], 1):
            ps = {**base, **{kk: vv for kk, vv in page.items() if kk not in ("background", "frame")}}
            ps["background"] = _merge(_merge(theme.get("background"), base.get("background")), page.get("background")) \
                or "#ffffff"
            ps["frame"] = _merge(_merge(theme.get("frame"), base.get("frame")), page.get("frame"))
            ps["slides"] = 1
            ps["seed"] = int(base.get("seed", 7)) + k
            canvas, ctx, slots = _render_page(ps, theme)
            img = canvas.convert("RGB")
            info = _save(img, out_dir / f"{name}-{k:02d}.{ext}", ps)
            warns = _dedupe(ctx.warnings)
            files.append(info)
            all_warn += [f"page {k}: {w}" for w in warns]
            pages_out.append({"page": k, "file": info["path"], "slots": _slot_info(slots, len(ctx.photos)),
                              "warnings": warns})
            t = img.copy()
            t.thumbnail((480, 600))
            thumbs.append(t)
        gap = 16
        ov = Image.new("RGB", (sum(t.width for t in thumbs) + gap * (len(thumbs) + 1), max(t.height for t in thumbs) + gap * 2),
                       (120, 120, 120))
        x = gap
        for t in thumbs:
            ov.paste(t, (x, gap))
            x += t.width + gap
        ov_path = out_dir / f"{name}-overview.jpg"
        ov.save(ov_path, quality=85)
        files.append({"path": str(ov_path.resolve()), "overview": True, "size_bytes": ov_path.stat().st_size})
        return {"success": True, "files": files, "pages": pages_out, "overview": str(ov_path.resolve()),
                "spec_file": str(spec_path.resolve()), "warnings": all_warn}

    canvas, ctx, slots = _render_page(spec, theme)
    W, H, slides = ctx.W, ctx.H, ctx.slides
    final = canvas.convert("RGB")
    files = []
    for k in range(slides):
        suffix = f"-{k + 1:02d}" if slides > 1 else ""
        files.append(_save(final.crop((k * W, 0, (k + 1) * W, H)), out_dir / f"{name}{suffix}.{ext}", spec))
    if slides > 1:
        prev = final.copy()
        prev.thumbnail((min(2400, W * slides // 2), H))
        pp = out_dir / f"{name}-overview.jpg"
        prev.save(pp, quality=85)
        files.append({"path": str(pp.resolve()), "overview": True, "size_bytes": pp.stat().st_size})
    return {
        "success": True,
        "files": files,
        "spec_file": str(spec_path.resolve()),
        "canvas": {"width": W, "height": H, "slides": slides},
        "slots": _slot_info(slots, len(ctx.photos)),
        "warnings": _dedupe(ctx.warnings),
    }
