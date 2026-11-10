"""Grouping check with synthetic EXIF. usage: python dev/test_grouping.py <photo_dir> <work_dir>"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vibe-post-studio" / "tools"))
import vibepost_engine as eng  # noqa: E402

src, work = Path(sys.argv[1]), Path(sys.argv[2])
shutil.rmtree(work, ignore_errors=True)
(work / "trip").mkdir(parents=True)
(work / "misc").mkdir()
P = sorted(src.glob("*.jpg"))


def dms(v: float) -> tuple[float, float, float]:
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    return (float(d), float(m), round(((v - d) * 60 - m) * 60, 2))


def tag(srcp: Path, dst: Path, when: str, lat: float, lon: float) -> None:
    with Image.open(srcp) as im:
        ex = im.getexif()
        ex.get_ifd(0x8769)[0x9003] = when
        gps = ex.get_ifd(0x8825)
        gps.update({1: "N", 2: dms(lat), 3: "E", 4: dms(lon)})
        im.save(dst, exif=ex, quality=92)


ARASHI, GION, NARA = (35.0094, 135.6668), (35.0037, 135.7788), (34.6851, 135.8048)
plan = [  # (photo, time, place) -> expected 3 time/gps groups
    (0, "2024:10:17 09:10:00", ARASHI), (1, "2024:10:17 09:40:00", ARASHI), (2, "2024:10:17 10:05:00", ARASHI),
    (3, "2024:10:17 11:00:00", GION),  # same morning, ~10 km away -> new group
    (4, "2024:10:17 11:20:00", GION),
    (5, "2024:10:18 15:00:00", NARA), (6, "2024:10:18 15:30:00", NARA),
]
paths = []
for k, (i, when, (lat, lon)) in enumerate(plan):
    dst = work / "trip" / f"IMG_{2041 + k}.jpg"
    tag(P[i], dst, when, lat, lon)
    paths.append(str(dst))
for i in (7, 8, 9):
    dst = work / "misc" / P[i].name
    shutil.copy(P[i], dst)
    paths.append(str(dst))
dup = work / "misc" / "copy-of-resatka-10.jpg"
shutil.copy(P[9], dup)
paths.append(str(dup))

res = eng.inspect_photos(paths, contact_sheet_dir=str(work))
print(json.dumps(res["grouping"], ensure_ascii=False, indent=1))
print("contact sheet:", res.get("contact_sheet"))
g = [x["photos"] for x in res["grouping"]["groups"]]
assert g[:3] == [[0, 1, 2], [3, 4], [5, 6]], g
assert [9, 10] in res["grouping"]["near_duplicates"], res["grouping"]["near_duplicates"]
print("OK")
