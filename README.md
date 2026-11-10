# workswarm-photocollage-plugin

**Vibe Post Studio / 氛围拼图帖** — a WorkSwarm plugin that lays out your own
photos as Instagram / Xiaohongshu collage posts and carousels in a vibe you
describe: grouping by content, place and time, frames, text, notes, camera
stats and date stamps. Photos are only cropped and resized — no AI image
generation, no colour grading.

## Layout

```
vibe-post-studio/            the plugin package (install this folder)
├── manifest.json
├── README.md                plugin description
├── skills/vibe-post/SKILL.md
├── tools/
│   ├── photo_inspect_tool.py
│   ├── post_render_tool.py
│   └── vibepost_engine.py   shared Pillow engine
└── assets/fonts/            OFL / Apache-2.0 fonts with licences
dev/                         development scripts (not part of the package)
├── run_samples.py           render sample posts straight through the engine
└── test_grouping.py         grouping check with synthetic EXIF
```

## Install (local)

1. Copy `vibe-post-studio/` to
   `~/.jiuwenswarm/agent/workspace/plugins/plugin_packages/local/vibe-post-studio`.
2. Validate and register with WorkSwarm's bundled plugin-creator scripts:
   ```
   python <plugin-creator>/scripts/validate_plugin.py vibe-post-studio
   python <plugin-creator>/scripts/register_plugin.py vibe-post-studio
   ```
3. Start a new chat and tick the 氛围拼图帖 plugin chip.

## Development

```
python dev/run_samples.py <photo_dir> <out_dir>
python dev/test_grouping.py <photo_dir> <work_dir>
```

Use the Python environment that has `jiuwenswarm` installed (Pillow, numpy and
fontTools come with it). Test photos are not included in this repository.
