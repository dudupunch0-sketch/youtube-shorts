#!/usr/bin/env python3
"""Create a scene-level media manifest from an episode JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


def slugify(value: str) -> str:
    result = []
    for char in value.lower().strip():
        if char.isalnum() or char in "-_":
            result.append(char)
        elif char in " _":
            result.append("-")
    return "".join(result).strip("-") or "episode"


def load_episode(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"episode file not found: {path}")
    try:
        episode = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid episode JSON: {error}") from error
    if not isinstance(episode, dict) or not episode.get("segments"):
        raise SystemExit("episode must contain a non-empty segments list")
    return episode


def generation_prompt(segment: dict[str, Any]) -> str:
    query = segment.get("visual_query", "")
    return (
        "Use case: illustration-story\n"
        "Asset type: vertical 9:16 still image for a Korean YouTube Shorts slideshow\n"
        f"Primary request: visualize this scene idea: {query}\n"
        "Style/medium: original editorial illustration, cinematic but readable\n"
        "Composition/framing: one clear focal subject, centered or upper-third subject, "
        "negative space for captions, vertical framing\n"
        "Lighting/mood: curious, mysterious, high contrast, suitable for a short fact explainer\n"
        "Constraints: no text, no subtitles, no watermark, no logo, no UI, no collage, "
        "do not reproduce official key art or an exact copyrighted character design\n"
        "Avoid: illegible details, extra characters, visual clutter, borders"
    )


def build_manifest(episode_path: Path, episode: dict[str, Any]) -> dict[str, Any]:
    episode_id = slugify(episode_path.stem)
    segments = []
    for index, segment in enumerate(episode["segments"], start=1):
        query = str(segment.get("visual_query", "")).strip()
        segments.append(
            {
                "index": index,
                "duration_sec": float(segment.get("duration_sec", 0)),
                "narration": segment.get("narration", ""),
                "caption": segment.get("caption", ""),
                "visual_type": segment.get("visual_type", "illustration"),
                "claim_type": segment.get("claim_type", "unknown"),
                "search": {
                    "status": "pending",
                    "queries": [query, f"{query} public domain", f"{query} Creative Commons"],
                    "provider_order": [
                        "official_public_api",
                        "openly_licensed_media_index",
                        "official_source_page",
                        "insane-search-fallback",
                    ],
                    "last_run_at": None,
                    "errors": [],
                },
                "candidates": [],
                "asset": {
                    "status": "pending",
                    "mode": None,
                    "path": None,
                    "source_url": None,
                    "landing_url": None,
                    "license": None,
                    "license_url": None,
                    "creator": None,
                    "attribution": None,
                    "generator": None,
                    "prompt": generation_prompt(segment),
                    "review_notes": None,
                },
            }
        )
    return {
        "manifest_version": 1,
        "episode_id": episode_id,
        "episode_path": str(episode_path),
        "title": episode.get("title"),
        "strategy": "collect_then_manual_review",
        "search_fallback_skill": "insane-search",
        "generation_fallback": "manual_only",
        "asset_root": f"output/media/{episode_id}",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "segments": segments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    episode = load_episode(args.episode)
    manifest = build_manifest(args.episode, episode)
    output = args.output or Path("output/manifests") / f"{manifest['episode_id']}.media.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote media manifest plan: {output}")
    print(f"Segments: {len(manifest['segments'])}; status: pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
