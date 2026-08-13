#!/usr/bin/env python3
"""Gate checks that run before a publish manifest may be uploaded.

``check_manifest`` is pure and works on the manifest dict alone, so it is unit
testable and can be re-run by the uploader immediately before the API call.
``check_render`` touches the filesystem and is kept separate.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

try:  # direct execution puts scripts/ on sys.path; tests import scripts.*
    from publish_metadata import tags_length, utf8_length
except ImportError:  # pragma: no cover - import style shim
    from scripts.publish_metadata import tags_length, utf8_length

VALID_PRIVACY_STATUS = ("private", "public", "unlisted")
UPLOADED_STATES = ("uploaded", "promoted")


def _limits(manifest: dict[str, Any]) -> dict[str, Any]:
    limits = manifest.get("limits") or {}
    return {
        "title_max_chars": int(limits.get("title_max_chars", 100)),
        "description_max_bytes": int(limits.get("description_max_bytes", 5000)),
        "tags_max_total_chars": int(limits.get("tags_max_total_chars", 500)),
        "shorts_max_duration_seconds": float(limits.get("shorts_max_duration_seconds", 180)),
    }


def check_metadata(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    limits = _limits(manifest)
    metadata = manifest.get("metadata") or {}

    title = str(metadata.get("title") or "").strip()
    if not title:
        failures.append("제목이 비어 있습니다.")
    elif len(title) > limits["title_max_chars"]:
        failures.append(
            f"제목이 {len(title)}자로 상한 {limits['title_max_chars']}자를 넘습니다."
        )

    description = str(metadata.get("description") or "")
    if not description.strip():
        failures.append("설명문이 비어 있습니다.")
    else:
        size = utf8_length(description)
        if size > limits["description_max_bytes"]:
            failures.append(
                f"설명문이 {size}바이트로 상한 {limits['description_max_bytes']}바이트를 "
                "넘습니다. 상한은 문자 수가 아니라 UTF-8 바이트입니다."
            )
        elif size > limits["description_max_bytes"] * 0.9:
            warnings.append(f"설명문이 {size}바이트로 상한에 가깝습니다.")

    tags = metadata.get("tags") or []
    if not isinstance(tags, list):
        failures.append("tags가 리스트가 아닙니다.")
    else:
        total = tags_length([str(tag) for tag in tags])
        if total > limits["tags_max_total_chars"]:
            failures.append(
                f"태그 전체 길이가 {total}자로 상한 {limits['tags_max_total_chars']}자를 넘습니다."
            )

    if not str(metadata.get("category_id") or "").strip():
        failures.append("category_id가 비어 있습니다.")
    for field in ("default_language", "default_audio_language"):
        if not str(metadata.get(field) or "").strip():
            failures.append(f"{field}가 비어 있습니다.")
    return failures, warnings


def check_disclosure(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    status = manifest.get("status") or {}
    metadata = manifest.get("metadata") or {}
    disclosure = manifest.get("disclosure") or {}
    description = str(metadata.get("description") or "")

    if not status.get("contains_synthetic_media"):
        failures.append(
            "contains_synthetic_media가 false입니다. 내레이션이 합성 음성이므로 true여야 합니다."
        )
    sentence = str(disclosure.get("description_sentence_ko") or "").strip()
    if not sentence:
        failures.append("AI 음성 고지 문장이 설정되지 않았습니다.")
    elif sentence not in description:
        failures.append("AI 음성 고지 문장이 설명문에 포함되어 있지 않습니다.")

    summary = manifest.get("claim_summary") or {}
    if summary.get("creative_interpretation"):
        blocks = metadata.get("description_blocks") or {}
        if not str(blocks.get("interpretation_notice") or "").strip():
            failures.append(
                "creative_interpretation 장면이 있는데 해석 표기 블록이 비어 있습니다."
            )

    if status.get("self_declared_made_for_kids"):
        warnings.append("아동용으로 선언되어 있어 댓글이 비활성화됩니다.")
    return failures, warnings


def check_licensing(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    entries = manifest.get("attribution") or []
    if not entries:
        failures.append("출처 항목이 없습니다. 선택된 미디어 자산이 있는지 확인하세요.")

    for entry in entries:
        scenes = ", ".join(str(index) for index in entry.get("segments") or [])
        label = f"장면 {scenes}" if scenes else "출처"
        if entry.get("license_decision") != "allow":
            failures.append(f"{label}: {entry.get('license_reason') or '라이선스 차단'}")
        for field in ("source_url", "license", "creator"):
            if not str(entry.get(field) or "").strip():
                failures.append(f"{label}: 필수 출처 항목 {field}가 비어 있습니다.")
        if entry.get("review_status") != "approved":
            failures.append(
                f"{label}: 자산이 아직 승인되지 않았습니다 "
                f"(현재 `{entry.get('review_status')}`)."
            )
        for condition in entry.get("license_conditions") or []:
            warnings.append(f"{label}: {condition}")

    segments_total = int(manifest.get("segment_count") or 0)
    covered = {index for entry in entries for index in entry.get("segments") or []}
    if segments_total and len(covered) < segments_total:
        missing = sorted(set(range(1, segments_total + 1)) - covered)
        failures.append(
            "선택된 자산이 없는 장면이 있습니다: "
            + ", ".join(str(index) for index in missing)
        )
    return failures, warnings


def check_gates(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    review = manifest.get("review") or {}
    upload = manifest.get("upload") or {}
    status = manifest.get("status") or {}

    if review.get("status") != "approved":
        failures.append(
            f"게시 계획이 승인되지 않았습니다 (현재 `{review.get('status')}`). "
            "scripts/approve_publish.py로 승인하세요."
        )
    elif not review.get("approved_at") or not review.get("approved_by"):
        failures.append("승인 기록에 approved_by 또는 approved_at이 없습니다.")

    if upload.get("state") in UPLOADED_STATES:
        failures.append(
            f"이미 업로드된 에피소드입니다 (state=`{upload.get('state')}`, "
            f"video_id=`{upload.get('video_id')}`)."
        )

    privacy = status.get("privacy_status")
    if privacy not in VALID_PRIVACY_STATUS:
        failures.append(f"privacy_status가 유효하지 않습니다: {privacy!r}")

    publish_at = status.get("publish_at")
    if publish_at:
        if privacy != "private":
            failures.append("publish_at 예약은 privacy_status가 private일 때만 가능합니다.")
        parsed = _parse_timestamp(publish_at)
        if parsed is None:
            failures.append(f"publish_at이 타임존 포함 ISO 8601 형식이 아닙니다: {publish_at!r}")
        elif parsed <= dt.datetime.now(dt.timezone.utc):
            failures.append(f"publish_at이 과거 시각입니다: {publish_at}")
    return failures, warnings


def _parse_timestamp(value: Any) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def check_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Run every filesystem-independent check and return the combined result."""
    failures: list[str] = []
    warnings: list[str] = []
    for check in (check_metadata, check_disclosure, check_licensing, check_gates):
        check_failures, check_warnings = check(manifest)
        failures.extend(check_failures)
        warnings.extend(check_warnings)
    return {"passed": not failures, "failures": failures, "warnings": warnings}


