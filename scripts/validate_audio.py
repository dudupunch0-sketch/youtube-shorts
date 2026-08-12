#!/usr/bin/env python3
"""Validate all WAV files referenced by a local TTS timing manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_validation import AudioValidationError, validate_wav


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    root = args.manifest.parent.parent.parent.resolve()
    failures = []
    checked = 0
    for segment in data.get("segments", []):
        path = Path(segment["audio_path"])
        if not path.is_absolute():
            path = root / path
        try:
            metrics = validate_wav(path)
            segment["audio_validation"] = metrics
            checked += 1
            print(
                f"OK segment {segment.get('index')}: {metrics['duration_sec']:.2f}s "
                f"peak={metrics['peak_normalized']:.3f} rms={metrics['rms_normalized']:.3f}"
            )
        except (KeyError, OSError, AudioValidationError) as error:
            failures.append(f"segment {segment.get('index')}: {error}")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        raise SystemExit(f"{len(failures)} audio file(s) failed validation")
    args.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: validated {checked} WAV file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
