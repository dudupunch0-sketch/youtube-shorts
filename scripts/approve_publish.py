#!/usr/bin/env python3
"""Record or withdraw human approval on a publish manifest.

Approval is a separate, explicit step. This script never edits metadata, media
licenses, or asset review status; it only records who approved the plan.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

try:  # direct execution puts scripts/ on sys.path; tests import scripts.*
    from publish_validation import check_manifest
except ImportError:  # pragma: no cover - import style shim
    from scripts.publish_validation import check_manifest

PLAN_APPROVAL_FAILURE = "게시 계획이 승인되지 않았습니다"


def blocking_failures(manifest: dict[str, Any]) -> list[str]:
    """Return failures that approval itself cannot resolve.

    The missing plan approval is expected before this script runs, so it is
    filtered out. Rights and metadata problems are not, so approving over them
    is refused unless the operator passes --force.
    """
    failures = check_manifest(manifest)["failures"]
    return [item for item in failures if not item.startswith(PLAN_APPROVAL_FAILURE)]


def apply_approval(
    manifest: dict[str, Any], *, approver: str, notes: list[str]
) -> dict[str, Any]:
    review = manifest.setdefault("review", {})
    review["status"] = "approved"
    review["approved_by"] = approver
    review["approved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    review.setdefault("notes", []).extend(notes)
    return manifest


def apply_withdrawal(manifest: dict[str, Any], *, reason: str | None) -> dict[str, Any]:
    review = manifest.setdefault("review", {})
    review["status"] = "needs_review"
    review["approved_by"] = None
    review["approved_at"] = None
    if reason:
        review.setdefault("notes", []).append(f"승인 취소: {reason}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--approve", action="store_true")
    group.add_argument("--withdraw", action="store_true")
    parser.add_argument("--by", help="승인자 이름. --approve에 필수")
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--reason", help="--withdraw 사유")
    parser.add_argument(
        "--force",
        action="store_true",
        help="권리·메타데이터 검증 실패를 무시하고 승인 기록만 남긴다",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))

    if args.withdraw:
        apply_withdrawal(manifest, reason=args.reason)
        args.manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Withdrew approval: {args.manifest}")
        return 0

    if not args.by:
        raise SystemExit("--approve에는 --by가 필요합니다")

    blocking = blocking_failures(manifest)
    if blocking and not args.force:
        print("승인할 수 없습니다. 아래 항목을 먼저 해결하세요:")
        for item in blocking:
            print(f"  - {item}")
        print("검증을 무시하고 승인 기록만 남기려면 --force를 쓰세요.")
        return 1

    apply_approval(manifest, approver=args.by, notes=list(args.note))
    if blocking:
        manifest["review"]["notes"].append(
            "--force로 승인됨. 미해결 검증 실패: " + "; ".join(blocking)
        )
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Approved by {args.by}: {args.manifest}")
    if blocking:
        print(f"WARNING: 미해결 검증 실패 {len(blocking)}건이 기록되었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
