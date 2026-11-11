"""photo_inspect: read-only facts about the user's photos for planning a post."""

from __future__ import annotations

from typing import Any

import vibepost_engine as engine
from openjiuwen.core.foundation.tool import Tool, ToolCard


def _args(inputs: Any) -> dict[str, Any]:
    if isinstance(inputs, dict):
        return inputs
    dump = getattr(inputs, "model_dump", None)
    return dump() if callable(dump) else {}


class PhotoInspectTool(Tool):
    """Inspect photos: size, orientation, EXIF camera stats, palette, brightness, focus point."""

    def __init__(self) -> None:
        super().__init__(
            ToolCard(
                id="photo_inspect",
                name="photo_inspect",
                description=(
                    "读取照片信息，用于规划 Instagram/小红书拼图帖（配合 vibe-post 技能使用）。"
                    "Read-only: returns each photo's size, orientation, EXIF camera stats (camera, lens, "
                    "focal length, aperture, shutter, ISO, date, GPS — only when present), a 5-colour palette, "
                    "brightness/warmth and a suggested crop focus point. Optionally writes a numbered "
                    "contact sheet to contact_sheet_dir. Never modifies the photos."
                ),
                input_params={
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Absolute paths of photos and/or folders (a folder expands to the jpg/png/webp/tif/bmp files directly inside it).",
                        },
                        "contact_sheet_dir": {
                            "type": "string",
                            "description": "Optional folder (chosen by the user) to write contact_sheet.jpg into.",
                        },
                    },
                    "required": ["paths"],
                },
            )
        )

    async def invoke(self, inputs: Any, **kwargs: Any) -> dict[str, Any]:
        """Run the inspection and return a JSON-serialisable result."""
        args = _args(inputs)
        paths = args.get("paths") or []
        if not isinstance(paths, list) or not paths:
            return {"success": False, "error": "paths must be a non-empty list of photo paths"}
        try:
            return engine.inspect_photos([str(p) for p in paths], args.get("contact_sheet_dir") or None)
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"{type(e).__name__}: {e}"}

    async def stream(self, inputs: Any, **kwargs: Any):
        """Single-shot stream wrapper."""
        yield await self.invoke(inputs, **kwargs)