def check_render(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    """Verify the render report and MP4 that the manifest points at."""
    failures: list[str] = []
    warnings: list[str] = []
    limits = _limits(manifest)

    report_path = manifest.get("render_report")
    if not report_path:
        failures.append("render_report 경로가 없습니다. 최종 렌더를 먼저 완료하세요.")
        return {"passed": False, "failures": failures, "warnings": warnings}

    resolved = _resolve(root, report_path)
    if not resolved.is_file():
        failures.append(f"render 보고서를 찾을 수 없습니다: {report_path}")
        return {"passed": False, "failures": failures, "warnings": warnings}

    try:
        report = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        failures.append(f"render 보고서 JSON이 잘못되었습니다: {error}")
        return {"passed": False, "failures": failures, "warnings": warnings}

    if report.get("draft"):
        failures.append("render가 draft입니다. draft는 게시할 수 없습니다.")
    duration = float(report.get("duration_sec") or 0)
    if not 50 <= duration <= 70:
        failures.append(f"영상 길이가 50-70초 범위를 벗어납니다: {duration}")
    if duration >= limits["shorts_max_duration_seconds"]:
        failures.append(
            f"영상 길이가 Shorts 상한 {limits['shorts_max_duration_seconds']}초 이상입니다."
        )
    if (report.get("width"), report.get("height")) != (1080, 1920):
        failures.append(
            f"해상도가 1080x1920이 아닙니다: {report.get('width')}x{report.get('height')}"
        )

    video_path = manifest.get("video_path") or report.get("output")
    if not video_path:
        failures.append("video_path가 없습니다.")
    else:
        video = _resolve(root, video_path)
        if not video.is_file():
            failures.append(f"MP4 파일을 찾을 수 없습니다: {video_path}")
        elif video.stat().st_size < 10_000:
            failures.append(f"MP4 파일이 비정상적으로 작습니다: {video_path}")

    return {"passed": not failures, "failures": failures, "warnings": warnings}


def _resolve(root: Path, value: Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else root / path
