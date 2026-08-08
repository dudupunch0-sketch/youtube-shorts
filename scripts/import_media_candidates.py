#!/usr/bin/env python3
"""Merge manually collected web candidates into a scene media manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("candidate_file", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    seed = json.loads(args.candidate_file.read_text(encoding="utf-8"))
    segments = {int(segment["index"]): segment for segment in manifest["segments"]}
    imported = 0
    for item in seed.get("candidates", []):
        index = int(item["segment_index"])
        if index not in segments:
            raise SystemExit(f"unknown segment index: {index}")
        candidate: dict[str, Any] = {
            key: value for key, value in item.items() if key != "segment_index"
        }
        candidate.setdefault("review_status", "needs_review")
        existing_urls = {
            existing.get("asset_url") for existing in segments[index].get("candidates", [])
        }
        if candidate.get("asset_url") not in existing_urls:
            segments[index].setdefault("candidates", []).append(candidate)
            segments[index]["search"]["status"] = "collected"
            imported += 1

    manifest["candidate_imports"] = manifest.get("candidate_imports", [])
    manifest["candidate_imports"].append(
        {
            "file": str(args.candidate_file),
            "imported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "count": imported,
        }
    )
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {imported} manual candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
