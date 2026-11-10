---
name: vibe-post
description: "氛围拼图帖：把用户自己的照片按指定氛围排版成 Instagram / 小红书帖子、拼图、多页图组或轮播图（背景、边框、文字、照片注释、相机参数、日期戳、贴纸等）。必读规则：调用 post_render 前先用 skill_tool 读取本技能全文；⓪用户没说明形式/风格时，先用一条消息询问（单张拼图 / 多页图组 / 全景轮播 / 按组分开发帖；是否要封面/结尾页；氛围；是否加注释及注释风格；输出目录），再开始渲染；①先用 photo_inspect 检查照片再分组——用户指定优先，其次按内容、地点、时间，每组用一句话说明理由；做多张时先确认分组；②只用用户原图，只裁剪缩放，禁止 AI 生成/重绘，禁止调色滤镜；③不得编造 EXIF；日期地点未知时先问，用户同意虚构才可虚构并注明；④只写入用户指定目录；⑤先出预览，按反馈小步修改，渲染警告（重叠、字太小）先修再给用户看。Vibe Post rules: read this skill via skill_tool before calling post_render."
---

# Vibe Post Studio

Turn the user's own photos into finished posts: collage layouts, backgrounds,
frames, text, photo notes, camera stats and small decorations, matched to a
vibe they describe. All rendering is done by `post_render` (Pillow); you only
write the spec.

Reply in the user's language.

## 0. Hard rules

1. **The user's photos only.** Never generate, repaint, retouch, upscale-with-AI
   or colour-grade photos. `post_render` only crops and resizes them.
2. **Never invent facts.** Camera stats come only from EXIF placeholders
   (section 8). Dates and places come from EXIF/GPS or the user. If they are
   unknown, ask once; invent them only if the user agrees, and say clearly
   that they are made up.
3. **Write only where the user said.** Ask for an output folder if none was
   given (suggest a `posts/` subfolder next to the photos).
4. **Nothing is uploaded or posted.** The user posts the files themselves.
5. **Preview first, then small changes.** Never redesign from scratch in
   response to a small piece of feedback.

## 1. Workflow

1. **Ask first when there is no direction.** If the user has not said what
   format/style they want, send **one** message before rendering anything
   (skip what they already told you; never ask the same thing twice):
   - **Format** with a one-line recommendation from the photo count
     (e.g. "10 photos → I'd suggest (b), about 5 pages"):
     (a) one collage post · (b) a series of pages, each its own layout with a
     shared theme · (c) a swipeable panorama carousel (one wide canvas cut into
     slides) · (d) separate posts, one per group.
   - For (b)/(c): **cover page and/or closing page?** (optional, not default)
   - **Vibe**, if not given: 3–4 examples from section 5.
   - **Notes on photos**: none · date & place · short captions; and a note
     style (section 4).
   - **Platform**: Instagram 4:5 (default), square, story 9:16, 小红书 3:4.
   - **Output folder**, if not given.
   If the user says "just do it" / "surprise me", use your recommendation and
   say what you chose.
2. **Inspect**: call `photo_inspect` once with all paths and
   `contact_sheet_dir` = the output folder.
3. **Group** (section 2). Show one line per group with the reason.
4. **Plan**: per post/page, 1–2 lines: layout, photos, background, text.
5. **Render a preview** (`name` like `kyoto-preview-1`). For a series use one
   `post_render` call with `theme` + `pages`.
6. **Fix every warning before showing** (overlaps, tiny text, text not fitting,
   photo enlarged too much, text across a carousel seam): adjust and re-render.
7. **Show**: the file path(s) (for a series also `-overview.jpg`) and a
   one-line summary per page.
8. **Tweak loop**: apply feedback as small edits to the last spec
   (`<name>.spec.json` next to the images); render `-preview-2`, `-preview-3` …
9. **Finish**: render the final name, then write a caption and 5–10 hashtags in
   the vibe, in the user's language. List files in posting order.

