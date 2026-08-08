---
name: namuwiki-source-capture
description: Capture context-rich NamuWiki evidence for Korean YouTube Shorts by selecting complete tables for structured facts and complete paragraphs for explanatory claims, using the project's mobile Playwright workflow and preserving provenance. Use when collecting, screenshotting, or documenting NamuWiki sources for a scene.
---

# NamuWiki Source Capture

## Overview

Collect readable, context-rich NamuWiki evidence for a Shorts scene. Choose the
capture boundary from the information shape: preserve a complete table for
structured data, or preserve the complete explanatory paragraph for prose.
Record the page and revision-history provenance, then leave rights approval to
human review.

## Choose the capture context

- Use `table` for measurements, weights, heights, IDs, classifications,
  comparisons, rates, and other values presented in rows and columns. Capture
  the nearest complete table so the title, column headers, and related rows
  remain visible. Never use a numeric cell by itself when the table supplies
  the meaning.
- Use `element` for origin stories, explanations, relationships, theories,
  quotes, and other prose. Capture the entire readable paragraph or list item
  containing the match, not only the matched sentence or keyword.
- Use `auto` by default. The project script selects the nearest visible table
  when the match is inside a table and otherwise selects the smallest readable
  text block containing the match.
- Use a distinctive phrase as `--match`. Do not search for a bare number when
  the page contains several unrelated occurrences; include the unit or a
  nearby unique phrase.

## Execute the project workflow

1. Identify the exact NamuWiki page and the sentence or data row that supports
   the scene's claim.
2. Run the repository capture script from WSL. Use `--context auto` unless the
   intended boundary is known explicitly.

   ```bash
   python3 scripts/capture_namuwiki.py \
     "https://namu.wiki/w/픽시(포켓몬스터)" \
     --match 7.5kg \
     --context auto \
     --segment=12 \
     --manifest=output/manifests/phantom-clefairy-shadow.media.json
   ```

   For an explanatory paragraph, use the full distinctive phrase and force a
   prose block when necessary:

   ```bash
   python3 scripts/capture_namuwiki.py \
     "https://namu.wiki/w/픽시(포켓몬스터)" \
     --match "피카츄가 아니라 삐삐가 마스코트로 내정" \
     --context element \
     --output-dir output/playwright/namuwiki/paragraph-test
   ```

   Add `--segment` and `--manifest` when the capture is ready to become a
   scene candidate; omit them while exploring or visually checking a source.

3. Keep embedded images, video, and iframes hidden by default. Use
   `--include-embedded-media` only when the media itself is intentionally
   being reviewed as a separate candidate; text permission does not
   automatically cover embedded third-party media.
4. Open the resulting PNG and confirm that a viewer can understand the claim
   without returning to the page. For a table, check the title, headers, and
   related rows. For prose, check that the complete paragraph is present and
   not truncated by an ad, navigation block, or unrelated container.
5. Keep the generated metadata JSON with the capture. It must retain the page
   URL, page title, history URL, capture time, match text, context type, and
   table dimensions when applicable.
6. Keep the manifest candidate at `needs_review`. Render the media review
   report and let the human decide whether the source and license are usable.

## Provenance and rights

- Record the original page URL, history URL, capture time, page title, and
  attribution in the candidate manifest.
- Under this project's current noncommercial assumption, treat NamuWiki text
  captures as a CC BY-NC-SA 2.0 KR candidate only after checking the document's
  exclusions and required attribution. Do not treat this assumption as
  approval for commercial use.
- Keep official artwork, screenshots, illustrations, advertisements, and
  embedded media under separate rights review. Do not infer their license from
  the surrounding NamuWiki text.
- Preserve the episode's claim type (`official`, `secondary_reference`, or
  `creative_interpretation`) separately from the capture's source metadata.
  A screenshot proves what the page says; it does not make an unverified claim
  official or factually correct.

## Failure handling

- If no match is found, use a more distinctive phrase, verify the page URL, and
  inspect the current page snapshot before changing the selector logic.
- If a table match produces only a cell, treat it as a bug or a wrong target;
  rerun with `--context table` and inspect the metadata's `context_type` and
  row/column counts.
- If a prose match captures a huge page container, rerun with `--context
  element` and a phrase inside the intended paragraph.
- If the page is blocked by WAF or normal access fails, use the installed
  `insane-search` fallback for access and trace the result. It does not grant
  reuse rights and should not replace provenance review.
- Do not silently generate a replacement image when a capture fails. Mark the
  scene as missing and keep generation behind explicit approval.

## Project integration

- Implementation: `scripts/capture_namuwiki.py`
- Candidate manifest: `output/manifests/*.media.json`
- Human review report: `scripts/render_media_review.py`
- Policy and acquisition order: `references/media-policy.md`
- Local captures and metadata live under `output/playwright/namuwiki/` and
  remain ignored from Git unless the project later decides to version them.

## TODO

- Add an optional paragraph-plus-nearest-heading context mode for sections
  where the heading is required to understand the prose.
- Add a stable section/table locator when NamuWiki's DOM changes make text
  matching ambiguous.
- Add a review-report thumbnail for local paragraph and table captures.
