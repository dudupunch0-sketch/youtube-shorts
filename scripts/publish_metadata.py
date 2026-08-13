#!/usr/bin/env python3
"""Assemble YouTube publish metadata from episode and media manifests."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

try:  # direct execution puts scripts/ on sys.path; tests import scripts.*
    from publish_licensing import classify_license
except ImportError:  # pragma: no cover - import style shim
    from scripts.publish_licensing import classify_license

BLOCK_ORDER = ("hook", "body", "ai_disclosure", "interpretation_notice", "attribution", "footer")


def utf8_length(value: str) -> int:
    """Return the UTF-8 byte length.

    The YouTube description limit is 5000 bytes, not 5000 characters. Korean
    text costs three bytes per character, so measuring characters would let a
    description pass here and be truncated by the API.
    """
    return len(value.encode("utf-8"))


def tags_length(tags: list[str]) -> int:
    """Return the tag length YouTube counts, including separators."""
    if not tags:
        return 0
    return len(", ".join(tags))


def selected_assets(segment: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the assets a segment actually uses, newest schema first.

    Manifest v2 records chosen assets in ``visual.assets``. Manifest v1 kept a
    single ``asset`` object. Candidates are never returned; an unselected
    candidate must not produce an attribution line.
    """
    visual = segment.get("visual") or {}
    assets = [asset for asset in (visual.get("assets") or []) if asset]
    if assets:
        return assets
    legacy = segment.get("asset") or {}
    if legacy.get("path") or legacy.get("source_url"):
        return [legacy]
    return []


def normalize_url(value: Any) -> str:
    """Normalize a URL for grouping.

    Collectors record the same page with different percent-encoding, so a
    NamuWiki document captured for several scenes would otherwise produce one
    duplicate attribution line per encoding variant.
    """
    if not value:
        return ""
    return unquote(str(value)).strip().rstrip("/")


def attribution_entries(
    media_manifest: dict[str, Any], *, commercial_use: bool
) -> list[dict[str, Any]]:
    """Build one attribution entry per distinct source across all segments."""
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for segment in media_manifest.get("segments", []):
        index = segment.get("index")
        for asset in selected_assets(segment):
            landing = asset.get("landing_url") or asset.get("source_url") or ""
            creator = asset.get("creator") or ""
            license_value = asset.get("license") or ""
            key = (normalize_url(landing), str(creator), str(license_value))
            entry = grouped.get(key)
            if entry is None:
                verdict = classify_license(license_value, commercial_use=commercial_use)
                entry = {
                    "segments": [],
                    "candidate_ids": [],
                    "source_url": asset.get("source_url"),
                    "landing_url": asset.get("landing_url"),
                    "license": license_value or None,
                    "license_url": asset.get("license_url"),
                    "creator": creator or None,
                    "attribution": asset.get("attribution"),
                    "provider": asset.get("provider"),
                    "review_status": asset.get("status"),
                    "license_decision": verdict["decision"],
                    "license_reason": verdict["reason"],
                    "license_conditions": verdict["conditions"],
                    "commercial_use_allowed": verdict["commercial_use_allowed"],
                }
                grouped[key] = entry
            if index is not None and index not in entry["segments"]:
                entry["segments"].append(index)
            candidate_id = asset.get("candidate_id")
            if candidate_id and candidate_id not in entry["candidate_ids"]:
                entry["candidate_ids"].append(candidate_id)
            # A single source reused across scenes is one attribution line, but
            # the strictest review status among them decides the gate.
            if asset.get("status") != "approved":
                entry["review_status"] = asset.get("status")

    entries = sorted(grouped.values(), key=lambda item: min(item["segments"], default=0))
    for entry in entries:
        entry["segments"].sort()
        entry["line"] = attribution_line(entry)
    return entries


def attribution_line(entry: dict[str, Any]) -> str:
    """Format one human-readable source line for the description.

    The scene prefix is always present so a reader can trace a source back to
    the moment it appears, including when the collector already recorded a
    ready-made attribution string.
    """
    scenes = ", ".join(str(index) for index in entry.get("segments", []))
    prefix = f"장면 {scenes}: " if scenes else ""
    if entry.get("attribution"):
        return prefix + " ".join(str(entry["attribution"]).split())
    creator = entry.get("creator") or "제작자 미기록"
    license_value = entry.get("license") or "라이선스 미기록"
    url = entry.get("landing_url") or entry.get("source_url") or ""
    line = f"{prefix}{creator} / {license_value}"
    return f"{line} ({url})" if url else line


def claim_summary(episode: dict[str, Any]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for segment in episode.get("segments", []):
        claim = str(segment.get("claim_type") or "unknown")
        summary[claim] = summary.get(claim, 0) + 1
    return summary


def build_description_blocks(
    episode: dict[str, Any],
    entries: list[dict[str, Any]],
    profile: dict[str, Any],
    disclosure: dict[str, Any],
    summary: dict[str, int],
    overrides: dict[str, Any] | None = None,
) -> dict[str, str]:
    overrides = overrides or {}
    topic = str(episode.get("topic") or "").strip()
    blocks = {
        "hook": str(episode.get("title") or "").strip(),
        "body": f"다루는 주제: {topic}" if topic else "",
        "ai_disclosure": str(disclosure.get("description_sentence_ko") or "").strip(),
        "interpretation_notice": "",
        "attribution": "",
        "footer": str(profile.get("footer") or "").strip(),
    }

    if summary.get("creative_interpretation"):
        blocks["interpretation_notice"] = (
            "이 영상에는 공식 설정이 아닌 해석과 팬 이론이 포함되어 있습니다. "
            "해석 부분은 공식 사실이 아닙니다."
        )

    if entries:
        lines = ["출처 및 라이선스"]
        lines.extend(f"- {entry['line']}" for entry in entries)
        blocks["attribution"] = "\n".join(lines)

    for key, value in overrides.items():
        if key in blocks:
            blocks[key] = str(value).strip()
    return blocks


def assemble_description(blocks: dict[str, str]) -> str:
    return "\n\n".join(blocks[key] for key in BLOCK_ORDER if blocks.get(key)).strip()