## 2. Grouping photos

Priority, highest first:

1. **The user's direction** ("beach ones together", "one per day", "#3 is the
   cover"). Follow it exactly.
2. **Content** (mountains, sea, food, people, city, night …), only if you can
   see the photos: open `contact_sheet.jpg` (numbered `#0, #1 …`) with your
   file-reading tool. If no image content comes back, you cannot see images;
   don't guess content from file names.
3. **Location and time**: `photo_inspect` → `grouping.groups` splits by
   shooting-time gaps (> 3 h), GPS distance (> 3 km) and folder.
4. **Colour** (palette) only as a tiebreaker.

- Always state each group with its reason, one line each, e.g.
  `Page 2 — High country: #3 #8 · mountain lakes, cool blue palette`.
- `grouping.near_duplicates`: use the better photo of each pair, or ask.
- Several posts (format d) or a different grouping than the user expects →
  wait for a yes before rendering.
- No metadata and you can't see images: show folder-based groups and ask.
- Order within a group: by time by default; by colour flow for mood posts.

## 3. Layouts and series design

| Photos on one page | Good templates |
|---|---|
| 1 | `single`, `magazine`, `free` (one tilted polaroid) |
| 2–3 | `hero`, `hero-side`, `filmstrip`, `grid` 2 cols, `magazine` (≤ 3) |
| 4 | `grid` 2×2, `polaroids`, `hero` (1 + 3) |
| 5–9 | `grid`, `polaroids` (≤ 6) — or split into pages |

Many photos: a series of pages (b), a panorama carousel (c) or separate posts
(d), as the user chose. Never default to the panorama carousel.

**Series (format b):**
- Put the shared look in `theme` (background base, frame, fonts, colours, note
  style). Pages may override background layers within the theme's palette.
- **Vary every page**: a different layout template and text position from the
  previous page; vary background layers (pattern / gradient / texture /
  blocks).
- At most **2 recurring motifs** across the series (e.g. tape + postmark), not
  every decoration on every page.
- Cover / closing pages only if the user asked for them.
- Landscape photos in wide slots, portrait in tall ones (`orientation`,
  `aspect`); pass `focus` from `photo_inspect` so crops keep the subject.

## 4. Notes on photos

A note is text attached to one photo (`photos[i].note`), positioned
automatically. Styles — pick by vibe, handwriting is just one option:

| style | look | suits |
|---|---|---|
| `minimal` | small spaced sans caps | gallery, moody, minimal |
| `typewriter` | typewriter font | film, journal |
| `label` | typewriter on a cream label | journal, zine, scrapbook |
| `handwritten` | Caveat, slight tilt | journal, casual, summer |
| `stamp` | orange digital date look (digits work best) | film |
| `magazine` | serif italic | magazine, editorial |

Positions: on the photo `top-left` `top-right` `bottom-left` `bottom-right`
(colour `auto` picks light/dark text for contrast), or beside it `below`
`above` `left` `right`. Content: date · place, or a 2–5 word caption. No
notes unless the user chose them.

## 5. Vibe dictionary

Start from the closest recipe; for an unlisted vibe blend two and say which.

