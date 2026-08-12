#!/usr/bin/env python3
"""Render a still-image layout preview for one episode segment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageOps


CANVAS = (1080, 1920)
CAPTION_BAND_HEIGHT = 320
BACKGROUND = (10, 10, 18)
DIVIDER_WIDTH = 8
LAYOUT_ALIASES = {"split_2up": "split_2up_left_right"}


def load_asset(repo_root: Path, selected: dict) -> Image.Image:
    path = selected.get("path")
    if not path:
        raise SystemExit("selected asset has no local path; run download_media_selection.py first")
    asset_path = (repo_root / path).resolve()
    if not asset_path.is_file():
        raise SystemExit(f"selected asset is missing: {asset_path}")
    return Image.open(asset_path).convert("RGB")


def render(manifest: dict, segment: dict, repo_root: Path) -> Image.Image:
    visual = segment.get("visual") or {}
    layout = LAYOUT_ALIASES.get(visual.get("layout", "full_frame"), visual.get("layout", "full_frame"))
    selected = visual.get("assets", [])
    if layout in {"split_2up_left_right", "split_2up_top_bottom"} and len(selected) != 2:
        raise SystemExit(f"{layout} preview requires exactly two selected assets")
    if layout == "full_frame" and len(selected) != 1:
        raise SystemExit("full_frame preview requires exactly one selected asset")
    if layout == "sequence" and not 2 <= len(selected) <= 4:
        raise SystemExit("sequence preview requires 2-4 selected assets")

    canvas = Image.new("RGB", CANVAS, BACKGROUND)
    content_height = CANVAS[1] - CAPTION_BAND_HEIGHT
    if layout in {"split_2up_left_right", "split_2up_top_bottom"}:
        panel_width = (CANVAS[0] - DIVIDER_WIDTH) // 2
        fit_mode = visual.get("fit", "contain")
        if layout == "split_2up_top_bottom":
            panel_size = (CANVAS[0], (content_height - DIVIDER_WIDTH) // 2)
        else:
            panel_size = (panel_width, content_height)
        for index, item in enumerate(selected):
            source = load_asset(repo_root, item)
            if fit_mode == "contain":
                panel = ImageOps.contain(source, panel_size, method=Image.Resampling.LANCZOS)
                panel_canvas = Image.new("RGB", panel_size, (245, 245, 248))
                panel_canvas.paste(panel, ((panel_size[0] - panel.width) // 2, (panel_size[1] - panel.height) // 2))
                panel = panel_canvas
            else:
                panel = ImageOps.fit(source, panel_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            if layout == "split_2up_top_bottom":
                canvas.paste(panel, (0, 0 if index == 0 else panel_size[1] + DIVIDER_WIDTH))
            else:
                x = 0 if index == 0 else panel_width + DIVIDER_WIDTH
                canvas.paste(panel, (x, 0))
        if layout == "split_2up_top_bottom":
            canvas.paste(Image.new("RGB", (CANVAS[0], DIVIDER_WIDTH), (230, 230, 235)), (0, panel_size[1]))
        else:
            canvas.paste(Image.new("RGB", (DIVIDER_WIDTH, content_height), (230, 230, 235)), (panel_width, 0))
    elif layout == "sequence":
        panel_width = (CANVAS[0] - DIVIDER_WIDTH * (len(selected) - 1)) // len(selected)
        for index, item in enumerate(selected):
            source = load_asset(repo_root, item)
            panel = ImageOps.fit(source, (panel_width, content_height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            x = index * (panel_width + DIVIDER_WIDTH)
            canvas.paste(panel, (x, 0))
            if index < len(selected) - 1:
                canvas.paste(Image.new("RGB", (DIVIDER_WIDTH, content_height), (230, 230, 235)), (x + panel_width, 0))
    else:
        panel = ImageOps.fit(load_asset(repo_root, selected[0]), (CANVAS[0], content_height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        canvas.paste(panel, (0, 0))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("segment", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    repo_root = manifest_path.parent.parent.parent
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    segment = next((item for item in data["segments"] if item["index"] == args.segment), None)
    if segment is None:
        raise SystemExit(f"segment not found: {args.segment}")
    output = args.output or repo_root / "output" / "playwright" / "media-preview" / f"segment-{args.segment:03d}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    render(data, segment, repo_root).save(output)
    print(f"Wrote media preview: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
