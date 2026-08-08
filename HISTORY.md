# Development History

This file records project decisions, experiments, and known limitations. It is a development log, not a user-facing release changelog.

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

## Earlier project milestones

- Added concept registry and the initial fictional-media lore concept.
- Added reference-Shorts style profiling without copying source videos.
- Added script generation paths for ChatGPT/Codex-style prompting, Claude Code, and API providers.
- Added scene-level local TTS generation and an ElevenLabs API fallback.
- Added the first Phantom/Clefairy shadow example episode for end-to-end testing.

## Open work

- Search or generate visuals for every scene and preserve attribution/provenance.
- Assemble captions, audio, visuals, and transitions into the final 9:16 video.
- Add automated WAV non-silence validation and generation-time fallback handling.
