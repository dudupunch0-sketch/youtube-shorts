#!/usr/bin/env python3
"""Render a human-review sheet from a publish manifest."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

try:  # direct execution puts scripts/ on sys.path; tests import scripts.*
    from publish_metadata import tags_length, utf8_length
    from publish_validation import check_manifest
except ImportError:  # pragma: no cover - import style shim
    from scripts.publish_metadata import tags_length, utf8_length
    from scripts.publish_validation import check_manifest

API_LIMITS_NOTE = (
    "썸네일, 재생목록, 끝 화면, 댓글 기본값, 저작권 클레임은 Data API로 처리할 수 없습니다. "
    "아래 수동 항목은 Studio에서 확인하세요."
)


def clean(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(" ".join(text.split()))


def link(label: str, url: Any) -> str:
    value = clean(url)
    return f"[{label}]({value})" if value else "미기록"


def render(manifest: dict[str, Any]) -> str:
    metadata = manifest.get("metadata") or {}
    status = manifest.get("status") or {}
    review = manifest.get("review") or {}
    entries = manifest.get("attribution") or []
    limits = manifest.get("limits") or {}
    result = check_manifest(manifest)

    description = str(metadata.get("description") or "")
    description_bytes = utf8_length(description)
    description_limit = int(limits.get("description_max_bytes", 5000))
    title = str(metadata.get("title") or "")
    tags = [str(tag) for tag in metadata.get("tags") or []]

    verdict = "통과" if result["passed"] else f"실패 {len(result['failures'])}건"

    lines = [
        f"# 게시 검토표 — {clean(title)}",
        "",
        f"- Episode: `{clean(manifest.get('episode_id'))}`",
        f"- 프로필: `{clean(manifest.get('publish_profile'))}`",
        f"- 상업적 이용 설정: `{manifest.get('commercial_use')}`",
        f"- 검토 상태: `{clean(review.get('status'))}`",
        f"- 검증 결과: {verdict}",
        "",
        "> 이 시트는 게시 승인용입니다. 승인은 `scripts/approve_publish.py`로 기록하고,",
        "> 업로드는 `scripts/validate_publish.py`가 통과한 뒤에만 가능합니다.",
        "",
    ]

    if result["failures"]:
        lines.extend(["## 검증 실패", ""])
        lines.extend(f"- {clean(item)}" for item in result["failures"])
        lines.append("")
    if result["warnings"]:
        lines.extend(["## 확인 필요", ""])
        lines.extend(f"- {clean(item)}" for item in result["warnings"])
        lines.append("")

    lines.extend(
        [
            "## 메타데이터",
            "",
            f"- 제목: {clean(title)}",
            f"- 제목 길이: {len(title)}자 / 상한 {limits.get('title_max_chars', 100)}자",
            f"- 설명문 길이: {description_bytes}바이트 / 상한 {description_limit}바이트",
            f"- 태그: {', '.join(tags) if tags else '없음'} "
            f"({tags_length(tags)}자 / 상한 {limits.get('tags_max_total_chars', 500)}자)",
            f"- 카테고리: `{clean(metadata.get('category_id'))}`",
            f"- 언어: `{clean(metadata.get('default_language'))}` / "
            f"오디오 `{clean(metadata.get('default_audio_language'))}`",
            "",
            "## 공개 설정",
            "",
            f"- 업로드 공개 상태: `{clean(status.get('privacy_status'))}`",
            f"- 예약 공개: `{clean(status.get('publish_at')) or '없음'}`",
            f"- 아동용 선언: `{status.get('self_declared_made_for_kids')}`",
            f"- 합성 미디어 선언: `{status.get('contains_synthetic_media')}`",
            "- 사람 판단: `[ ] 이 공개 설정으로 진행`",
            "",
            "## 설명문 전문",
            "",
            "```text",
            description or "(비어 있음)",
            "```",
            "",
            "## 장면 주장 유형",
            "",
        ]
    )
    summary = manifest.get("claim_summary") or {}
    if summary:
        lines.extend(f"- `{clean(key)}`: {value}개" for key, value in sorted(summary.items()))
    else:
        lines.append("- 기록 없음")
    lines.append("")

    lines.extend([f"## 출처 {len(entries)}건", ""])
    if not entries:
        lines.extend(["**출처 없음** — 선택된 미디어 자산이 없습니다.", ""])
    for index, entry in enumerate(entries, start=1):
        scenes = ", ".join(str(item) for item in entry.get("segments") or [])
        decision = entry.get("license_decision")
        lines.extend(
            [
                f"### 출처 {index} — 장면 {scenes}",
                "",
                f"- 원본 페이지: {link('landing page', entry.get('landing_url'))}",
                f"- 파일: {link('열기', entry.get('source_url'))}",
                f"- 제작자: {clean(entry.get('creator')) or '미기록'}",
                f"- 라이선스: `{clean(entry.get('license')) or '미기록'}`",
                f"- 라이선스 URL: {link('확인', entry.get('license_url'))}",
                f"- 자산 승인 상태: `{clean(entry.get('review_status'))}`",
                f"- 라이선스 판정: `{clean(decision)}` — {clean(entry.get('license_reason'))}",
                f"- 상업적 이용 가능: `{entry.get('commercial_use_allowed')}`",
                f"- 표기 문구: {clean(entry.get('line'))}",
            ]
        )
        for condition in entry.get("license_conditions") or []:
            lines.append(f"- 조건: {clean(condition)}")
        lines.extend(["- 사람 판단: `[ ] 승인  [ ] 교체  [ ] 추가 확인`", ""])

    checklist = manifest.get("manual_checklist") or []
    lines.extend(["## API로 처리하지 않는 항목", "", f"> {API_LIMITS_NOTE}", ""])
    if checklist:
        lines.extend(f"- `[ ]` {clean(item)}" for item in checklist)
    else:
        lines.append("- 기록된 항목이 없습니다.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    output = args.output or args.manifest.with_name(
        args.manifest.name.replace(".publish.json", ".publish-review.md")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(manifest), encoding="utf-8")
    print(f"Wrote publish review sheet: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