| Vibe | Background (base + layers) | Layout / frame | Type · notes | Extras |
|---|---|---|---|---|
| 90s film / 胶片 | `#efe8dc` + `paper`; stripes `#e7c9a633` | `filmstrip` or `grid` + `film` frame | `typewriter` · `stamp` | `date_stamp` |
| Clean gallery / 极简 | `#f6f5f2`, plain | `single` margin 0.1 + `keyline` | `sans` 600 caps · `minimal` | stats lines |
| Travel journal / 手账 | `#f1e9da` + `paper`; dots or grid pattern | `polaroids` / `free` + `polaroid`, shadow | `hand` title · `label` or `handwritten` | tape, `postmark`, `scrap`, `swatches` |
| Scrapbook / 剪贴簿 | `kraft` texture | `free` tilted polaroids + `matte` | `hand` + `typewriter` · `label` | `scrap` (ruled), `label` tags, tape |
| Magazine / 杂志 | `#fbfaf7`, plain | `magazine` | `serif` 700 + `sans` caps · `magazine` | issue line |
| Moody / 暗调 | `#121212`; radial gradient to `#232323` | `grid`, gap 0.012 | `sans` 800 caps white · `minimal` | none |
| Zine / 拼贴 | `#f4f1ea` + `grain`; checks or stripes | `free` rotate ±4–8, `matte` + shadow | `sans` 800 + `hand` · `label` | `block`s, `marker`, stickers |
| Minimal Japanese / 日系 | `#fafaf8`, plain | `single` / `hero-side`, margin 0.12 | `serif` 300–400 · `minimal` | thin `line` |
| Summer / 夏日 | linear gradient `#ffe8c7`→`#ffd1dc` | `grid` + `rounded` | `sans` 800 + `hand` · `handwritten` | `sparkle` stickers, `block`s |
| Notebook / 笔记本 | `#f7f4ec` + `lines` pattern with margin line | `single` / `hero` + `matte` | `hand` · `handwritten` | `postmark` |
| Camera nerd / 参数党 | `#f5f5f5` or `#111`; grid pattern | `grid` / `single` + `keyline` | `mono` · `minimal` | `{settings:N}` lines |

## 6. Design rules

- Minimum sizes: body text and notes `size` ≥ 0.025, titles ≥ 0.045,
  postmarks ≥ 0.08. The renderer warns below ≈ 0.022.
- Text must not overlap photos, other text, postmarks or film strips. Text on
  a photo only on purpose: set `"on_photo": true` and give it contrast
  (`shadow` or `background`). Fix every overlap warning.
- Keep text ≥ 0.05 from slide edges; carousel text boxes inside one slide.
- Per page: ≤ 2 font roles, ≤ 3 kinds of decoration, ≤ 2 effects per text.
- Chinese: `sans` / `serif` look best; other roles fall back to a system
  Chinese font. `digital` has digits and `' . - :` only. Avoid combined emoji
  (👩‍👩‍👧) and flags. Vertical Chinese text is not supported.

## 7. Tool results

- `photo_inspect` → `photos[]` (index, size, orientation, aspect, `exif`,
  `palette`, `brightness`, `tone`, `warmth`, `focus`), `grouping`
  (`groups`, `near_duplicates`, `note`), `contact_sheet`.
- `post_render` → `files[]`, `spec_file`, `warnings`; single posts also
  `slots`; series also `pages[]` (file, slots, warnings per page) and
  `overview`.

## 8. Spec reference

Coordinates are **fractions of one slide/page**: `x`/`w` of the width, `y`/`h`
of the height (panorama carousel: slide 2 starts at `x = 1`).

### Top level

```jsonc
{
  "format": "4:5",       // 1:1 | 4:5 | 3:4 (小红书) | 9:16 | 2:3 | {"w":1080,"h":1350}
  "width": 1080,
  "slides": 1,           // panorama carousel only (> 1)
  "background": {...},   // see below
  "photos": [...],
  "layout": {...},
  "frame": {...},
  "date_stamp": {...},
  "texts": [...],
  "decorations": [...],
  "output_format": "jpg" // or "png"
}
```

**Series:** replace the per-page keys with `theme` + `pages`:

```jsonc
{
  "format": "4:5",
  "theme": {
    "background": {"color": "#efe6d8", "texture": "paper"},
    "frame": {"style": "matte", "shadow": true},
    "fonts": {"title": "serif", "body": "sans", "note": "typewriter"},
    "colors": {"text": "#2b2622", "accent": "#b5562f"},
    "note_style": "label"
  },
  "pages": [
    {"background": {"pattern": {"type": "dots"}}, "layout": {...}, "photos": [...], "texts": [...]},
    {"background": {"gradient": {...}}, "layout": {...}, "photos": [...]}
  ]
}
```

