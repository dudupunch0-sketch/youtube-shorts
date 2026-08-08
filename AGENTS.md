# YouTube Shorts Automation Project Instructions

## Project goal

Build a repeatable pipeline for Korean YouTube Shorts about fictional-media lore and other reference-backed domain facts.

## Canonical episode pipeline

1. Select an explicit concept from `concepts/registry.json`.
2. Expand a short topic or premise into a Korean script using the active concept's style profile.
3. Produce 12-18 short narration segments. The target is 60 seconds, with an accepted total timeline of 50-70 seconds.
4. Find or generate one visual asset per segment. Record source URL, license, creator, or generation provenance.
5. Generate scene audio, captions, and the final 9:16 video.
6. Validate the episode, timing manifest, media provenance, and final render before publishing.

## Content and references

- Prefer official settings, primary references, or clearly identified secondary references.
- Creative interpretation is allowed for fictional works, but label interpretation as interpretation.
- Do not copy the supplied Shorts. Reuse only abstract pacing, structure, and presentation patterns recorded in `references/`.
- Keep one idea per segment and include a hook and a conclusion.

## TTS policy (decision recorded 2026-08-08)

- Qwen3-TTS 0.6B (`Sohee`) is the preferred quality/reference voice based on listening tests.
- Supertonic 3 (`F1`) is the production-safe local provider and remains the configured default because it is fast, stable, and generated valid audio on this machine.
- Qwen CPU audio was pleasant but too slow for routine 15-scene production. Normal Qwen FP16 GPU sampling failed on the MX450, and a deterministic GPU smoke test produced an invalid constant-value WAV. Do not treat that GPU output as usable.
- Do not reopen the provider comparison unless explicitly requested. If Qwen is selected later, verify that the output is finite, non-silent, and audibly valid before using it.
- Keep ElevenLabs as the external API fallback.
- Supertonic narration must include an intelligible AI-generated voice disclosure in the upload pipeline.

## Audio validation

Before an audio file enters the video pipeline, check its sample rate, duration, finite sample values, non-zero signal, and a basic peak/RMS range. A file that opens but is silent or has a constant sample value is invalid.

## Environment rules

- Run project commands in WSL Ubuntu. Do not install a Linux NVIDIA driver inside WSL; the Windows NVIDIA driver supplies the WSL CUDA bridge.
- Keep model caches, virtual environments, generated audio, and manifests out of Git unless they are intentionally documented artifacts.
- Use the existing scripts and configuration before adding a new provider or pipeline path.

## Current TODO

- Complete asset search/generation and attribution handling.
- Complete caption timing and 9:16 video assembly.
- Add automated audio non-silence validation to the local TTS script.
- Add a safe provider fallback policy for generation-time failures, not only model-load failures.
- Expand the style skill TODOs using additional reference Shorts when the channel direction is finalized.
