---
name: vibe-post
description: "氛围拼图帖：把用户自己的照片按指定氛围排版成 Instagram / 小红书帖子、拼图、轮播图（加边框、文字、相机参数、日期戳、贴纸等）。必读规则：调用 post_render 前先用 skill_tool 读取本技能全文；①先用 photo_inspect 检查照片，再分组——用户的指定优先，其次按内容、地点、时间分组；要做多张帖子时先把分组方案发给用户确认；②只用用户的原图，只裁剪缩放，禁止 AI 生成或重绘照片，禁止调色/滤镜；③不得编造 EXIF 相机参数；④输出目录必须是用户指定的目录，未指定先问；⑤先渲染预览，按反馈小步修改。Vibe Post rules: read this skill via skill_tool before calling post_render."
---

# Vibe Post Studio

Turn the user's own photos into a finished post: collage layout, frames, text,
camera stats and small decorations, matched to a vibe they describe. All
rendering is done by `post_render` (Pillow); you only write the spec.

Reply in the user's language.

## 0. Hard rules

1. **The user's photos only.** Never generate, repaint, retouch, upscale-with-AI
   or colour-grade photos. `post_render` only crops and resizes them; don't
   try to work around that.
2. **Never invent EXIF.** Camera stats come from `{camera:N}`-style
   placeholders (section 7). If a photo has no EXIF, say so and offer to drop
   the line or use text the user types.
3. **Write only where the user said.** Ask for an output folder if none was
   given (the folder the photos are in is a fine suggestion, in a
   `posts/` subfolder).
4. **Nothing is uploaded or posted.** The user posts the files themselves.
5. **Preview first, then small changes.** Never redesign from scratch in
   response to a small piece of feedback.

## 1. Workflow

1. **Collect** (ask only for what's missing, in one message): photo paths or
   folder, the vibe in their words, the platform/format, output folder.
   Defaults: Instagram portrait 4:5, 1080 px wide.
2. **Inspect**: call `photo_inspect` once with all paths and
   `contact_sheet_dir` = the output folder.
3. **Group** (section 2).
4. **Plan**: for each post, state in 3–5 lines: layout, photo order and hero,
   frame, the exact text, decorations. If the user only gave a vibe, carry on
   without waiting (except for multi-post grouping, which needs a yes).
5. **Render a preview**: `post_render` with `name` like `kyoto-1-preview-1`.
6. **Fix warnings before showing** (text doesn't fit, photo enlarged too much,
   text crosses a carousel seam): adjust the spec and re-render.
7. **Show**: give the output file path(s) and a one-line summary of the design.
8. **Tweak loop**: apply each piece of feedback as a small edit to the last
   spec (`<name>.spec.json` is saved next to the image), render
   `-preview-2`, `-preview-3` …
9. **Finish**: render the final name (e.g. `kyoto-1`), then write a caption and
   5–10 hashtags in the vibe, in the user's language. For a carousel, list the
   slide files in order.

## 2. Grouping photos

Priority, highest first:

1. **The user's direction**: "beach ones together", "one post per day",
   "#3 is the cover". Follow it exactly; don't regroup.
2. **Content**: what is in the photo (mountains, sea, food, people, city,
   night, interiors …). Only if you can actually see the photos: open
   `contact_sheet.jpg` (numbered `#0, #1 …`) with your file-reading tool. If no
   image content comes back, you cannot see images; don't guess content from
   file names.
3. **Location and time**: `photo_inspect` → `grouping.groups` already splits by
   shooting-time gaps (> 3 h), GPS distance (> 3 km) and folder. You may name a
   place from `gps_center` if you are confident; otherwise show coordinates.
4. **Colour** (palette) only as a tiebreaker.

Also:

- `grouping.near_duplicates` lists near-identical pairs: use only the better
  one (sharper / better framed), or ask.
- **Several groups → several posts**: send the grouping as a short list and
  wait for a yes, e.g.
  `Post 1 — Arashiyama morning: #0 #1 #2 · Post 2 — Gion: #3 #4 · Post 3 — Nara: #5 #6. OK?`
- **Several groups in one carousel**: one group per slide, or a cover slide
  then the groups.
- **No metadata and you can't see images**: show the folder-based groups and
  ask the user how to group. Never pretend to know what a photo shows.
- Inside a group: order by time by default; by colour flow for mood posts.
- Hero photo: the strongest image. With vision, judge it; without, prefer a
  photo the user mentioned, else the one with the highest resolution and a
  clear focus point.

## 3. Choosing a layout

| Photos in the post | Good templates |
|---|---|
| 1 | `single` (wide border + stats), `magazine` |
| 2–3 | `hero`, `hero-side`, `filmstrip`, `magazine` (≤ 3) |
| 4 | `grid` (2×2), `polaroids`, `hero` (1 + 3) |
| 5–9 | `grid`, `polaroids` (≤ 6), `carousel` |
| 6+ telling a story | `carousel`, 3–5 slides |

- Landscape photos go in wide slots, portrait photos in tall ones; check
  `orientation` and `aspect` from `photo_inspect`.
- Pass each photo's `focus` from `photo_inspect` (or the user's choice) so
  crops keep the subject.
