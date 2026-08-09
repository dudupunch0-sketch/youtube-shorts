#!/usr/bin/env python3
"""Set a scene's visual layout and selected candidate references."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


LAYOUT_ALIASES = {"split_2up": "split_2up_left_right"}
LAYOUT_RULES = {
    "full_frame": {"positions": ["full"], "fit": "cover"},
    "split_2up_left_right": {"positions": ["left", "right"], "fit": "contain"},
    "split_2up_top_bottom": {"positions": ["top", "bottom"], "fit": "contain"},
    "sequence": {"positions": ["sequence"], "fit": "cover"},
}
TRANSITIONS = ("fade", "slide_left", "slide_up", "cut")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("segment", type=int)
    parser.add_argument("layout", choices=sorted({*LAYOUT_RULES, *LAYOUT_ALIASES}))
    parser.add_argument("candidate_indices", type=int, nargs="+")
    parser.add_argument("--transition", choices=TRANSITIONS, default="fade")
    parser.add_argument("--transition-duration", type=float, default=0.28)
    args = parser.parse_args()

    layout = LAYOUT_ALIASES.get(args.layout, args.layout)
    if layout == "sequence":
        if not 2 <= len(args.candidate_indices) <= 4:
            raise SystemExit("sequence requires 2-4 candidate indices")
    elif len(args.candidate_indices) != len(LAYOUT_RULES[layout]["positions"]):
        expected = len(LAYOUT_RULES[layout]["positions"])
        raise SystemExit(f"{args.layout} requires exactly {expected} candidate index(es), received {len(args.candidate_indices)}")
    if len(set(args.candidate_indices)) != len(args.candidate_indices):
        raise SystemExit("candidate indices must be unique")

    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    segment = next((item for item in data["segments"] if item["index"] == args.segment), None)
    if segment is None:
        raise SystemExit(f"segment not found: {args.segment}")
    candidates = segment.get("candidates", [])
    for index in args.candidate_indices:
        if not 1 <= index <= len(candidates):
            raise SystemExit(
                f"segment {args.segment} has {len(candidates)} candidate(s); "
                f"candidate {index} is invalid"
            )

    positions = LAYOUT_RULES[layout]["positions"]
    existing_assets = segment.get("visual", {}).get("assets", []) if isinstance(segment.get("visual"), dict) else []
    if layout == "sequence":
        positions = ["sequence"] * len(args.candidate_indices)
    transition_sequence = []
    if layout == "sequence":
        start = TRANSITIONS.index(args.transition)
        transition_sequence = [
            TRANSITIONS[(start + boundary) % len(TRANSITIONS)]
            for boundary in range(len(args.candidate_indices) - 1)
        ]
    segment["visual"] = {
        "layout": layout,
        "fit": LAYOUT_RULES[layout]["fit"],
        "caption_safe_area": "bottom",
        "assets": [
            {
                "position": position,
                **({"order": order} if layout == "sequence" else {}),
                "candidate_id": candidates[candidate_index - 1].get("candidate_id"),
                "candidate_index": candidate_index,
                "status": next((item.get("status") for item in existing_assets if item.get("candidate_index") == candidate_index), "needs_review"),
                "mode": next((item.get("mode") for item in existing_assets if item.get("candidate_index") == candidate_index), "sourced"),
                "path": next((item.get("path") for item in existing_assets if item.get("candidate_index") == candidate_index), None),
                "source_url": candidates[candidate_index - 1].get("asset_url"),
                "landing_url": candidates[candidate_index - 1].get("landing_url"),
                "license": candidates[candidate_index - 1].get("license"),
                "license_url": candidates[candidate_index - 1].get("license_url"),
                "creator": candidates[candidate_index - 1].get("creator"),
                "attribution": candidates[candidate_index - 1].get("attribution"),
                "review_notes": "Candidate selected for layout review; rights confirmation still required.",
            }
            for order, (position, candidate_index) in enumerate(zip(positions, args.candidate_indices), start=1)
        ],
        "transition": {
            "default": args.transition,
            "duration_sec": args.transition_duration,
            "sequence": transition_sequence,
            "avoid_consecutive_same": True,
        },
    }
    args.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Set segment {args.segment}: {args.layout} ({len(args.candidate_indices)} candidate refs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
