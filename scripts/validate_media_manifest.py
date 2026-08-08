#!/usr/bin/env python3
"""Validate a media manifest and its approved still-image assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ASSET_STATUSES = {"pending", "needs_review", "approved", "rejected"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
WEBP_SIGNATURE = b"RIFF"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def valid_image_header(path: Path) -> bool:
    header = path.read_bytes()[:12]
    if header.startswith(PNG_SIGNATURE) or header.startswith(JPEG_SIGNATURE):
        return True
    return header.startswith(WEBP_SIGNATURE) and header[8:12] == b"WEBP"


def validate(manifest_path: Path) -> tuple[int, int, int]:
    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"manifest not found: {manifest_path}")
    except json.JSONDecodeError as error:
        fail(f"invalid manifest JSON: {error}")

    segments = manifest.get("segments")
    if not isinstance(segments, list) or not 12 <= len(segments) <= 18:
        fail("manifest must contain 12-18 segments")

    approved = 0
    # Manifests live under output/manifests; asset paths are repository-relative.
    manifest_root = manifest_path.parent.parent.parent.resolve()
    for expected_index, segment in enumerate(segments, start=1):
        if segment.get("index") != expected_index:
            fail(f"segment index mismatch at position {expected_index}")
        asset = segment.get("asset") or {}
        status = asset.get("status")
        if status not in ASSET_STATUSES:
            fail(f"segment {expected_index}: invalid asset status {status!r}")
        candidates = segment.get("candidates", [])
        if not isinstance(candidates, list):
            fail(f"segment {expected_index}: candidates must be a list")
        for candidate_index, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                fail(f"segment {expected_index} candidate {candidate_index}: expected object")
            for field in ("provider", "asset_url", "landing_url", "review_status"):
                if not candidate.get(field):
                    fail(f"segment {expected_index} candidate {candidate_index}: missing {field}")

        if status != "approved":
            continue
        mode = asset.get("mode")
        if mode not in {"sourced", "generated"}:
            fail(f"segment {expected_index}: invalid asset mode {mode!r}")
        relative_path = asset.get("path")
        if not isinstance(relative_path, str) or not relative_path:
            fail(f"segment {expected_index}: missing asset path")
        asset_path = (manifest_root / relative_path).resolve()
        if manifest_root not in asset_path.parents:
            fail(f"segment {expected_index}: asset escapes repository root")
        if asset_path.suffix.lower() not in IMAGE_EXTENSIONS:
            fail(f"segment {expected_index}: unsupported image extension {asset_path.suffix}")
        if not asset_path.is_file() or asset_path.stat().st_size < 1024:
            fail(f"segment {expected_index}: missing or suspiciously small asset {asset_path}")
        if not valid_image_header(asset_path):
            fail(f"segment {expected_index}: invalid image header {asset_path}")

        if mode == "sourced":
            for field in ("source_url", "landing_url", "license", "license_url", "creator", "attribution"):
                if not asset.get(field):
                    fail(f"segment {expected_index}: sourced asset missing {field}")
        else:
            for field in ("generator", "prompt"):
                if not asset.get(field):
                    fail(f"segment {expected_index}: generated asset missing {field}")
        approved += 1
    candidate_count = sum(len(segment.get("candidates", [])) for segment in segments)
    return len(segments), approved, candidate_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    total, approved, candidate_count = validate(args.manifest)
    pending = total - approved
    print(
        f"OK: {args.manifest} | {approved}/{total} approved image assets | "
        f"{pending} awaiting review | {candidate_count} collected candidates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
