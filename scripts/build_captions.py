#!/usr/bin/env python3
"""Build scene caption cues from an episode and measured TTS timing manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_value, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d}.{millis:03d}"


def load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"could not read JSON {path}: {error}") from error


def build(episode: dict[str, Any], timing: dict[str, Any]) -> dict[str, Any]:
    episode_segments = {item["index"]: item for item in episode.get("segments", [])}
    cues = []
    cursor = 0.0
    for item in timing.get("segments", []):
        index = int(item["index"])
        source = episode_segments.get(index, {})
        duration = float(item.get("timeline_duration_sec") or item.get("speech_duration_sec") or 0)
        if duration <= 0:
            raise SystemExit(f"segment {index} has no positive timeline duration")
        cues.append(
            {
                "index": index,
                "start_sec": round(cursor, 3),
                "end_sec": round(cursor + duration, 3),
                "text": source.get("caption") or source.get("narration") or "",
                "narration": source.get("narration") or item.get("narration") or "",
            }
        )
        cursor += duration
    return {
        "manifest_version": 1,
        "episode_path": episode.get("episode_path"),
        "timing_manifest": timing.get("episode_path"),
        "total_duration_sec": round(cursor, 3),
        "cues": cues,
    }


def render_vtt(captions: dict[str, Any]) -> str:
    lines = ["WEBVTT", ""]
    for cue in captions["cues"]:
        lines.extend(
            [
                str(cue["index"]),
                f"{timestamp(cue['start_sec'])} --> {timestamp(cue['end_sec'])}",
                cue["text"],
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("timing_manifest", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-vtt", type=Path)
    args = parser.parse_args()
    episode = load(args.episode)
    timing = load(args.timing_manifest)
    result = build(episode, timing)
    episode_id = args.episode.stem
    output_json = args.output_json or Path("output/manifests") / f"{episode_id}.captions.json"
    output_vtt = args.output_vtt or Path("output/captions") / f"{episode_id}.vtt"
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_vtt.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_vtt.write_text(render_vtt(result), encoding="utf-8")
    print(f"Wrote captions: {output_json} and {output_vtt}")
    print(f"Duration: {result['total_duration_sec']:.3f}s; cues: {len(result['cues'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
