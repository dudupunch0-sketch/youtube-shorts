#!/usr/bin/env python3
"""Create a YouTube publish plan from an episode and its media manifest.

The plan is always written at ``review.status = needs_review``. Nothing here
approves an asset, a license, or a publish time.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

try:  # direct execution puts scripts/ on sys.path; tests import scripts.*
    from publish_metadata import (
        assemble_description,
        attribution_entries,
        build_description_blocks,
        claim_summary,
        tags_length,
        utf8_length,
    )
except ImportError:  # pragma: no cover - import style shim
    from scripts.publish_metadata import (
        assemble_description,
        attribution_entries,
        build_description_blocks,
        claim_summary,
        tags_length,
        utf8_length,
    )

DEFAULT_PIPELINE = Path("config/pipeline.json")


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"{label} not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid {label} JSON: {error}") from error


def resolve_profile(publish: dict[str, Any], name: str | None) -> tuple[str, dict[str, Any]]:
    profiles = publish.get("profiles") or {}
    profile_name = name or publish.get("default_profile")
    if profile_name not in profiles:
        available = ", ".join(sorted(profiles)) or "없음"
        raise SystemExit(f"unknown publish profile: {profile_name!r} (available: {available})")
    return profile_name, profiles[profile_name]


def build_manifest(
    episode_path: Path,
    episode: dict[str, Any],
    media_path: Path,
    media: dict[str, Any],
    publish: dict[str, Any],
    profile_name: str,
    profile: dict[str, Any],
    overrides: dict[str, Any],
    render_report: Path | None,
    video_path: str | None,
) -> dict[str, Any]:
    commercial_use = bool(publish.get("commercial_use", True))
    disclosure = publish.get("ai_disclosure") or {}
    entries = attribution_entries(media, commercial_use=commercial_use)
    summary = claim_summary(episode)

    blocks = build_description_blocks(
        episode,
        entries,
        profile,
        disclosure,
        summary,
        overrides.get("description_blocks"),
    )
    description = assemble_description(blocks)

    tags = overrides.get("tags")
    if tags is None:
        tags = list(profile.get("base_tags") or [])
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]

    episode_id = media.get("episode_id") or episode_path.stem
    return {
        "manifest_version": 1,
        "episode_id": episode_id,
        "episode_path": str(episode_path),
        "media_manifest": str(media_path),
        "render_report": str(render_report) if render_report else None,
        "video_path": video_path,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "publish_profile": profile_name,
        "commercial_use": commercial_use,
        "segment_count": len(media.get("segments") or episode.get("segments") or []),
        "limits": publish.get("limits") or {},
        "metadata": {
            "title": overrides.get("title") or episode.get("title"),
            "title_candidates": overrides.get("title_candidates") or [],
            "description": description,
            "description_blocks": blocks,
            "tags": tags,
            "category_id": str(overrides.get("category_id") or profile.get("category_id") or ""),
            "default_language": profile.get("default_language"),
            "default_audio_language": profile.get("default_audio_language"),
        },
        "status": {
            "privacy_status": publish.get("upload_privacy_status", "private"),
            "publish_at": overrides.get("publish_at"),
            "self_declared_made_for_kids": bool(profile.get("made_for_kids", False)),
            "contains_synthetic_media": bool(profile.get("contains_synthetic_media", True)),
            "license": "youtube",
            "embeddable": True,
        },
        "attribution": entries,
        "claim_summary": summary,
        "disclosure": {
            "required": bool(disclosure.get("required", True)),
            "api_field": disclosure.get("api_field", "status.containsSyntheticMedia"),
            "description_sentence_ko": disclosure.get("description_sentence_ko"),
        },
        "manual_checklist": list(publish.get("manual_checklist") or []),
        "review": {"status": "needs_review", "approved_by": None, "approved_at": None, "notes": []},
        "checks": {"validated_at": None, "passed": None, "failures": [], "warnings": []},
        "upload": {
            "state": "not_uploaded",
            "video_id": null_if_missing(overrides.get("video_id")),
            "uploaded_at": None,
            "promoted_at": None,
            "attempts": [],
        },
    }


def null_if_missing(value: Any) -> Any:
    return value or None


def default_path(episode_id: str, suffix: str) -> Path:
    return Path("output/manifests") / f"{episode_id}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media_manifest", type=Path)
    parser.add_argument("--episode", type=Path, help="기본값은 media manifest의 episode_path")
    parser.add_argument("--pipeline", type=Path, default=DEFAULT_PIPELINE)
    parser.add_argument("--profile", help="config/pipeline.json publish.profiles의 키")
    parser.add_argument("--overrides", type=Path, help="config/publish/<episode_id>.json")
    parser.add_argument("--render-report", type=Path)
    parser.add_argument("--video", help="게시할 MP4 경로")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    media = load_json(args.media_manifest, "media manifest")
    episode_path = args.episode or Path(str(media.get("episode_path") or ""))
    episode = load_json(episode_path, "episode")

    pipeline = load_json(args.pipeline, "pipeline config")
    publish = pipeline.get("publish")
    if not publish:
        raise SystemExit("config/pipeline.json에 publish 블록이 없습니다")
    profile_name, profile = resolve_profile(publish, args.profile)

    episode_id = media.get("episode_id") or episode_path.stem
    overrides_path = args.overrides or Path("config/publish") / f"{episode_id}.json"
    overrides = load_json(overrides_path, "publish overrides") if overrides_path.is_file() else {}

    render_report = args.render_report
    if render_report is None:
        candidate = default_path(episode_id, ".render.json")
        render_report = candidate if candidate.is_file() else None
    video_path = args.video or (f"output/video/{episode_id}.mp4" if render_report else None)

    manifest = build_manifest(
        episode_path,
        episode,
        args.media_manifest,
        media,
        publish,
        profile_name,
        profile,
        overrides,
        render_report,
        video_path,
    )

    output = args.output or default_path(episode_id, ".publish.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    metadata = manifest["metadata"]
    blocked = [entry for entry in manifest["attribution"] if entry["license_decision"] != "allow"]
    print(f"Wrote publish plan: {output}")
    print(f"Profile: {profile_name}; commercial_use: {manifest['commercial_use']}")
    print(f"Title: {len(str(metadata['title'] or ''))} chars")
    print(f"Description: {utf8_length(metadata['description'])} bytes")
    print(f"Tags: {len(metadata['tags'])} ({tags_length(metadata['tags'])} chars)")
    print(f"Sources: {len(manifest['attribution'])}; license-blocked: {len(blocked)}")
    print("Review status: needs_review")
    if not render_report:
        print("NOTE: 최종 render 보고서가 없습니다. 검증은 렌더 완료 후에 통과합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
