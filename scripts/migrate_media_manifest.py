#!/usr/bin/env python3
"""Migrate a v1 media manifest to the multi-asset visual schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    for segment in data.get("segments", []):
        if "visual" not in segment:
            legacy = segment.get("asset") or {}
            segment["visual"] = {
                "layout": "full_frame",
                "fit": "cover",
                "caption_safe_area": "bottom",
                "assets": [],
            }
            if legacy.get("status") == "approved":
                segment["visual"]["assets"] = [{**legacy, "position": "full"}]
    data["manifest_version"] = max(int(data.get("manifest_version", 1)), 2)
    args.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Migrated media manifest to v{data['manifest_version']}: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
