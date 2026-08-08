# Local TTS provider comparison

Test date: 2026-08-08

## Test setup

- OS/runtime: WSL Ubuntu 24.04, Python 3.11 TTS environment
- GPU visible to Windows: GeForce MX450, 2 GB VRAM, driver 452.56
- Test episode: `output/episodes/phantom-clefairy-shadow.json`
- Test text: the first three scene narrations, unless noted otherwise

## Observations

### Supertonic 3

- Provider: `supertonic`
- Voice: `F1`
- Runtime: CPU
- Output: 44.1 kHz WAV
- Scene durations: 6.618s, 3.971s, 6.409s
- Generation times: 5.29s, 3.01s, 5.77s
- Full 15-scene total at speed 1.4: 67.718s
- Full 15-scene total at speed 1.5: 64.891s
- Result: practical for the production pipeline; actual speech duration is available and generation is fast enough for batch work.

### Qwen3-TTS 0.6B

- Provider: `qwen3_tts`
- Speaker: `Sohee`
- Runtime: CPU fallback; PyTorch did not expose CUDA to WSL
- Output: 24 kHz WAV
- Generated scenes: 1 and 2
- Scene durations: 7.280s and 5.120s
- Observed runtime: approximately 5m47s to the first scene and 1m40s for the second after model loading.
- Result: generation works, but it is too slow for routine 15-scene production on this machine without a usable CUDA setup.

## Current decision

Use Supertonic 3 as the default local provider. Keep Qwen3-TTS as an optional quality/reference provider until the NVIDIA driver and CUDA path are updated or a stronger GPU is available. The accepted episode duration is 50-70 seconds.

The Supertonic model uses the OpenRAIL-M license, so the upload pipeline should include an intelligible disclosure that the narration is AI-generated.