Page `background` / `frame` merge over the theme's. In texts and decorations
`"font": "title" | "body" | "note"` and colour names from `theme.colors`
(e.g. `"color": "accent"`) resolve through the theme. Output:
`<name>-01.jpg …` + `<name>-overview.jpg`.

### background (layers drawn in this order)

```jsonc
{"color": "#f1e9da",
 "gradient": {"type": "linear", "colors": ["#ffe8c7", "#ffd1dc"], "angle": 135},
             // or {"type": "radial", "colors": [...], "center": [0.5, 0.3], "radius": 1}
 "pattern": {"type": "grid", "color": "#0000001a", "spacing": 0.04, "width": 1},
             // grid | dots (dot_size) | lines (top, margin_color) | checks | stripes (angle, ratio)
 "texture": "paper"}  // none | paper | grain | kraft (+ texture_strength)
```
A plain string means a flat colour. Use `#rrggbbaa` for see-through pattern
colours.

### photos[]

A path string, or `{"path", "focus": [x, y], "caption" (polaroid frame only),
"note": "text" | {"text", "style", "position", "size", "color", "rotate"},
"frame": {per-photo overrides incl. "tilt", "style"}}`.

### layout templates

| template | params (defaults) | notes |
|---|---|---|
| `single` | margin 0.06, bottom_space 0 | 1 photo |
| `grid` | cols auto, margin 0.06, gap 0.02, top_space, bottom_space | all photos |
| `hero` | hero 0.62, margin, gap, top_space, bottom_space | photo 0 on top, rest in a row |
| `hero-side` | same | photo 0 left, rest stacked right |
| `filmstrip` | frames 3, strip_width 0.7, frame_ratio 1.5, tilt, offset_x, offset_y | vertical film strip |
| `polaroids` | margin, top_space, bottom_space, size | scattered, auto tilt; polaroid frame |
| `magazine` | hero 0.64, margin, gap | photo 0 full-bleed top; ≤ 2 small photos bottom-right; title area x 0.06–0.44, y 0.66–0.95 |
| `carousel` | tilt | panorama; needs `slides` ≥ 2 |
| `free` | slots: `[{"x","y","w","h","rotate"}]` | full control |

### frame

`style`: `none` | `matte` | `keyline` | `polaroid` | `film` | `rounded`;
`width` (px, auto), `color`, `radius` (px), `shadow`, `tilt`, `caption_font`,
`caption_color`.

### date_stamp

`{"photos": "all" | [0, 2], "format": "film" | "dots" | "iso", "text", "color"}`
— EXIF date; skipped with a warning when missing unless `text` is given by
the user.

### texts[]

```jsonc
{"text": "QUIET PLACES", "box": [0.05, 0.035, 0.6, 0.06],
 "font": "title", "weight": 800, "size": 0.045, "tracking": 0.18,
 "align": "left", "valign": "top", "line_height": 1.25, "color": "text",
 "uppercase": false, "opacity": 1, "rotate": 0, "on_photo": false,
 "effects": {"shadow": true}}
```

- `font`: theme roles `title` `body` `note`, or `sans` (Inter 100–900) ·
  `serif` (Playfair 400–900) · `serif_italic` · `hand` · `typewriter` ·
  `mono` · `mono_bold` · `digital`.
- `size` < 1 = fraction of width (0.045 ≈ 49 px); ≥ 1 = px. Auto-shrinks to fit.
- `effects`: `shadow`, `glow`, `stroke`, `marker` (highlighter), `background`
  (label behind text: colour or `{color, padding, radius, per_line}`).
- EXIF placeholders (N = photo index): `{camera:N}` `{lens:N}` `{settings:N}`
  `{date:N}` `{datetime:N}` `{focal_length:N}` `{aperture:N}` `{shutter:N}`
  `{iso:N}` `{gps:N}`; a line whose placeholders are empty is dropped.

