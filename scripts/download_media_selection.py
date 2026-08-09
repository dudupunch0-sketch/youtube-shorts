#!/usr/bin/env python3
"""Download selected media references into an ignored local review folder."""

from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


USER_AGENT = "youtube-shorts-media-review/0.1"


def extension_for(candidate: dict, response_type: str | None = None) -> str:
    path = urllib.parse.urlparse(candidate.get("asset_url", "")).path.lower()
    suffix = Path(path).suffix
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    guessed = mimetypes.guess_extension(response_type or "")
    return guessed if guessed in {".jpg", ".jpeg", ".png", ".webp"} else ".bin"


def copy_or_download(candidate: dict, destination: Path, repo_root: Path) -> Path:
    capture_path = candidate.get("capture_path")
    if capture_path:
        local_source = (repo_root / capture_path).resolve()
        if local_source.is_file():
            target = destination.with_suffix(local_source.suffix.lower() or ".png")
            shutil.copy2(local_source, target)
            return target

    asset_url = candidate.get("asset_url")
    if not asset_url or not asset_url.startswith(("http://", "https://")):
        raise SystemExit(f"candidate has no downloadable URL or local capture: {candidate.get('title')}")
    request = urllib.request.Request(asset_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                raise SystemExit(f"candidate is not an image: {asset_url} ({content_type})")
            target = destination.with_suffix(extension_for(candidate, content_type))
            target.write_bytes(response.read())
            return target
    except urllib.error.URLError as error:
        raise SystemExit(f"download failed: {asset_url}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--segment", type=int, nargs="+")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    repo_root = manifest_path.parent.parent.parent
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    wanted = set(args.segment or [segment["index"] for segment in data["segments"]])
    downloaded = 0
    for segment in data["segments"]:
        if segment["index"] not in wanted:
            continue
        visual = segment.get("visual") or {}
        for selected in visual.get("assets", []):
            candidate_index = selected.get("candidate_index")
            candidates = segment.get("candidates", [])
            if not isinstance(candidate_index, int) or not 1 <= candidate_index <= len(candidates):
                raise SystemExit(f"segment {segment['index']}: invalid selected candidate index")
            candidate = candidates[candidate_index - 1]
            position = selected.get("position", "full")
            review_dir = repo_root / "output" / "media-candidates" / data["episode_id"]
            review_dir.mkdir(parents=True, exist_ok=True)
            order = selected.get("order")
            asset_label = f"{position}-{int(order):02d}" if position == "sequence" and order else position
            destination = review_dir / f"segment-{segment['index']:03d}-{asset_label}"
            if not args.force and any(destination.with_suffix(ext).is_file() for ext in (".jpg", ".jpeg", ".png", ".webp")):
                existing = next(destination.with_suffix(ext) for ext in (".jpg", ".jpeg", ".png", ".webp") if destination.with_suffix(ext).is_file())
                output_path = existing
            else:
                output_path = copy_or_download(candidate, destination, repo_root)
            selected.update(
                {
                    "status": "needs_review",
                    "mode": "sourced",
                    "path": output_path.relative_to(repo_root).as_posix(),
                    "source_url": candidate.get("asset_url"),
                    "landing_url": candidate.get("landing_url"),
                    "license": candidate.get("license"),
                    "license_url": candidate.get("license_url"),
                    "creator": candidate.get("creator"),
                    "attribution": candidate.get("attribution"),
                    "review_notes": "Downloaded for local review only; not approved for publication.",
                }
            )
            downloaded += 1

    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Downloaded {downloaded} selected asset(s) for local review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
