#!/usr/bin/env python3
"""Recommend and apply scene presentation layouts and transitions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


LAYOUT_ALIASES = {"split_2up": "split_2up_left_right"}
LAYOUTS = {
    "full_frame": {"count": 1, "positions": ["full"], "fit": "cover"},
    "split_2up_left_right": {"count": 2, "positions": ["left", "right"], "fit": "contain"},
    "split_2up_top_bottom": {"count": 2, "positions": ["top", "bottom"], "fit": "contain"},
    "sequence": {"min_count": 2, "max_count": 4, "positions": ["sequence"], "fit": "cover"},
}
TRANSITIONS = ("fade", "slide_left", "slide_up", "cut")
COMPARISON_TERMS = ("비교", "대비", "정반대", "닮", "비슷", "차이", "vs", "versus", "둘")
SEQUENCE_TERMS = ("먼저", "다음", "그리고", "이어", "순서", "과정", "반전")


def stable_candidate_id(candidate: dict[str, Any], index: int) -> str:
    source = "|".join(
        str(candidate.get(key) or "")
        for key in ("provider", "asset_url", "landing_url", "capture_path", "title", "query")
    )
    if not source.strip("|"):
        source = f"candidate-{index}"
    return f"cand-{hashlib.sha1(source.encode('utf-8')).hexdigest()[:12]}"


def canonical_layout(value: str | None) -> str:
    layout = str(value or "full_frame")
    return LAYOUT_ALIASES.get(layout, layout)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SystemExit(f"file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid JSON {path}: {error}") from error
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return data


def merge_dict(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def candidate_indices(segment: dict[str, Any], override: dict[str, Any], layout: str) -> list[int]:
    candidates = segment.get("candidates", [])
    requested_ids = override.get("candidate_ids")
    if isinstance(requested_ids, list) and requested_ids:
        lookup = {item.get("candidate_id"): index for index, item in enumerate(candidates, start=1)}
        return [lookup[item] for item in requested_ids if item in lookup]
    requested = override.get("candidate_indices")
    if isinstance(requested, list) and requested:
        return [int(item) for item in requested]
    if not candidates:
        return []
    if layout in {"split_2up_left_right", "split_2up_top_bottom"}:
        return list(range(1, min(len(candidates), 2) + 1))
    if layout == "sequence":
        return list(range(1, min(len(candidates), 3) + 1))
    return [1]


def recommend_layout(segment: dict[str, Any], override: dict[str, Any]) -> tuple[str, float, str]:
    explicit = override.get("layout") or override.get("mode")
    if explicit and explicit not in {"auto", "planner"}:
        layout = canonical_layout(str(explicit))
        return layout, 1.0, str(override.get("reason") or "Explicit scene override")

    candidates = segment.get("candidates", [])
    if len(candidates) == 0:
        return "full_frame", 0.18, "No candidates collected; reserve a text-card or additional-search fallback."
    text = " ".join(
        str(segment.get(key) or "")
        for key in ("narration", "caption", "visual_query")
    ).lower()
    if len(candidates) >= 2 and any(term.lower() in text for term in COMPARISON_TERMS):
        return "split_2up_left_right", 0.86, "Comparison or contrast language supports parallel two-up framing."
    if len(candidates) >= 2 and any(term.lower() in text for term in SEQUENCE_TERMS):
        return "sequence", 0.78, "Narration suggests an ordered reveal or progression."
    if len(candidates) >= 2:
        return "sequence", 0.58, "Multiple candidates are available; sequence avoids assuming a direct comparison."
    return "full_frame", 0.82, "One candidate is available and can fill the scene."


def choose_transition(scene_index: int, previous: str | None, requested: str | None) -> str:
    if requested in TRANSITIONS:
        return requested
    start = scene_index % len(TRANSITIONS)
    for offset in range(len(TRANSITIONS)):
        choice = TRANSITIONS[(start + offset) % len(TRANSITIONS)]
        if choice != previous:
            return choice
    return "cut"


def transition_plan(
    scene_index: int,
    asset_count: int,
    visual: dict[str, Any],
    override: dict[str, Any],
    previous: str | None,
) -> tuple[dict[str, Any], str | None]:
    existing = visual.get("transition") if isinstance(visual.get("transition"), dict) else {}
    requested = override.get("transition")
    requested_sequence: list[Any] = []
    if isinstance(requested, dict):
        requested_sequence = requested.get("sequence") or []
        requested_default = requested.get("default")
    else:
        requested_default = requested if isinstance(requested, str) else None
    if not requested_sequence:
        requested_sequence = existing.get("sequence") or []
    sequence: list[str] = []
    for boundary in range(max(asset_count - 1, 0)):
        explicit = requested_sequence[boundary] if boundary < len(requested_sequence) else requested_default
        effect = choose_transition(scene_index + boundary, previous, explicit)
        sequence.append(effect)
        previous = effect
    result = {
        "default": requested_default if requested_default in TRANSITIONS else "fade",
        "duration_sec": float(
            (requested.get("duration_sec") if isinstance(requested, dict) else None)
            or existing.get("duration_sec")
            or 0.28
        ),
        "sequence": sequence,
        "avoid_consecutive_same": True,
    }
    return result, previous


def make_visual_asset(
    candidate: dict[str, Any],
    candidate_index: int,
    position: str,
    existing_assets: list[dict[str, Any]],
    order: int | None = None,
) -> dict[str, Any]:
    candidate_id = candidate["candidate_id"]
    previous = next(
        (
            item
            for item in existing_assets
            if item.get("candidate_id") == candidate_id
            or item.get("candidate_index") == candidate_index
        ),
        {},
    )
    result = {
        "position": position,
        "candidate_id": candidate_id,
        "candidate_index": candidate_index,
        "status": previous.get("status", "needs_review"),
        "mode": previous.get("mode", "sourced"),
        "path": previous.get("path"),
        "source_url": previous.get("source_url") or candidate.get("asset_url"),
        "landing_url": previous.get("landing_url") or candidate.get("landing_url"),
        "license": previous.get("license") or candidate.get("license"),
        "license_url": previous.get("license_url") or candidate.get("license_url"),
        "creator": previous.get("creator") or candidate.get("creator"),
        "attribution": previous.get("attribution") or candidate.get("attribution"),
        "review_notes": previous.get("review_notes") or "Candidate selected for presentation review; rights confirmation still required.",
    }
    for key in (
        "provider",
        "content_type",
        "capture_path",
        "capture_metadata_path",
        "capture_context",
        "capture_match",
        "third_party_media_present",
    ):
        if previous.get(key) is not None:
            result[key] = previous[key]
        elif candidate.get(key) is not None:
            result[key] = candidate[key]
    if order is not None:
        result["order"] = order
    return result


def apply_segment(segment: dict[str, Any], override: dict[str, Any], previous_transition: str | None) -> str | None:
    for index, candidate in enumerate(segment.get("candidates", []), start=1):
        candidate.setdefault("candidate_id", stable_candidate_id(candidate, index))
    layout, confidence, reason = recommend_layout(segment, override)
    if layout not in LAYOUTS:
        raise SystemExit(f"segment {segment.get('index')}: unsupported layout {layout}")
    indices = candidate_indices(segment, override, layout)
    candidates = segment.get("candidates", [])
    if layout in {"split_2up_left_right", "split_2up_top_bottom"} and len(indices) != 2:
        reason = f"{reason} Two candidates are required; awaiting additional candidate collection."
        indices = []
    if layout == "sequence" and not 2 <= len(indices) <= 4:
        reason = f"{reason} Sequence needs 2-4 candidates; awaiting additional candidate collection."
        indices = []

    old_visual = segment.get("visual") if isinstance(segment.get("visual"), dict) else {}
    override_assets = override.get("assets") if isinstance(override.get("assets"), list) else []
    existing_assets = [*old_visual.get("assets", []), *override_assets]
    positions = LAYOUTS[layout].get("positions", [])
    if layout == "sequence":
        visual_assets = [
            make_visual_asset(candidates[index - 1], index, "sequence", existing_assets, order=order)
            for order, index in enumerate(indices, start=1)
        ]
    else:
        visual_assets = [
            make_visual_asset(candidates[index - 1], index, positions[position], existing_assets)
            for position, index in enumerate(indices)
        ]
    transition, last_transition = transition_plan(
        int(segment["index"]), len(visual_assets) if layout == "sequence" else 1, old_visual, override, previous_transition
    )
    fit = LAYOUTS[layout]["fit"]
    if any(
        candidates[index - 1].get("provider") == "namuwiki_capture"
        or candidates[index - 1].get("content_type") == "text_excerpt_capture"
        for index in indices
    ):
        # Evidence captures should preserve the complete table/paragraph context.
        fit = "contain"
    segment["visual"] = {
        "layout": layout,
        "fit": fit,
        "caption_safe_area": "bottom",
        "assets": visual_assets,
        "transition": transition,
    }
    segment["presentation"] = {
        "mode": "manual" if override.get("layout") not in {None, "auto", "planner"} else "auto",
        "recommended_layout": layout,
        "confidence": confidence,
        "reason": reason,
        "source": "override" if override.get("layout") not in {None, "auto", "planner"} else "planner",
        "candidate_ids": [candidates[index - 1]["candidate_id"] for index in indices],
    }
    return last_transition


def plan(manifest: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    previous_transition: str | None = None
    for segment in manifest.get("segments", []):
        key = str(segment.get("index"))
        override = overrides.get(key) or overrides.get(int(key)) or {}
        previous_transition = apply_segment(segment, override, previous_transition)
    manifest["presentation_overrides"] = overrides
    manifest["presentation_planner"] = {
        "script": "scripts/plan_presentation.py",
        "transition_policy": "avoid_consecutive_same",
        "stable_candidate_ids": True,
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--overrides", type=Path, help="Optional per-episode presentation override JSON")
    parser.add_argument("--output", type=Path, help="Write to a separate manifest instead of updating in place")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    manifest = load_json(args.manifest)
    overrides = dict(manifest.get("presentation_overrides") or {})
    if args.overrides:
        overrides = merge_dict(overrides, load_json(args.overrides))
    result = plan(manifest, overrides)
    summary = []
    for segment in result.get("segments", []):
        visual = segment.get("visual", {})
        summary.append(
            {
                "index": segment.get("index"),
                "layout": visual.get("layout"),
                "assets": [item.get("candidate_index") for item in visual.get("assets", [])],
                "transitions": (visual.get("transition") or {}).get("sequence", []),
                "confidence": (segment.get("presentation") or {}).get("confidence"),
            }
        )
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    output = args.output or args.manifest
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote presentation plan: {output}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
