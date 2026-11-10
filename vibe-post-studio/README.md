# Vibe Post Studio / 氛围拼图帖

A WorkSwarm plugin that lays out **your own photos** as Instagram or
Xiaohongshu posts — collages, carousels, frames, captions, camera stats and
date stamps — in a vibe you describe ("90s film", "travel journal",
"magazine", "moody" …).

把你自己的照片按你描述的氛围排成 Instagram / 小红书拼图帖或轮播图。

## What it does

- **Groups photos** by your instructions first, then by content (if the chat
  model can see images), shooting place and time, and folder. Near-duplicates
  are flagged. Several groups become several posts after you confirm.
- **Lays them out**: single, grid, hero, film strip, scattered polaroids,
  magazine page, multi-slide carousel, or free placement.
- **Adds the finishing touches**: matte / keyline / polaroid / film / rounded
  frames, text in bundled fonts (with Chinese and emoji fallback), EXIF
  camera-stats lines, film-style date stamps, tape, postmarks, colour swatches,
  stickers.
- **Previews first**, then changes one thing at a time from your feedback;
  ends with a caption and hashtags.

## What it never does

- No AI image generation or retouching, no colour grades or filters. Photos
  are only colour-managed to sRGB, cropped and resized; originals are never
  modified.
- No made-up camera stats: missing EXIF is reported, not invented.
- Nothing is uploaded; files are written only to the folder you choose.

## Components

| Component | Purpose |
|---|---|
| `skills/vibe-post` | Workflow, grouping rules, layout guide, vibe dictionary, spec reference |
| `tools/photo_inspect_tool.py` | Photo facts, suggested groups, contact sheet |
| `tools/post_render_tool.py` | Renders a spec to JPG/PNG |
| `tools/vibepost_engine.py` | Shared Pillow engine |
| `assets/fonts` | Inter, Playfair Display, Caveat, Special Elite, Space Mono, DSEG7 (OFL / Apache 2.0; licences included) |

## Usage

Enable the plugin chip in a new chat, then e.g.:

- 把这个文件夹里的照片做成胶片风的 Instagram 拼图帖
- Group my trip photos by place and make a travel-journal collage for each group
- 用这些照片做一个 3 页的轮播图，加上相机参数

Requirements: none beyond WorkSwarm (uses its bundled Pillow, numpy and
fontTools). Chinese text uses a system Chinese font; colour emoji need
Windows' Segoe UI Emoji.
