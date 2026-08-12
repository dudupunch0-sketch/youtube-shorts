#!/usr/bin/env python3
"""Validate a media manifest and its approved still-image assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ASSET_STATUSES = {"pending", "needs_review", "approved", "rejected"}
LAYOUT_ALIASES = {"split_2up": "split_2up_left_right"}
LAYOUT_RULES = {
    "full_frame": {"min_assets": 1, "max_assets": 1, "positions": ["full"]},
    "split_2up_left_right": {"min_assets": 2, "max_assets": 2, "positions": ["left", "right"]},
    "split_2up_top_bottom": {"min_assets": 2, "max_assets": 2, "positions": ["top", "bottom"]},
    "sequence": {"min_assets": 2, "max_assets": 4, "positions": ["sequence"]},
}
TRANSITIONS = {"fade", "slide_left", "slide_up", "cut"}
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


def validate_approved_asset(asset: dict[str, Any], segment_index: int, asset_label: str, manifest_root: Path) -> None:
    mode = asset.get("mode")
    if mode not in {"sourced", "generated"}:
        fail(f"segment {segment_index} {asset_label}: invalid asset mode {mode!r}")
    relative_path = asset.get("path")
    if not isinstance(relative_path, str) or not relative_path:
        fail(f"segment {segment_index} {asset_label}: missing asset path")
    asset_path = (manifest_root / relative_path).resolve()
    if manifest_root not in asset_path.parents:
        fail(f"segment {segment_index} {asset_label}: asset escapes repository root")
    if asset_path.suffix.lower() not in IMAGE_EXTENSIONS:
        fail(f"segment {segment_index} {asset_label}: unsupported image extension {asset_path.suffix}")
    if not asset_path.is_file() or asset_path.stat().st_size < 1024:
        fail(f"segment {segment_index} {asset_label}: missing or suspiciously small asset {asset_path}")
    if not valid_image_header(asset_path):
        fail(f"segment {segment_index} {asset_label}: invalid image header {asset_path}")

    if mode == "sourced":
        for field in ("source_url", "landing_url", "license", "license_url", "creator", "attribution"):
            if not asset.get(field):
                fail(f"segment {segment_index} {asset_label}: sourced asset missing {field}")
    else:
        for field in ("generator", "prompt"):
            if not asset.get(field):
                fail(f"segment {segment_index} {asset_label}: generated asset missing {field}")


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

        visual = segment.get("visual")
        if isinstance(visual, dict):
            layout_raw = visual.get("layout", "full_frame")
            layout = LAYOUT_ALIASES.get(layout_raw, layout_raw)
            if layout not in LAYOUT_RULES:
                fail(f"segment {expected_index}: invalid visual layout {layout_raw!r}")
            visual_assets = visual.get("assets", [])
            if not isinstance(visual_assets, list):
                fail(f"segment {expected_index}: visual.assets must be a list")
            rule = LAYOUT_RULES[layout]
            if visual_assets and not rule["min_assets"] <= len(visual_assets) <= rule["max_assets"]:
                fail(
                    f"segment {expected_index}: layout {layout_raw!r} requires "
                    f"{rule['min_assets']}-{rule['max_assets']} visual asset(s), received {len(visual_assets)}"
                )
            positions = [item.get("position") for item in visual_assets]
            expected_positions = ["sequence"] * len(visual_assets) if layout == "sequence" else rule["positions"]
            if visual_assets and positions != expected_positions:
                fail(f"segment {expected_index}: visual asset positions must be {expected_positions}")
            if layout == "sequence" and visual_assets:
                orders = [item.get("order") for item in visual_assets]
                if orders != list(range(1, len(visual_assets) + 1)):
                    fail(f"segment {expected_index}: sequence asset orders must be consecutive from 1")
            transition = visual.get("transition") or {}
            if transition:
                if not isinstance(transition, dict):
                    fail(f"segment {expected_index}: visual.transition must be an object")
                default_transition = transition.get("default", "fade")
                if default_transition not in TRANSITIONS:
                    fail(f"segment {expected_index}: invalid default transition {default_transition!r}")
                try:
                    duration = float(transition.get("duration_sec", 0.28))
                except (TypeError, ValueError):
                    fail(f"segment {expected_index}: invalid transition duration")
                if not 0.0 <= duration <= 1.5:
                    fail(f"segment {expected_index}: transition duration must be between 0 and 1.5 seconds")
                transition_sequence = transition.get("sequence", [])
                if not isinstance(transition_sequence, list) or any(item not in TRANSITIONS for item in transition_sequence):
                    fail(f"segment {expected_index}: invalid transition sequence")
                expected_transition_count = max(len(visual_assets) - 1, 0) if layout == "sequence" else 0
                if visual_assets and len(transition_sequence) != expected_transition_count:
                    fail(
                        f"segment {expected_index}: sequence transition count must be {expected_transition_count}"
                    )
                if transition.get("avoid_consecutive_same", True):
                    for left, right in zip(transition_sequence, transition_sequence[1:]):
                        if left == right:
                            fail(f"segment {expected_index}: consecutive transitions repeat {left!r}")
            selected_assets = visual_assets
        else:
            selected_assets = [asset] if asset else []

        for selected_index, selected_asset in enumerate(selected_assets, start=1):
            if not isinstance(selected_asset, dict):
                fail(f"segment {expected_index} visual asset {selected_index}: expected object")
            selected_status = selected_asset.get("status")
            if selected_status not in ASSET_STATUSES:
                fail(f"segment {expected_index} visual asset {selected_index}: invalid status {selected_status!r}")
            candidate_index = selected_asset.get("candidate_index")
            if candidate_index is not None and not 1 <= candidate_index <= len(candidates):
                fail(f"segment {expected_index} visual asset {selected_index}: invalid candidate_index")
            candidate_id = selected_asset.get("candidate_id")
            if candidate_id and candidate_index is not None:
                expected_candidate_id = candidates[candidate_index - 1].get("candidate_id")
                if expected_candidate_id and candidate_id != expected_candidate_id:
                    fail(
                        f"segment {expected_index} visual asset {selected_index}: "
                        "candidate_id does not match candidate_index"
                    )
            if selected_status == "approved":
                validate_approved_asset(
                    selected_asset,
                    expected_index,
                    f"visual asset {selected_index}",
                    manifest_root,
                )
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