- More than 9 photos: split into several posts or a carousel.

## 4. Vibe dictionary

Start from the closest recipe and adjust. For an unlisted vibe, blend two
recipes and say which.

| Vibe | Background | Layout / frame | Type | Extras |
|---|---|---|---|---|
| 90s film / 胶片 | `#efe8dc` + `paper` | `filmstrip` (tilt −3, offset_x 0.14) or `grid` + `film` frame | `typewriter` | `date_stamp` |
| Clean gallery / 极简 | `#f6f5f2` | `single` margin 0.1 + `keyline` `#d8d6d0` | `sans` 600 caps, tracking 0.12; `mono` stats; `serif_italic` place | stats lines |
| Travel journal / 手账 | `#f1e9da` + `paper` | `polaroids` (top_space 0.1) + `polaroid` frame, shadow | `hand` title + captions | tape ×2, `postmark`, `swatches` |
| Magazine / 杂志 | `#fbfaf7` | `magazine` | `serif` 700 title, `sans` 600 caps tracking 0.25 | issue line, "VOL." |
| Moody / 暗调 | `#121212` | `grid`, gap 0.012, top_space 0.1 | `sans` 800 caps white + light subtitle | none |
| Zine / 拼贴 | `#f4f1ea` + `grain` | `free` slots with rotate ±4–8, `matte` + shadow | mixed `sans` 800 + `hand` | `marker`, stickers, tape |
| Minimal Japanese / 日系 | `#fafaf8` | `single` or `hero-side`, big margin 0.12, `none` frame | `serif` 300–400, small, lots of space | thin `line` |
| Summer / 夏日 | `#fff4e0` | `grid` + `rounded` frame | `sans` 800 + `hand` | `sparkle` stickers |
| Camera nerd / 参数党 | `#f5f5f5` or `#111` | `grid` / `single` + `keyline` | `mono` | `{settings:N}` under each photo |
| Carousel / 轮播 | `#e9e4da` + `paper` | `carousel`, `slides` 3, `matte` + shadow, tilt 2 | `hand` "swipe →" | "fin." on last slide |

## 5. Design rules

- Keep important text at least 0.05 from the slide edges; on carousels keep
  every text box inside one slide.
- At most 2 font roles and 3 kinds of decoration per post; at most 2 effects
  per text.
- Text on top of a photo needs contrast: `shadow`, or a `background` label.
- Chinese: `sans` / `serif` look best; `hand` / `typewriter` / `mono` fall back
  to a system Chinese font for CJK characters.
- `digital` (date stamps) has digits and `' . - :` only.
- Emoji work in all font roles (Windows: colour emoji). Combined emoji (👩‍👩‍👧)
  and flags may not render; avoid them.
- Vertical Chinese text is not supported yet.

## 6. Spec reference

All coordinates are **fractions of one slide**: `x`/`w` of slide width,
`y`/`h` of slide height. In a carousel, slide 2 starts at `x = 1`.

```jsonc
{
  "format": "4:5",            // 1:1 | 4:5 | 3:4 (小红书) | 9:16 (story) | 2:3 | {"w":1080,"h":1350}
  "width": 1080,
  "slides": 1,                // >1 for carousels; files <name>-01.jpg …
  "background": {"color": "#efe8dc", "texture": "paper"},  // or "#ffffff"; texture none|paper|grain
  "photos": [
    "C:/photos/a.jpg",
    {"path": "C:/photos/b.jpg", "focus": [0.5, 0.4], "caption": "sea day",
     "frame": {"tilt": 3}}    // per-photo frame overrides
  ],
  "layout": {"template": "grid", "cols": 2, "margin": 0.06, "gap": 0.02,
             "top_space": 0.1, "bottom_space": 0},
  "frame": {"style": "matte", "shadow": true},
  "date_stamp": {"photos": "all", "format": "film"},   // or "text": "'24 10 17"
  "texts": [ … ],
  "decorations": [ … ],
  "output_format": "jpg"      // jpg (quality 95) | png
}
```

### layout templates

| template | params (defaults) | notes |
|---|---|---|
| `single` | margin 0.06, bottom_space 0 | 1 photo |
| `grid` | cols auto, margin 0.06, gap 0.02, top_space, bottom_space | all photos |
| `hero` | hero 0.62, margin, gap, top_space, bottom_space | photo 0 on top, rest in a row |
| `hero-side` | same | photo 0 left, rest stacked right |
| `filmstrip` | frames 3, strip_width 0.7, frame_ratio 1.5, tilt, offset_x, offset_y | vertical film strip |
| `polaroids` | margin, top_space, bottom_space, size | scattered, auto tilt; sets polaroid frame |
| `magazine` | hero 0.64, margin, gap | photo 0 full-bleed top; ≤ 2 small photos bottom-right; leave the bottom-left (x 0.06–0.44, y 0.66–0.95) for the title |
| `carousel` | tilt | needs `slides` ≥ 2; photos flow across the swipes |
| `free` | slots: `[{"x","y","w","h","rotate"}]` | full control; one slot per photo |

