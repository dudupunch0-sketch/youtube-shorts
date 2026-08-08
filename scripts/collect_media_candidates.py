#!/usr/bin/env python3
"""Collect web-media candidates and provenance for a scene media manifest."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


USER_AGENT = "youtube-shorts-media-collector/0.1 (+local review workflow)"
OPENVERSE_URL = "https://api.openverse.org/v1/images/"
WIKIMEDIA_URL = "https://commons.wikimedia.org/w/api.php"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def fetch_json(url: str, params: dict[str, Any], timeout: float) -> tuple[dict[str, Any] | None, str | None]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as error:
        return None, f"http_{error.code}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return None, type(error).__name__


def openverse_candidates(query: str, limit: int, timeout: float) -> tuple[list[dict[str, Any]], str | None]:
    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    # Commercial results are the least risky starting point. If none exist,
    # collect an unfiltered pass for human review rather than silently inventing assets.
    passes = [{"license_type": "commercial"}, {}]
    for license_filter in passes:
        params = {"q": query, "page_size": limit, "mature": "false", **license_filter}
        payload, error = fetch_json(OPENVERSE_URL, params, timeout)
        if error:
            errors.append(error)
            continue
        for item in (payload or {}).get("results", []):
            candidates.append(
                {
                    "provider": "openverse",
                    "query": query,
                    "title": item.get("title"),
                    "asset_url": item.get("url"),
                    "thumbnail_url": item.get("thumbnail"),
                    "landing_url": item.get("foreign_landing_url"),
                    "license": item.get("license"),
                    "license_url": item.get("license_url"),
                    "creator": item.get("creator"),
                    "creator_url": item.get("creator_url"),
                    "attribution": item.get("attribution"),
                    "review_status": "needs_review",
                }
            )
        if candidates:
            break
    return candidates, ", ".join(sorted(set(errors))) or None


def commons_candidates(query: str, limit: int, timeout: float) -> tuple[list[dict[str, Any]], str | None]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size",
        "format": "json",
        "formatversion": 2,
    }
    payload, error = fetch_json(WIKIMEDIA_URL, params, timeout)
    if error:
        return [], error
    results = []
    for item in (payload or {}).get("query", {}).get("pages", []):
        info = (item.get("imageinfo") or [{}])[0]
        if not str(info.get("mime", "")).startswith("image/"):
            continue
        metadata = info.get("extmetadata") or {}
        title = item.get("title", "")
        landing_url = "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        results.append(
            {
                "provider": "wikimedia_commons",
                "query": query,
                "title": title,
                "asset_url": info.get("url"),
                "thumbnail_url": info.get("thumburl") or info.get("url"),
                "landing_url": landing_url,
                "license": (metadata.get("LicenseShortName") or {}).get("value"),
                "license_url": (metadata.get("LicenseUrl") or {}).get("value"),
                "creator": (metadata.get("Artist") or {}).get("value"),
                "creator_url": None,
                "attribution": None,
                "review_status": "needs_review",
            }
        )
    return results, None


def dedupe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for candidate in candidates:
        key = candidate.get("asset_url") or candidate.get("landing_url")
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


STOP_WORDS = {
    "a", "an", "and", "as", "background", "black", "clean", "concept", "dramatic",
    "entry", "for", "graphic", "idea", "in", "of", "on", "original", "pokemon",
    "reveal", "side", "style", "the", "to", "versus", "with",
}


def query_variants(query: str) -> list[str]:
    """Make provider-friendly short queries from a scene description."""
    words = re.findall(r"[A-Za-z0-9.]+", query)
    meaningful = [word for word in words if word.lower() not in STOP_WORDS]
    variants = [query.strip()]
    if meaningful:
        variants.append(" ".join(meaningful[:4]))
        variants.append(" ".join(meaningful[:2]))
    return list(dict.fromkeys(value for value in variants if value))


def collect_segment(
    segment: dict[str, Any], limit_per_provider: int, timeout: float
) -> tuple[int, list[dict[str, Any]], list[str]]:
    queries = segment.get("search", {}).get("queries") or []
    if not queries:
        return int(segment["index"]), [], ["no_query"]

    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    for variant in query_variants(queries[0])[:2]:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as provider_pool:
            futures = [
                provider_pool.submit(collector, variant, limit_per_provider, timeout)
                for collector in (openverse_candidates, commons_candidates)
            ]
            for collector, future in zip((openverse_candidates, commons_candidates), futures):
                found, error = future.result()
                candidates.extend(found)
                if error:
                    errors.append(f"{collector.__name__}({variant}): {error}")
        if len(candidates) >= limit_per_provider * 2:
            break
    return int(segment["index"]), dedupe(candidates), errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--limit-per-provider", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    total_candidates = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as segment_pool:
        futures = [
            segment_pool.submit(collect_segment, segment, args.limit_per_provider, args.timeout)
            for segment in segments
        ]
        collected = [future.result() for future in futures]

    for segment, (_, candidates, errors) in zip(segments, collected):
        search = segment.setdefault("search", {})
        segment["candidates"] = candidates
        search["last_run_at"] = now()
        search["errors"] = errors
        search["status"] = "collected" if candidates else ("blocked_or_failed" if errors else "no_results")
        segment["asset"]["status"] = "pending"
        segment["asset"]["mode"] = None
        segment["asset"]["path"] = None
        segment["asset"]["review_notes"] = "Candidates collected; select and verify license manually before approval."
        total_candidates += len(candidates)

    data["strategy"] = "collect_then_manual_review"
    data["generation_fallback"] = "manual_only"
    data["collected_at"] = now()
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {total_candidates} candidates across {len(data.get('segments', []))} segments")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
