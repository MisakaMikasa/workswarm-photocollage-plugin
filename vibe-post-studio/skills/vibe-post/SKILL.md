---
name: vibe-post
description: "氛围拼图帖：把用户自己的照片按指定氛围排版成 Instagram / 小红书帖子、拼图、多页图组或轮播图（背景、边框、文字、照片注释、相机参数、日期戳、贴纸等）。必读规则：调用 post_render 前先用 skill_tool 读取本技能全文；⓪用户没说明形式/风格时，渲染前分两轮用 ask_user 提问（每轮最多 4 题、每题最多 4 个选项，推荐项放第一个并标“推荐”）：第一轮问结构——形式（多页图组 / 多页+封面 / 单张拼图 / 全景轮播）、摆放（随意叠放 / 随意不重叠 / 整齐网格 / 杂志主次）、文字（不要文字 / 只要标题 / 标题+短注释 / 我来提供）、画幅；第二轮问外观——字体（有文字才问）、背景、色调、装饰多少；用户已说明或话中已隐含的（如“杂志风、干净整齐”→不重叠、杂志主次）不再问，并用一句话说明默认选择；整轮都已确定就跳过；每次 ask_user（包括确认分组等是/否问题）都必须用 questions 并给 2–4 个可点选项，不要只传 query，否则空提交会反复重问；缺输出目录时一并询问；预览图必须用发送文件工具直接发到对话里，不要只给本地链接；①先用 photo_inspect 检查照片再分组——用户指定优先，其次按内容、地点、时间，每组用一句话说明理由；做多张时先确认分组；②只用用户原图，只裁剪缩放，禁止 AI 生成/重绘，禁止调色滤镜；③不得编造 EXIF；日期地点未知时先问，用户同意虚构才可虚构并注明；④只写入用户指定目录；⑤先出预览，按反馈小步修改，渲染警告（重叠、字太小）先修再给用户看。Vibe Post rules: read this skill via skill_tool before calling post_render."
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

1. **Ask about style first when there is no direction: two rounds.**
   `ask_user` allows **at most 4 questions per call and 2–4 options per
   question**, so ask in two calls, the second after the first is answered.
   Put the **recommended option first** and mark it "(推荐 / recommended)";
   don't spend an option slot on "you decide" (the user can always type their
   own answer). Never ask the same thing twice.

   **Every `ask_user` call must use `questions` with 2–4 options, including
   yes/no confirmations.** A plain `query` with no options gives the user
   nothing to click; an empty submit makes WorkSwarm re-ask the same question
   until they type. Put long details (the grouping list, the plan) in
   `query` and keep the question itself short, e.g. "按此分组继续？" with
   options "继续（推荐）" · "调整分组" · "合并成更少页".

   **Short-circuit: don't ask what is already decided.** Before each round,
   drop every question that is
   - answered outright ("4:5", "no text", "handwriting"), or
   - **implied** by what the user said: "magazine / clean / editorial" →
     editorial arrangement, no overlap, serif or sans, plain background;
     "scrapbook / messy / journal" → loose & layered, handwriting, paper
     texture; "minimal" → tidy, no decorations, sans; "film" → film strip,
     typewriter; or
   - irrelevant after earlier answers (no font question after "no text").
   Name the implied choices in one line in the lead text so the user can
   correct them ("I'll keep it clean: editorial layout, no overlap, serif").
   If nothing is left to ask in a round, skip that round.

   **Round 1: structure**

   | Question | Options (max 4) |
   |---|---|
   | Format | series of pages · series + cover page · one collage post · panorama carousel — recommend from the photo count ("10 photos → series, ~4 pages") |
   | Arrangement (includes overlap) | loose & layered (photos overlap) · loose, no overlap · tidy grid · editorial (one big + small) — film strip if the user types it |
   | Text | none · title only · title + short notes · I'll give you the text |
   | Platform | Instagram 4:5 · square 1:1 · story 9:16 · 小红书 3:4 |

   **Round 2: look**

   | Question | Options (max 4) |
   |---|---|
   | Font style (only if there is text) | handwritten casual · cursive script · elegant serif · clean sans (typewriter / marker if the user types them) |
   | Background | paper texture · pattern (grid / dots / checks / stripes) · soft gradient · plain colour |
   | Colour mood | warm · cool · pastel · neutral / dark |
   | Decorations | a few (tape, stamp) · none · lots (stickers, labels, scraps) |

   If the output folder is missing, ask for it in round 1's lead text.
   Separate posts per group, a closing page, or other choices come in as
   typed answers. If the user says "just do it" / "surprise me" / "go
   ahead" instead of answering, use the recommended options and say which
   you used. Map the answers with section 1a.