### frame

`style`: `none` | `matte` | `keyline` | `polaroid` | `film` | `rounded`.
Options: `width` (px; auto if omitted), `color`, `radius` (px), `shadow`
(bool), `tilt` (degrees), `caption_font`, `caption_color` (polaroid captions
come from `photos[i].caption`).

### date_stamp

`{"photos": "all" | [0, 2], "format": "film" | "dots" | "iso", "text": "...", "color": "#ff8a2a"}`.
Uses the EXIF date; without one it is skipped with a warning unless `text` is
given (only when the user supplies the date).

### texts[]

```jsonc
{"text": "QUIET PLACES", "box": [0.05, 0.035, 0.6, 0.06],
 "font": "sans", "weight": 800, "size": 0.045, "tracking": 0.18,
 "align": "left", "valign": "top", "line_height": 1.25, "color": "#f2f2f2",
 "uppercase": false, "opacity": 1, "rotate": 0,
 "effects": {"shadow": true}}
```

- `font`: `sans` (Inter, weights 100–900) · `serif` (Playfair, 400–900) ·
  `serif_italic` · `hand` (Caveat) · `typewriter` · `mono` · `mono_bold` ·
  `digital`.
- `size`: < 1 means fraction of slide width (0.045 ≈ 49 px); ≥ 1 means px.
  Text is shrunk automatically to fit its box (with a warning).
- `tracking`: letter spacing in em (0.1–0.3 for spaced caps).
- `\n` forces a line break; long text wraps inside `box`.
- `effects`: `shadow` (true or `{color, opacity, blur, offset}`), `glow`
  (true / colour / `{color, blur, strength}`), `stroke` (colour or
  `{color, width}`), `marker` (true or colour: highlighter behind text),
  `background` (colour or `{color, padding, radius, per_line}`: label).
- **EXIF placeholders** (N = photo index in `photos`): `{camera:N}`
  `{lens:N}` `{settings:N}` (e.g. `23mm  f/2  1/250s  ISO 400`) `{date:N}`
  `{datetime:N}` `{focal_length:N}` `{aperture:N}` `{shutter:N}` `{iso:N}`
  `{gps:N}`. A line whose placeholders are all empty is dropped.

### decorations[]

Add `"layer": "under"` to draw below the photos.

| type | fields |
|---|---|
| `rect` | box, color, radius, outline, outline_width (bars, panels) |
| `line` | from [x,y], to [x,y], color, width |
| `tape` | photo (index), length 0.3, color, angle |
| `swatches` | box, colors (`"auto"`, a photo index, or a hex list), count 5, shape circle/square, labels |
| `sticker` | shape star/sparkle/heart/circle/arrow, at [x,y], size 0.05, color, rotate |
| `postmark` | at [x,y], size 0.09, lines (≤ 3 short strings), color, opacity, font, rotate |

## 7. Tool results

- `photo_inspect` → `photos[]` (index, size, orientation, aspect, `exif`,
  `palette`, `brightness`, `tone`, `warmth`, `focus`), `grouping`
  (`groups`, `near_duplicates`, `note`), `contact_sheet`.
- `post_render` → `files[]` (paths; carousels also get `-overview.jpg`),
  `spec_file`, `slots` (where each photo landed), `warnings`. Treat every
  warning as something to fix or to tell the user.

## 8. Example (travel journal, 4 photos)

```json
{
  "format": "4:5",
  "background": {"color": "#f1e9da", "texture": "paper"},
  "photos": [
    {"path": "C:/trip/IMG_2041.jpg", "caption": "the castle"},
    {"path": "C:/trip/IMG_2047.jpg", "caption": "our cabin"},
    {"path": "C:/trip/IMG_2050.jpg", "caption": "sea day"},
    {"path": "C:/trip/IMG_2053.jpg", "caption": "foggy morning"}
  ],
  "layout": {"template": "polaroids", "margin": 0.05, "top_space": 0.1, "bottom_space": 0.06},
  "frame": {"style": "polaroid", "shadow": true},
  "decorations": [
    {"type": "tape", "photo": 0}, {"type": "tape", "photo": 3},
    {"type": "postmark", "at": [0.86, 0.075], "lines": ["BAVARIA", "OCT 2024"], "size": 0.065},
    {"type": "swatches", "colors": "auto", "box": [0.06, 0.935, 0.3, 0.035], "labels": false}
  ],
  "texts": [
    {"text": "Two weeks, no plans ✈️", "box": [0.06, 0.03, 0.66, 0.07],
     "font": "hand", "size": 0.065, "color": "#3b2f2a"}
  ]
}
```
