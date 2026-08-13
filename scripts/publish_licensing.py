#!/usr/bin/env python3
"""Classify media licenses for the publish gate.

Recorded licenses are free text written by collectors and humans, so exact
string matching is not usable. This module extracts license traits from the
recorded value and turns them into an allow/block decision plus the conditions
a human still has to satisfy.
"""

from __future__ import annotations

import re
from typing import Any

PUBLIC_DOMAIN_PATTERNS = (
    "public domain",
    "publicdomain",
    "cc0",
    "pd-",
    "no known copyright",
    "own work",
    "own_work",
)

# Either an explicit "cc"/"creative commons" token, or a bare clause code such
# as "by-nc-sa". A lone "by" is not enough; prose like "used by permission"
# must not be read as a Creative Commons license.
CC_PATTERN = re.compile(r"\b(?:cc|creative commons)\b|(?<![a-z-])by(?:-(?:nc|nd|sa))+(?![a-z])")

UNKNOWN_VALUES = ("", "unknown", "none", "null", "n/a", "미기록", "미확인")


def normalize_license(value: Any) -> str:
    """Lowercase and collapse a recorded license string."""
    if value is None:
        return ""
    return " ".join(str(value).split()).strip().lower()


def license_traits(value: Any) -> dict[str, Any]:
    """Extract the reuse-relevant traits of a recorded license string."""
    normalized = normalize_license(value)
    traits = {
        "raw": None if value is None else str(value),
        "normalized": normalized,
        "unknown": normalized in UNKNOWN_VALUES,
        "public_domain": False,
        "creative_commons": False,
        "noncommercial": False,
        "no_derivatives": False,
        "share_alike": False,
        "attribution_required": False,
    }
    if traits["unknown"]:
        return traits
    if any(pattern in normalized for pattern in PUBLIC_DOMAIN_PATTERNS):
        traits["public_domain"] = True
        return traits
    if CC_PATTERN.search(normalized):
        traits["creative_commons"] = True
        traits["attribution_required"] = True
        # Match the clause tokens only inside license codes such as
        # "cc by-nc-sa 2.0 kr" or a bare "by-nc-nd", never inside prose.
        for code in re.findall(r"by(?:-[a-z]{2}){0,3}", normalized):
            parts = code.split("-")[1:]
            traits["noncommercial"] = traits["noncommercial"] or "nc" in parts
            traits["no_derivatives"] = traits["no_derivatives"] or "nd" in parts
            traits["share_alike"] = traits["share_alike"] or "sa" in parts
    return traits


def classify_license(value: Any, *, commercial_use: bool) -> dict[str, Any]:
    """Decide whether a recorded license may be published on this channel.

    ``commercial_use`` reflects whether the channel is monetized. It only
    relaxes the NonCommercial clause. It never relaxes an unknown license, an
    unrecognized license string, or a NoDerivatives clause.
    """
    traits = license_traits(value)
    result: dict[str, Any] = {
        "decision": "block",
        "reason": "",
        "conditions": [],
        "commercial_use_allowed": None,
        "traits": traits,
    }

    if traits["unknown"]:
        result["reason"] = "라이선스가 기록되지 않았습니다. 사용 전 권리를 확인해야 합니다."
        return result

    if not traits["public_domain"] and not traits["creative_commons"]:
        result["reason"] = (
            f"인식할 수 없는 라이선스 표기입니다: {traits['normalized']!r}. "
            "재사용 조건을 확인해 표기를 정규화하세요."
        )
        return result

    if traits["no_derivatives"]:
        result["reason"] = (
            "NoDerivatives(ND) 조건입니다. 자막·합성·편집이 들어가는 영상에 사용할 수 없습니다."
        )
        return result

    result["commercial_use_allowed"] = not traits["noncommercial"]

    if traits["noncommercial"] and commercial_use:
        result["reason"] = (
            "NonCommercial(NC) 조건인데 채널이 상업적 이용으로 설정되어 있습니다. "
            "수익화를 끄거나 다른 출처로 교체하세요."
        )
        return result

    conditions = []
    if traits["noncommercial"]:
        conditions.append("비영리 채널 전제를 유지해야 합니다. 수익화를 켜면 재검토가 필요합니다.")
    if traits["attribution_required"]:
        conditions.append("설명문에 제작자·라이선스·원본 링크를 표기해야 합니다.")
    if traits["share_alike"]:
        conditions.append("ShareAlike(SA) 조건입니다. 영상에 적용될 범위를 사람이 확인해야 합니다.")

    result["decision"] = "allow"
    result["reason"] = "재사용 가능한 라이선스로 분류되었습니다."
    result["conditions"] = conditions
    return result
