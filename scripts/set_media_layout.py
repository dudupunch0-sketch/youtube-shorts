#!/usr/bin/env python3
"""Set a scene's visual layout and selected candidate references."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


LAYOUT_COUNTS = {"full_frame": 1, "split_2up": 2}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("segment", type=int)
    parser.add_argument("layout", choices=sorted(LAYOUT_COUNTS))
    parser.add_argument("candidate_indices", type=int, nargs="+")
    args = parser.parse_args()

    expected = LAYOUT_COUNTS[args.layout]
    if len(args.candidate_indices) != expected:
        raise SystemExit(
            f"{args.layout} requires exactly {expected} candidate index(es), "
            f"received {len(args.candidate_indices)}"
        )
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

    positions = ["left", "right"] if args.layout == "split_2up" else ["full"]
    segment["visual"] = {
        "layout": args.layout,
        "fit": "contain" if args.layout == "split_2up" else "cover",
        "caption_safe_area": "bottom",
        "assets": [
            {
                "position": position,
                "candidate_index": candidate_index,
                "status": "needs_review",
                "mode": "sourced",
                "path": None,
                "source_url": None,
                "landing_url": None,
                "license": None,
                "license_url": None,
                "creator": None,
                "attribution": None,
                "review_notes": "Candidate selected for layout review; rights confirmation still required.",
            }
            for position, candidate_index in zip(positions, args.candidate_indices)
        ],
    }
    args.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Set segment {args.segment}: {args.layout} ({len(args.candidate_indices)} candidate refs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