### decorations[]

`"layer": "under"` draws below the photos.

| type | fields |
|---|---|
| `block` | box, color, opacity, radius, rotate — colour block (usually `layer: under`) |
| `scrap` | box, color, rotate, ruled, shadow — torn paper piece |
| `label` | box, text, shape rect/pill/tag, color, text_color, font, size, rotate, uppercase |
| `rect` | box, color, radius, outline, outline_width |
| `line` | from [x,y], to [x,y], color, width |
| `tape` | photo (index), length 0.3, color, angle |
| `swatches` | box, colors (`"auto"`, photo index, or hex list), count, shape, labels |
| `sticker` | shape star/sparkle/heart/circle/arrow, at [x,y], size, color, rotate |
| `postmark` | at [x,y], size ≥ 0.08, lines (≤ 3), color, opacity, font, rotate |

## 9. Example: 3-page series

```json
{
  "format": "4:5",
  "theme": {
    "background": {"color": "#efe6d8", "texture": "paper"},
    "frame": {"style": "matte", "shadow": true},
    "fonts": {"title": "serif", "body": "sans", "note": "typewriter"},
    "colors": {"text": "#2b2622", "accent": "#b5562f"},
    "note_style": "label"
  },
  "pages": [
    {
      "background": {"pattern": {"type": "dots", "color": "#7a5c3a33", "spacing": 0.035}},
      "photos": [{"path": "C:/trip/IMG_2041.jpg", "note": {"text": "Oct 21 · Michigan", "position": "bottom-left"}},
                 "C:/trip/IMG_2044.jpg", "C:/trip/IMG_2045.jpg"],
      "layout": {"template": "hero-side", "hero": 0.6, "top_space": 0.13, "bottom_space": 0.1},
      "decorations": [{"type": "block", "box": [0.55, 0.1, 0.4, 0.5], "color": "#d9b48f", "rotate": 3, "layer": "under"}],
      "texts": [{"text": "Autumn Roads", "box": [0.06, 0.035, 0.7, 0.08], "font": "title", "weight": 700, "size": 0.07}]
    },
    {
      "background": {"gradient": {"type": "linear", "colors": ["#dfe8ee", "#b9cbd8"], "angle": 100}},
      "photos": [{"path": "C:/trip/IMG_2050.jpg", "note": {"text": "still water", "position": "top-left", "style": "minimal"}},
                 {"path": "C:/trip/IMG_2052.jpg", "note": {"text": "high country", "position": "top-right", "style": "minimal"}}],
      "layout": {"template": "grid", "cols": 2, "gap": 0.03, "top_space": 0.12, "bottom_space": 0.12},
      "texts": [{"text": "HIGH COUNTRY", "box": [0.06, 0.04, 0.88, 0.06], "font": "body", "weight": 800,
                 "size": 0.045, "tracking": 0.2, "color": "#24384a"}]
    },
    {
      "background": {"color": "#b8936a", "texture": "kraft"},
      "photos": [{"path": "C:/trip/IMG_2060.jpg", "caption": "cabin days", "frame": {"style": "polaroid", "tilt": -4}}],
      "layout": {"template": "free", "slots": [{"x": 0.14, "y": 0.1, "w": 0.6, "h": 0.62}]},
      "decorations": [{"type": "scrap", "box": [0.42, 0.68, 0.5, 0.22], "rotate": 3, "ruled": true},
                      {"type": "label", "box": [0.62, 0.06, 0.32, 0.07], "text": "DAY 04", "shape": "tag"}],
      "texts": [{"text": "A cabin, a warm drink,\nnowhere else to be.", "box": [0.47, 0.72, 0.42, 0.15],
                 "font": "hand", "size": 0.042, "rotate": 3, "on_photo": true}]
    }
  ]
}
```
