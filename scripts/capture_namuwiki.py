#!/usr/bin/env python3
"""Capture a contextual NamuWiki text or table block in a mobile viewport."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


CLI = ["npx", "--yes", "--package", "@playwright/cli", "playwright-cli"]
CAPTURE_SELECTOR = '[data-codex-capture-root="true"]'


def run_cli(session: str, *args: str, timeout: int) -> dict[str, Any]:
    command = [*CLI, "--session", session, *args, "--json"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "Playwright CLI failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid Playwright CLI JSON: {result.stdout[:500]}") from error


def eval_page(session: str, function: str, timeout: int) -> dict[str, Any]:
    response = run_cli(session, "eval", function, timeout=timeout)
    result = response.get("result")
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"value": result}
    return result or {}


def source_url_for_page(page: str) -> str:
    if page.startswith("http://") or page.startswith("https://"):
        return page
    return "https://namu.wiki/w/" + quote(page, safe="()")


def add_manifest_candidate(
    manifest_path: Path,
    segment_index: int,
    metadata: dict[str, Any],
    capture_path: str,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    segment = next((item for item in manifest["segments"] if item["index"] == segment_index), None)
    if segment is None:
        raise SystemExit(f"segment not found: {segment_index}")
    candidate = {
        "provider": "namuwiki_capture",
        "query": metadata.get("match"),
        "title": metadata.get("page_title") or metadata.get("page_url"),
        "asset_url": metadata.get("page_url"),
        "thumbnail_url": None,
        "landing_url": metadata.get("page_url"),
        "license": "CC BY-NC-SA 2.0 KR (text; verify document and media exclusions)",
        "license_url": "https://creativecommons.org/licenses/by-nc-sa/2.0/kr/",
        "creator": "NamuWiki contributors; see page history",
        "creator_url": metadata.get("history_url"),
        "attribution": f"나무위키 '{metadata.get('page_title')}' 문서 및 문서 역사: {metadata.get('history_url') or metadata.get('page_url')}",
        "review_status": "needs_review",
        "content_type": "text_excerpt_capture",
        "capture_path": capture_path,
        "capture_metadata_path": capture_path.rsplit(".", 1)[0] + ".json",
        "capture_selector": metadata.get("selector"),
        "capture_match": metadata.get("match"),
        "capture_context": metadata.get("context_type"),
        "context_rows": metadata.get("context_rows"),
        "context_columns": metadata.get("context_columns"),
        "third_party_media_present": metadata.get("third_party_media_present", False),
        "review_notes": "Noncommercial NamuWiki text capture; verify attribution, revision, and embedded media separately.",
    }
    existing = next(
        (item for item in segment.get("candidates", []) if item.get("capture_path") == capture_path),
        None,
    )
    if existing is None:
        segment.setdefault("candidates", []).append(candidate)
    else:
        existing.update(candidate)
    segment.setdefault("search", {})["status"] = "collected"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", help="NamuWiki page name or full URL")
    parser.add_argument("--match", required=True, nargs="+", help="Text contained in the block to capture")
    parser.add_argument(
        "--include-embedded-media",
        action="store_true",
        help="Keep images, videos, and iframes inside the captured block",
    )
    parser.add_argument(
        "--context",
        choices=("auto", "table", "element"),
        default="auto",
        help="Capture context mode; auto captures the nearest full table when the match is in a table",
    )
    parser.add_argument("--segment", type=int)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("output/playwright/namuwiki"))
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    if args.segment is not None and args.manifest is None:
        raise SystemExit("--manifest is required when --segment is provided")

    match = " ".join(args.match)
    page_url = source_url_for_page(args.page)
    slug = f"segment-{args.segment:03d}" if args.segment is not None else "capture"
    session = f"namuwiki-{slug}"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = args.output_dir / f"{slug}.png"
    metadata_path = args.output_dir / f"{slug}.json"

    run_cli(session, "open", page_url, "--browser", "chromium", "--mobile", timeout=args.timeout)
    run_cli(session, "resize", "390", "844", timeout=args.timeout)
    match_json = json.dumps(match, ensure_ascii=False)
    context_json = json.dumps(args.context, ensure_ascii=False)
    media_policy = "" if args.include_embedded_media else "target.querySelectorAll('img, video, iframe').forEach(node => node.style.display = 'none');"
    find_block = f"""() => {{
      const needle = {match_json};
      const contextMode = {context_json};
      const isVisible = node => {{
        const style = getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      }};
      document.querySelectorAll('[data-codex-capture-root="true"]').forEach(node => node.removeAttribute('data-codex-capture-root'));
      const nodes = Array.from(document.querySelectorAll('p, li, td, blockquote, h2, h3, h4, div'))
        .filter(node => isVisible(node) && (node.innerText || '').includes(needle))
        .sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
      const blockTags = new Set(['P', 'LI', 'TD', 'TH', 'BLOCKQUOTE', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'DIV']);
      const leafBlocks = nodes.filter(node => !Array.from(node.children).some(child =>
        blockTags.has(child.tagName) && (child.innerText || '').includes(needle)
      ));
      const matchNode = nodes.find(node => ['TD', 'TH'].includes(node.tagName)) || leafBlocks[0] || nodes[0];
      if (!matchNode) return {{ok: false, page_url: location.href, match: needle}};
      let target = matchNode;
      let contextType = 'element';
      let contextNote = 'Captured the smallest readable text block containing the match.';
      let matchExcerpt = (matchNode.innerText || '').trim();
      const nearestTable = matchNode.closest('table');
      if ((contextMode === 'auto' || contextMode === 'table') && nearestTable && isVisible(nearestTable)) {{
        target = nearestTable;
        contextType = 'table';
        contextNote = 'Captured the nearest complete table so the title, headers, and related rows remain visible.';
      }}
      if (contextMode === 'table' && contextType !== 'table') {{
        return {{ok: false, page_url: location.href, match: needle, reason: 'match is not inside a visible table'}};
      }}
      if (contextType === 'element') {{
        const paragraphs = matchExcerpt.split(/\\n\\s*\\n/).map(value => value.trim()).filter(Boolean);
        const matchedParagraph = paragraphs.find(value => value.includes(needle));
        if (matchedParagraph && paragraphs.length > 1) {{
          const wrapper = document.createElement('div');
          wrapper.style.cssText = 'box-sizing:border-box; max-width:calc(100vw - 24px); padding:12px; background:#fff; color:#222; font-family:inherit; font-size:18px; line-height:1.7; white-space:pre-wrap; overflow-wrap:anywhere;';
          wrapper.textContent = matchedParagraph;
          document.body.appendChild(wrapper);
          target = wrapper;
          matchExcerpt = matchedParagraph;
          contextNote = 'Extracted the complete paragraph containing the match from a larger text container.';
        }}
      }}
      const floatingNodes = Array.from(document.querySelectorAll('body *')).filter(node => {{
        if (node === target || target.contains(node)) return false;
        const position = getComputedStyle(node).position;
        return position === 'fixed' || position === 'sticky';
      }});
      floatingNodes.forEach(node => node.style.setProperty('display', 'none', 'important'));
      const embeddedMediaCount = target.querySelectorAll('img, video, iframe').length;
      {media_policy}
      target.setAttribute('data-codex-capture-root', 'true');
      target.scrollIntoView({{block: 'center', inline: 'nearest'}});
      const title = document.querySelector('h1')?.innerText?.trim() || document.title;
      const historyLink = Array.from(document.querySelectorAll('a')).find(a => (a.innerText || '').trim() === '역사');
      const rows = contextType === 'table' ? Array.from(target.rows || []).map(row => Array.from(row.cells || []).map(cell => (cell.innerText || '').trim())) : [];
      return {{
        ok: true,
        selector: '{CAPTURE_SELECTOR}',
        page_url: location.href,
        page_title: title,
        history_url: historyLink ? new URL(historyLink.getAttribute('href'), location.href).href : null,
        match: needle,
        text_excerpt: (target.innerText || '').trim(),
        match_excerpt: matchExcerpt,
        context_type: contextType,
        context_rows: rows.length,
        context_columns: rows.reduce((max, row) => Math.max(max, row.length), 0),
        context_note: contextNote,
        floating_ui_hidden: floatingNodes.length,
        third_party_media_present: embeddedMediaCount > 0,
        embedded_media_hidden: {str(not args.include_embedded_media).lower()}
      }};
    }}"""
    metadata = eval_page(session, find_block, args.timeout)
    if not metadata.get("ok"):
        raise SystemExit(f"could not find capture text: {match}")
    run_cli(
        session,
        "screenshot",
        CAPTURE_SELECTOR,
        "--filename",
        str(screenshot_path.resolve()),
        "--hires",
        timeout=args.timeout,
    )
    metadata.update(
        {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "viewport_css": {"width": 390, "height": 844},
            "mobile_emulation": True,
            "screenshot_path": screenshot_path.resolve().as_posix(),
        }
    )
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.manifest and args.segment is not None:
        repo_root = args.manifest.resolve().parent.parent.parent
        capture_rel = screenshot_path.resolve().relative_to(repo_root).as_posix()
        add_manifest_candidate(args.manifest.resolve(), args.segment, metadata, capture_rel)
    print(f"Captured NamuWiki block: {screenshot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
