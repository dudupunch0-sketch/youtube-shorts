#!/usr/bin/env python3
"""Validate a rendered Shorts MP4 and its render report."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from audio_validation import validate_wav


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("draft") and not args.allow_draft:
        raise SystemExit("render is a draft; pass --allow-draft for review validation")
    output = Path(report["output"])
    if not output.is_absolute():
        output = args.report.parent.parent.parent / output
    if not output.is_file() or output.stat().st_size < 10_000:
        raise SystemExit(f"missing or suspiciously small MP4: {output}")
    duration = float(report.get("duration_sec", 0))
    if not 50 <= duration <= 70:
        raise SystemExit(f"render duration outside 50-70 seconds: {duration}")
    if report.get("width") != 1080 or report.get("height") != 1920:
        raise SystemExit("render report is not 1080x1920")
    audio_path = Path(report["audio_path"])
    if not audio_path.is_absolute():
        audio_path = args.report.parent.parent.parent / audio_path
    audio = validate_wav(audio_path)
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise SystemExit("imageio-ffmpeg is required for MP4 metadata validation") from error
    probe = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    details = probe.stderr
    size_match = re.search(r"(\d{3,5})x(\d{3,5})", details)
    if not size_match or (int(size_match.group(1)), int(size_match.group(2))) != (1080, 1920):
        raise SystemExit("MP4 metadata does not contain 1080x1920 video")
    print(f"OK: {output} | {duration:.3f}s | 1080x1920 | audio {audio['duration_sec']:.3f}s")
    if report.get("draft"):
        print("NOTE: draft render validated; media rights and final approval remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
