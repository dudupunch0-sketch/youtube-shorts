#!/usr/bin/env python3
"""Render a clickable human-review report from a media manifest."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


def clean(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(" ".join(text.split()))


def link(label: str, url: Any) -> str:
    value = clean(url)
    return f"[{label}]({value})" if value else "미기록"


def render(manifest: dict[str, Any]) -> str:
    segments = manifest.get("segments", [])
    candidate_count = sum(len(segment.get("candidates", [])) for segment in segments)
    covered = sum(bool(segment.get("candidates")) for segment in segments)
    approved = sum(segment.get("asset", {}).get("status") == "approved" for segment in segments)

    lines = [
        f"# 미디어 후보 검토표 — {clean(manifest.get('title'))}",
        "",
        f"- Episode: `{clean(manifest.get('episode_id'))}`",
        f"- 장면: {len(segments)}개",
        f"- 후보가 있는 장면: {covered}/{len(segments)}개",
        f"- 수집 후보: {candidate_count}개",
        f"- 승인된 자산: {approved}/{len(segments)}개",
        "",
        "> 라이선스와 실제 사용 가능 여부는 자동 판단하지 않습니다. 아래 원본 페이지와 라이선스를 직접 확인한 뒤, 사용할 후보 번호를 알려주세요.",
        "> 예: `1번 후보 1·2 사용 검토, 4번 후보 1 사용, 나머지는 추가 검색`",
        "",
        "## 판단 기준",
        "",
        "- `unknown` 또는 빈 라이선스: 사용 전 권리 확인 필요",
        "- 공식 캐릭터 아트·스크린샷·로고: 플랫폼 정책과 권리 범위를 별도 확인",
        "- 사용할 후보는 원본 페이지, 제작자, 라이선스, 출처 표기 조건까지 함께 확정",
        "- 후보가 없는 장면은 추가 검색이 필요하며 자동 생성하지 않음",
        "",
    ]

    for segment in segments:
        index = segment.get("index")
        candidates = segment.get("candidates", [])
        search = segment.get("search", {})
        visual_query = segment.get("visual_query") or (search.get("queries") or [""])[0]
        lines.extend(
            [
                f"## 장면 {index} — {clean(segment.get('caption'))}",
                "",
                f"- 내레이션: {clean(segment.get('narration'))}",
                f"- 검색 의도: `{clean(visual_query)}`",
                f"- 검색 상태: `{clean(search.get('status'))}`",
                "",
            ]
        )
        visual = segment.get("visual") or {}
        if visual.get("layout"):
            selected = visual.get("assets") or []
            refs = ", ".join(
                f"{item.get('position')}: 후보 {item.get('candidate_index')}"
                for item in selected
            ) or "아직 선택되지 않음"
            lines.extend([f"- 화면 레이아웃: `{clean(visual.get('layout'))}`", f"- 선택 후보: {refs}", ""])
        if search.get("errors"):
            lines.extend([f"- 검색 오류: `{clean('; '.join(search['errors']))}`", ""])
        if not candidates:
            lines.extend(["**후보 없음** — 이 장면은 추가 검색이 필요합니다.", ""])
            continue

        for candidate_index, candidate in enumerate(candidates, start=1):
            license_value = clean(candidate.get("license")) or "unknown"
            lines.extend(
                [
                    f"### 후보 {candidate_index} — {clean(candidate.get('provider'))}",
                    "",
                    f"- 제목: {clean(candidate.get('title')) or '미기록'}",
                    f"- 미리보기/파일: {link('열기', candidate.get('asset_url'))}",
                    f"- 원본 페이지: {link('landing page', candidate.get('landing_url'))}",
                    *(
                        [f"- 모바일 캡처: [로컬 파일](../playwright/namuwiki/{Path(candidate['capture_path']).name})"]
                        if candidate.get("capture_path")
                        else []
                    ),
                    *(
                        [
                            f"- 캡처 맥락: `{clean(candidate.get('capture_context'))}`"
                            + (
                                f" ({candidate.get('context_rows')}행 × {candidate.get('context_columns')}열)"
                                if candidate.get("context_rows") and candidate.get("context_columns")
                                else ""
                            )
                        ]
                        if candidate.get("capture_context")
                        else []
                    ),
                    f"- 라이선스: `{license_value}`",
                    f"- 라이선스 URL: {link('확인', candidate.get('license_url'))}",
                    f"- 제작자: {clean(candidate.get('creator')) or '미기록'}",
                    f"- 출처 표기: {clean(candidate.get('attribution')) or '미기록'}",
                    f"- 현재 상태: `{clean(candidate.get('review_status')) or 'needs_review'}`",
                    "- 사람 판단: `[ ] 승인  [ ] 거절  [ ] 추가 확인`",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    output = args.output or args.manifest.with_name(
        args.manifest.name.replace(".media.json", ".media-review.md")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(manifest), encoding="utf-8")
    print(f"Wrote media review report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
