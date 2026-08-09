# Development History

This file records project decisions, experiments, and known limitations. It is a development log, not a user-facing release changelog.

## 2026-08-08 — Search fallback installed

- Installed the public `insane-search-codex` package, version 0.8.2, from `fivetaku/gptaku-plugins-codex`.
- Installed its Python dependencies in an isolated skill-local virtual environment so the WSL system Python remains unchanged.
- Intended role: fallback for blocked, WAF-protected, or failed source URLs after ordinary search/API access fails.
- Verification: `https://example.com` returned `strong_ok` through the `curl_cffi` probe path.
- The plugin smoke test passed 6 of 8 checks. One selector test and one external `httpbin` test failed in this environment; the core benign URL path passed.
- The skill improves access only. It does not replace license verification or media attribution.

## 2026-08-08 — First media implementation

- Approved the first implementation scope: collect web image/video candidates per scene, keep 12-18 scene support, and leave license decisions to human review.
- Added `references/media-policy.md` with acquisition order, manual-review gates, generated-asset constraints, and provenance fields.
- Added `scripts/plan_media.py`, `scripts/collect_media_candidates.py`, `scripts/import_media_candidates.py`, and `scripts/validate_media_manifest.py`.
- Added `scripts/render_media_review.py`, which creates a clickable scene-by-scene review sheet instead of silently approving a source.
- Added `full_frame` and `split_2up` visual layouts, multi-asset provenance fields, a local two-up preview, and a v1-to-v2 manifest migrator.
- Added mobile NamuWiki text capture with Playwright/Chromium. The Phantom episode now has captures for the shadow classification, Gengar weight, Clefable weight, Clefairy weight, and the fan-theory paragraph; embedded media is hidden by default.
- The first episode manifest now records 10 unapproved candidates across the 15 scenes. The candidates include public-index results and manually imported web-image search results; their licenses remain explicitly `unknown` where they were not verified.
- Validation passed in collection mode: `0/15 approved`, `15 awaiting review`, `10 collected candidates`.
- The public APIs also returned timeouts and HTTP 429 rate limits for some scene queries. Those scenes remain visibly marked as missing/failed in the review sheet rather than being filled with generated images.
- Image generation was tested during implementation but is not part of the accepted media output because it is costly and does not match the desired source-collection workflow. Existing generated files remain local and unreferenced.
- `insane-search` was not invoked for this episode because ordinary API access did not encounter a blocked URL. It remains installed as the blocked-access fallback.

## 2026-08-09 — Contextual NamuWiki captures

- Updated `scripts/capture_namuwiki.py` so `--context auto` captures the nearest complete table when a match is inside a table, preserving the title, headers, and related rows.
- Recaptured the Phantom episode's numeric NamuWiki candidates for segments 8, 9, and 12. Each now records a 6-row × 5-column table context and updates the existing candidate in place.
- Added `capture_context`, row/column counts, and the context mode to the media review report.
- Added the reusable `skills/namuwiki-source-capture/` project skill, documenting when to capture a complete table versus a complete explanatory paragraph and how to retain provenance.
- Improved prose capture for NamuWiki's nested `div` layout by extracting the matching paragraph from larger containers and hiding fixed/sticky page controls. Verified the attached-style paragraph capture and the segment 12 table capture visually.

## 2026-08-08 — TTS comparison closed

### Context

- Machine GPU: NVIDIA GeForce MX450, 2 GB VRAM.
- Windows NVIDIA driver updated from 452.56 to 591.86.
- WSL2 CUDA bridge now works. WSL reports the MX450 and CUDA 13.1.
- Qwen environment uses PyTorch 2.13.0+cu130 and sees one CUDA device.

### Supertonic 3

- Provider: local `supertonic`, voice `F1`, CPU.
- Full 15-scene test at speed 1.5:
  - generation time: 66.928 seconds;
  - speech duration: 59.281 seconds;
  - planned timeline: 64.891 seconds.
- Result: valid, pleasant enough, fast, and suitable for routine batch generation.

### Qwen3-TTS 0.6B

- Provider: local `qwen3_tts`, speaker `Sohee`, 24 kHz WAV.
- CPU test generated valid audio, and the listening result was preferred over Supertonic for naturalness.
- CPU timing was approximately 5 minutes 47 seconds for the first scene and 1 minute 40 seconds for the second scene after model loading. A full 15-scene CPU run was not completed.
- After the driver update, normal FP16 GPU sampling still failed with a CUDA device-side assertion caused by invalid sampling probabilities.
- A deterministic GPU smoke test completed in about 114.6 seconds, but its WAV contained a constant `-1.0` sample value and was silent. It is not a valid production result.

### Decision

The TTS comparison is closed for now. Qwen is recorded as the quality/reference provider. Supertonic 3 remains the configured production default and practical fallback until Qwen GPU output is both valid and operationally fast. Do not use the silent Qwen GPU artifact.

## 2026-08-08 — Timing policy finalized

- The episode target remains 60 seconds.
- The accepted total duration is flexible: 50-70 seconds.
- The recommended structure is 12-18 segments, usually 2.5-5 seconds each.
- Timing manifests record actual speech duration, planned duration, timeline duration, and generation time.

## 2026-08-09 — Presentation, audio validation, and draft video pipeline

- Added `scripts/plan_presentation.py` with stable candidate IDs, automatic layout recommendations, per-scene overrides, confidence/reason metadata, and compatibility support for the old `split_2up` name.
- Added `split_2up_left_right`, `split_2up_top_bottom`, and `sequence` layouts. Sequence scenes support restrained `fade`, `slide_left`, `slide_up`, and `cut` transitions with consecutive-repeat avoidance.
- Recorded the Phantom episode's requested presentation overrides in `config/presentation/phantom-clefairy-shadow.json`. Scene 5 remains automatic and keeps its candidate shortage/review state visible.
- Added local WAV validation for finite samples, non-silence, constant-signal detection, sample rate, duration, peak, and RMS. The 15-scene Supertonic F1 run passed all checks.
- Added measured-duration WebVTT captions and a Pillow/imageio-ffmpeg 9:16 compositor. The current draft rendered at 63.321 seconds and passed geometry, duration, and audio validation.
- Added a dependency-free `make test` unittest suite for presentation recommendation, stable candidate IDs, and silent/non-silent WAV behavior.
- Draft mode intentionally permits `needs_review` assets and missing-candidate text cards for visual inspection. Final rendering remains blocked until the human chooses and approves every source and confirms attribution/license handling.
- NamuWiki evidence captures now default to preserving the complete table or paragraph context in the vertical render (`contain`) instead of cropping the sides.

## Earlier project milestones

- Added concept registry and the initial fictional-media lore concept.
- Added reference-Shorts style profiling without copying source videos.
- Added script generation paths for ChatGPT/Codex-style prompting, Claude Code, and API providers.
- Added scene-level local TTS generation and an ElevenLabs API fallback.
- Added the first Phantom/Clefairy shadow example episode for end-to-end testing.

## Open work

- Add a real media-search adapter that stores landing pages, licenses, creators, and attribution for sourced assets.
- Complete candidate coverage, human source review, attribution decisions, and final approved render.
- Add generation-time provider fallback handling, not only model-load failure handling.
