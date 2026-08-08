#!/usr/bin/env python3
"""Validate the JSON contract used by the Shorts production pipeline."""

import json
import sys
from pathlib import Path


REQUIRED_ROOT_FIELDS = {
    "title",
    "topic",
    "language",
    "target_duration_sec",
    "estimated_duration_sec",
    "segments",
}
REQUIRED_SEGMENT_FIELDS = {
    "index",
    "narration",
    "visual_query",
    "visual_type",
    "caption",
    "duration_sec",
    "source",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: python3 scripts/validate_episode.py path/to/episode.json")

    path = Path(sys.argv[1])
    if not path.is_file():
        fail(f"file not found: {path}")

    try:
        episode = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc}")

    missing = REQUIRED_ROOT_FIELDS - episode.keys()
    if missing:
        fail(f"missing root fields: {', '.join(sorted(missing))}")

    segments = episode["segments"]
    if not isinstance(segments, list) or not segments:
        fail("segments must be a non-empty list")

    indexes = []
    duration_sum = 0.0
    for position, segment in enumerate(segments, start=1):
        missing = REQUIRED_SEGMENT_FIELDS - segment.keys()
        if missing:
            fail(f"segment {position} missing fields: {', '.join(sorted(missing))}")
        if segment["index"] != position:
            fail(f"segment {position} has index {segment['index']}")
        if not segment["narration"].strip():
            fail(f"segment {position} has empty narration")
        if not segment["visual_query"].strip():
            fail(f"segment {position} has empty visual_query")
        duration = segment["duration_sec"]
        if not isinstance(duration, (int, float)) or not 2.5 <= duration <= 5.0:
            fail(f"segment {position} duration must be between 2.5 and 5.0 seconds")
        source = segment["source"]
        for key in ("status", "source_url", "license", "creator"):
            if key not in source:
                fail(f"segment {position} source missing {key}")
        indexes.append(segment["index"])
        duration_sum += duration

    if indexes != list(range(1, len(segments) + 1)):
        fail("segment indexes must be consecutive")

    if not 50 <= duration_sum <= 70:
        fail(f"sum of segment durations is {duration_sum:g}s; expected 50-70s")

    if not 12 <= len(segments) <= 18:
        print(f"WARN: {len(segments)} segments is outside the recommended 12-18 range")

    print(
        f"OK: {path} | {len(segments)} segments | "
        f"{duration_sum:g}s | media status: "
        f"{sum(segment['source']['status'] == 'ready' for segment in segments)}/"
        f"{len(segments)} ready"
    )


if __name__ == "__main__":
    main()
