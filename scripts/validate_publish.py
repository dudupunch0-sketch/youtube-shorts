#!/usr/bin/env python3
"""Validate a publish manifest before upload.

Runs the manifest checks and, unless skipped, the render/MP4 checks. The result
is written back into the manifest's ``checks`` block so the review sheet and the
uploader see the same verdict.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

try:  # direct execution puts scripts/ on sys.path; tests import scripts.*
    from publish_validation import check_manifest, check_render
except ImportError:  # pragma: no cover - import style shim
    from scripts.publish_validation import check_manifest, check_render


def validate(manifest: dict[str, Any], root: Path, *, skip_render: bool) -> dict[str, Any]:
    result = check_manifest(manifest)
    failures = list(result["failures"])
    warnings = list(result["warnings"])
    if skip_render:
        warnings.append("render 검증을 건너뛰었습니다. 업로드 전에 반드시 다시 검증하세요.")
    else:
        render_result = check_render(manifest, root)
        failures.extend(render_result["failures"])
        warnings.extend(render_result["warnings"])
    return {"passed": not failures, "failures": failures, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--skip-render",
        action="store_true",
        help="렌더 전 단계에서 메타데이터·권리·게이트만 검사한다",
    )
    parser.add_argument("--root", type=Path, help="상대 경로 기준 디렉터리. 기본값은 현재 위치")
    parser.add_argument(
        "--no-write", action="store_true", help="manifest의 checks 블록을 갱신하지 않는다"
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    root = args.root or Path.cwd()
    result = validate(manifest, root, skip_render=args.skip_render)

    if not args.no_write:
        manifest["checks"] = {
            "validated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "passed": result["passed"],
            "failures": result["failures"],
            "warnings": result["warnings"],
            "render_checked": not args.skip_render,
        }
        args.manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    for item in result["warnings"]:
        print(f"WARN: {item}")
    if result["passed"]:
        print(f"OK: {args.manifest} | 게시 준비 완료")
        if args.skip_render:
            print("NOTE: render 검증은 실행되지 않았습니다.")
        return 0

    print(f"FAIL: {args.manifest} | 실패 {len(result['failures'])}건")
    for item in result["failures"]:
        print(f"  - {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
