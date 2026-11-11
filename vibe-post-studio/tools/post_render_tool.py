"""post_render: draw a collage post from a JSON spec with Pillow (photos are never AI-edited)."""

from __future__ import annotations

import json
from typing import Any

import vibepost_engine as engine
from openjiuwen.core.foundation.tool import Tool, ToolCard


def _args(inputs: Any) -> dict[str, Any]:
    if isinstance(inputs, dict):
        return inputs
    dump = getattr(inputs, "model_dump", None)
    return dump() if callable(dump) else {}


class PostRenderTool(Tool):
    """Render a post (collage, frames, text, decorations) from a spec into output_dir."""

    def __init__(self) -> None:
        super().__init__(
            ToolCard(
                id="post_render",
                name="post_render",
                description=(
                    "按 spec 渲染拼图帖图片（配合 vibe-post 技能使用，先读技能中的 spec 说明）。"
                    "Draws a post from the user's own photos: layout template, frames, backgrounds, text, "
                    "photo notes, camera stats, date stamp and decorations. One call renders a single post, a "
                    "panorama carousel, or a themed series of pages (spec.theme + spec.pages). Photos are only "
                    "cropped/resized, never repainted or AI-edited; originals are untouched. Writes "
                    "<name>.jpg (or <name>-01.jpg… plus <name>-overview.jpg) and <name>.spec.json into "
                    "output_dir; returns file paths and layout warnings (overlaps, tiny text) to fix."
                ),
                input_params={
                    "type": "object",
                    "properties": {
                        "spec": {
                            "type": "object",
                            "description": "Post spec (format, photos, layout, frame, texts, decorations…) as described in the vibe-post skill.",
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Folder chosen by the user (or the current project) for the output files.",
                        },
                        "name": {
                            "type": "string",
                            "description": "Base file name without extension, e.g. 'kyoto-preview-1'.",
                        },
                    },
                    "required": ["spec", "output_dir"],
                },
            )
        )

    async def invoke(self, inputs: Any, **kwargs: Any) -> dict[str, Any]:
        """Render and verify the output files exist and are non-empty."""
        args = _args(inputs)
        spec = args.get("spec")
        if isinstance(spec, str):
            try:
                spec = json.loads(spec)
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"spec is not valid JSON: {e}"}
        if not isinstance(spec, dict):
            return {"success": False, "error": "spec must be an object"}
        output_dir = str(args.get("output_dir") or "").strip()
        if not output_dir:
            return {"success": False, "error": "output_dir is required (ask the user where to save)"}
        name = str(args.get("name") or "post").strip() or "post"
        try:
            result = engine.render_post(spec, output_dir, name)
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
        bad = [f["path"] for f in result["files"] if not f.get("size_bytes")]
        if bad:
            return {"success": False, "error": f"empty output files: {bad}"}
        return result

    async def stream(self, inputs: Any, **kwargs: Any):
        """Single-shot stream wrapper."""
        yield await self.invoke(inputs, **kwargs)
