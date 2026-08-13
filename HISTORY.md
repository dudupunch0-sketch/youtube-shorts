# Development History

This file records project decisions, experiments, and known limitations. It is a development log, not a user-facing release changelog.

## 2026-08-13 — Publish layer stage 1

### Context

Evaluated `block/buzz` as a way to hand off content production and channel operations. It
is a Nostr-based self-hosted collaboration workspace (channels, agents-as-members, YAML
workflows, signed audit log), not a content tool. It produces no script, audio, video, or
upload. Its genuinely relevant features are frame-anchored video comments and
reaction-triggered approval workflows, but the approval gates are still marked in-progress
upstream, and the project has one participant, so there is no second approver for the
audit trail to record. Decision: do not integrate. Revisit if a second reviewer joins and
the approval gates ship; only pipeline steps 4 and 6 would need to move.

### Publish design and implementation

- Added `docs/youtube-publish-design.md` describing the stage after final render.
- Implemented stage 1, which needs no network or OAuth: `scripts/plan_publish.py`,
  `scripts/render_publish_review.py`, `scripts/approve_publish.py`,
  `scripts/validate_publish.py`, plus the shared modules `scripts/publish_licensing.py`,
  `scripts/publish_metadata.py`, and `scripts/publish_validation.py`.
- Added the `publish` block to `config/pipeline.json`, YouTube OAuth paths to
  `.env.example`, and gitignore entries for the credential files. Publish manifests and
  review sheets are whitelisted in `.gitignore` like media manifests.
- Added 17 unit tests. `make test` now runs 21.

### Decisions

- The channel has no monetization plan, so `commercial_use` is `false`. It relaxes the
  NonCommercial clause only. Unknown licenses, unrecognized license strings, NoDerivatives,
  and franchise official artwork stay blocked.
- `status.containsSyntheticMedia` is writable in `videos.insert` (added to the Data API on
  2024-10-30), so the AI-voice disclosure required by the TTS policy is automated rather
  than left to Studio. Both the API field and the description sentence are validated.
- The description limit is 5000 UTF-8 bytes, not characters. Korean is three bytes per
  character, so the practical limit is about 1,660 characters. Validating characters would
  let descriptions be silently truncated.
- `videos.insert` has its own quota bucket at 100 calls per day, separate from the shared
  10,000-unit pool, so quota is not a constraint at this channel's scale.
- Uploads will be pinned to `privacyStatus: private`; promotion is a separate step.

### Applying it to the Phantom episode

- 7 distinct sources across 15 scenes; 4 are license-blocked. Three record `unknown` and
  one is `by-nc-nd`. The three NamuWiki captures pass now that NC is relaxed, but carry
  ShareAlike warnings.
- 7 scenes (2, 3, 7, 10, 11, 14, 15) have no selected asset at all.
- Two defects were found by running the planner on real data and then fixed: NamuWiki
  landing URLs differing only in percent-encoding of `)` produced duplicate attribution
  lines, and collector-recorded attribution strings dropped the scene prefix.
- The monetization decision alone does not make this episode publishable.

### Where to pick this up

In order. Steps 1-3 need no new accounts or credentials.

1. **Replace the four license-blocked sources.** Scenes 1 and 4 use two `unknown`
   pokemondb artworks, scene 9 uses an `unknown` dexerto page, and scene 5 uses a
   `by-nc-nd` asset. Prefer Openverse, Wikimedia Commons, or an official source page with
   a recorded license. Re-run `plan_publish.py` after each change; the license verdict is
   recomputed from the media manifest every time.
2. **Fill or resolve the seven empty scenes** (2, 3, 7, 10, 11, 14, 15). Either collect
   candidates or decide they stay text cards. A text card still needs a manifest entry, or
   `check_licensing` reports the scene as missing.
3. **Render final and validate for real.** Once every selected asset is `approved`, render
   without `--draft`, then run `validate_publish.py` *without* `--skip-render`. The render
   checks (draft flag, 50-70s, 1080x1920, MP4 present) have never run against a real final
   render, only against a synthetic fixture.
4. **Publish stage 2.** Requires a Google Cloud project and an OAuth desktop client, which
   is a user action, not a code change. Scopes and the WSL consent flow are in section 6 of
   `docs/youtube-publish-design.md`. Scripts to add: `authorize_youtube.py`,
   `upload_youtube.py`.
5. **Stages 3-4.** `promote_youtube.py` for public/scheduled release, then
   `fetch_youtube_stats.py`.

Config-only decisions still open, all in `config/pipeline.json` under `publish`:
`category_id` (24), post-upload default (private, manual promotion),
`selfDeclaredMadeForKids` (false), and the description `footer` (empty).

Not planned: `block/buzz` integration. See the context note at the top of this entry.

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
- Implement publish stage 2 and beyond: OAuth authorization, private upload, promotion to public or scheduled, and stats collection.