2. **Inspect**: call `photo_inspect` once with the photo paths or simply the
   folder (it expands to the images inside) and `contact_sheet_dir` = the
   output folder. Use the returned `path`s in the spec.
3. **Group** (section 2). Show one line per group with the reason. To
   confirm, use `ask_user` with options (continue / adjust), never a bare
   free-text question.
4. **Plan**: per post/page, 1–2 lines: layout, photos, background, text.
5. **Render a preview** (`name` like `kyoto-preview-1`). For a series use one
   `post_render` call with `theme` + `pages`.
6. **Fix every warning before showing** (overlaps, tiny text, text not fitting,
   photo enlarged too much, text across a carousel seam): adjust and re-render.
7. **Show in the chat**: send the images themselves with the file-sending
   tool (`send_file_to_user`): every page plus `-overview.jpg` for a series.
   Local file links don't open for the user, so never rely on a link alone.
   Add a one-line summary per page.
8. **Tweak loop**: apply feedback as small edits to the last spec
   (`<name>.spec.json` next to the images); render `-preview-2`, `-preview-3` …
9. **Finish**: render the final name, then write a caption and 5–10 hashtags in
   the vibe, in the user's language. List files in posting order.

## 1a. Turning the answers into a spec

| Answer | Spec |
|---|---|
| tidy grid | `grid` (or `hero` for 1 big + rest), `matte`/`keyline`/`none` frame, no tilt |
| editorial | `hero`, `hero-side`, `magazine` |
| loose & tilted | `scatter` (tilt 5–9) or `polaroids`; `polaroid`/`matte` frame + shadow |
| film strip | `filmstrip`, or `grid` + `film` frame |
| loose & layered / loose, no overlap | `scatter` `overlap` 0.15–0.35 (`variety` 0.3; higher for "messy"/"pile") / `overlap` 0; tidy and editorial layouts never overlap |
| decorations none / a few / lots | no decorations / 1–2 kinds (tape, postmark) / up to 3 kinds per page (stickers, labels, scraps, tape) |
| handwritten casual | font `hand` (Caveat) or `scrawl` (Reenie Beanie, messier) |
| cursive script | font `script` (Dancing Script) |
| marker | font `marker` (Permanent Marker), short words only |
| typewriter / clean sans / elegant serif | `typewriter` / `sans` / `serif` or `serif_italic` |
| background & mood | section 5 recipes; pattern colours with low alpha (`#rrggbb22`) |
| no text | no `texts`, no `note`s, no postmark text |

Mix: within a series keep the answers as the theme, but vary layout details
page to page (e.g. scatter with different photo counts, one hero page).

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
| 2–3 | `hero`, `hero-side`, `filmstrip`, `grid` 2 cols, `magazine` (≤ 3), `scatter` |
| 4 | `grid` 2×2, `scatter`, `polaroids`, `hero` (1 + 3) |
| 5–9 | `grid`, `scatter` (overlap ≥ 0.15), `polaroids` (≤ 6) — or split into pages |

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
| `handwritten` | Caveat, slight tilt (set `"font": "script"` or `"scrawl"` for cursive / messier) | journal, casual, summer |
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
| `scatter` | overlap 0.12 (0–0.45), tilt 6 (max °), variety 0.25 (size mix; photo 0 biggest), margin, top_space, bottom_space | loose, tilted, optionally overlapping pile; keeps each photo's shape; later photos lie on top |
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
  `serif` (Playfair 400–900) · `serif_italic` · `hand` (Caveat, casual) ·
  `script` (Dancing Script, cursive 400–700) · `marker` (Permanent Marker) ·
  `scrawl` (Reenie Beanie, messy pen) · `typewriter` · `mono` · `mono_bold` ·
  `digital`. Handwriting fonts read best at size ≥ 0.035.
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
