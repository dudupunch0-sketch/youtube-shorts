# Local TTS provider comparison

Test date: 2026-08-08

## Test setup

- OS/runtime: WSL Ubuntu 24.04, Python 3.11 TTS environment
- GPU visible to Windows/WSL: GeForce MX450, 2 GB VRAM, Windows driver 591.86, CUDA 13.1 bridge
- GPU compute capability: 7.5 (Turing)
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
- Full 15-scene generation at speed 1.4: 74.914s generation time; 67.718s timeline
- Full 15-scene generation at speed 1.5: 66.928s generation time; 64.891s timeline; 59.281s speech
- Result: practical for the production pipeline; actual speech duration is available and generation is fast enough for batch work.

### Qwen3-TTS 0.6B

- Provider: `qwen3_tts`
- Speaker: `Sohee`
- Runtime: CPU valid-output test, then WSL CUDA GPU tests after driver update
- Output: 24 kHz WAV
- Generated scenes: 1 and 2
- Scene durations: 7.280s and 5.120s
- Observed runtime: approximately 5m47s to the first scene and 1m40s for the second after model loading.
- Normal FP16 GPU sampling failed with a CUDA device-side assertion caused by invalid sampling probabilities.
- A deterministic GPU smoke test completed in approximately 114.6s but produced a constant-value `-1.0` WAV, so the file was silent and invalid.
- Result: CPU output sounded better in listening tests, but Qwen is currently too slow on CPU and invalid on the tested GPU path for routine production.

## Current decision

Use Supertonic 3 as the default local provider. Keep Qwen3-TTS as the preferred quality/reference provider, but do not use its current silent GPU smoke-test output. Revisit Qwen as a production provider only after valid non-silent GPU output and acceptable generation speed are confirmed. The accepted episode duration is 50-70 seconds.

The Supertonic model uses the OpenRAIL-M license, so the upload pipeline should include an intelligible disclosure that the narration is AI-generated.
