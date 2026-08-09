#!/usr/bin/env python3
"""Generate scene-level audio with local Supertonic 3 or Qwen3-TTS."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Optional

from audio_validation import AudioValidationError, validate_wav


class LocalTtsError(RuntimeError):
    """Raised when a local TTS provider cannot be loaded or run."""


def slugify(value: str) -> str:
    result = []
    for char in value.lower().strip():
        if char.isalnum() or char in "-_":
            result.append(char)
        elif char in " _":
            result.append("-")
    return "".join(result).strip("-") or "episode"


def load_episode(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise LocalTtsError(f"episode file not found: {path}")
    try:
        episode = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LocalTtsError(f"invalid episode JSON: {error}") from error
    if not isinstance(episode, dict) or not episode.get("segments"):
        raise LocalTtsError("episode must contain a non-empty segments list")
    return episode


def choose_device(provider: str, requested: str) -> str:
    if provider == "supertonic":
        return "cpu"
    if requested != "auto":
        return requested
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def build_synthesizer(args: argparse.Namespace) -> tuple[Callable[[str], tuple[Any, int]], str, Optional[str]]:
    device = choose_device(args.provider, args.device)
    if args.provider == "supertonic":
        try:
            import numpy as np
            import soundfile as sf
            from supertonic import TTS
        except ImportError as error:
            raise LocalTtsError(
                "Supertonic is not installed. Run: uv pip install --python .venv-tts/bin/python "
                "supertonic soundfile"
            ) from error

        tts = TTS(auto_download=True)
        try:
            voice_style = tts.get_voice_style(voice_name=args.voice)
        except Exception as error:
            raise LocalTtsError(f"could not load Supertonic voice '{args.voice}': {error}") from error

        def synthesize(text: str) -> tuple[Any, int]:
            wav, _duration = tts.synthesize(
                text=text,
                lang=args.language,
                voice_style=voice_style,
                total_steps=args.steps,
                speed=args.speed,
            )
            audio = np.asarray(wav).squeeze()
            if audio.ndim != 1:
                audio = audio.reshape(-1)
            return audio, 44100

        def save(audio: Any, sample_rate: int, path: Path) -> None:
            sf.write(path, audio, sample_rate, subtype="PCM_16")

        synthesize.save = save  # type: ignore[attr-defined]
        return synthesize, device, args.voice

    if args.provider == "qwen3_tts":
        try:
            import numpy as np
            import soundfile as sf
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as error:
            raise LocalTtsError(
                "Qwen3-TTS is not installed. Run: uv pip install --python .venv-tts/bin/python "
                f"qwen-tts soundfile (import error: {error})"
            ) from error

        model_name = args.model or "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
        dtype = torch.float16 if device.startswith("cuda") else torch.float32
        load_kwargs: dict[str, Any] = {"device_map": device, "dtype": dtype}
        try:
            model = Qwen3TTSModel.from_pretrained(model_name, **load_kwargs)
        except Exception as error:
            if device.startswith("cuda") and args.device == "auto":
                print(f"WARN: Qwen GPU load failed; retrying on CPU: {error}")
                device = "cpu"
                model = Qwen3TTSModel.from_pretrained(model_name, device_map="cpu", dtype=torch.float32)
            else:
                raise LocalTtsError(f"could not load Qwen3-TTS model: {error}") from error

        def synthesize(text: str) -> tuple[Any, int]:
            language = "Korean" if args.language == "ko" else args.language
            wavs, sample_rate = model.generate_custom_voice(
                text=text,
                language=language,
                speaker=args.speaker,
                instruct=args.instruct,
            )
            audio = np.asarray(wavs[0]).squeeze()
            if audio.ndim != 1:
                audio = audio.reshape(-1)
            return audio, int(sample_rate)

        def save(audio: Any, sample_rate: int, path: Path) -> None:
            sf.write(path, audio, sample_rate, subtype="PCM_16")

        synthesize.save = save  # type: ignore[attr-defined]
        return synthesize, device, args.speaker

    raise LocalTtsError(f"unsupported provider: {args.provider}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate local TTS audio for an episode JSON.")
    parser.add_argument("episode", help="Episode JSON path.")
    parser.add_argument("--provider", choices=("supertonic", "qwen3_tts"), required=True)
    parser.add_argument("--output-dir", help="Directory for scene WAV files.")
    parser.add_argument("--manifest", help="Timing manifest output path.")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda:0"), default="auto")
    parser.add_argument("--voice", default="F1", help="Supertonic voice style, e.g. F1 or M1.")
    parser.add_argument("--speaker", default="Sohee", help="Qwen3-TTS speaker.")
    parser.add_argument("--model", help="Qwen model name or local model path.")
    parser.add_argument("--instruct", default="차분하고 또렷한 정보형 유튜브 쇼츠 내레이션으로 말해줘.")
    parser.add_argument("--language", default="ko")
    parser.add_argument("--speed", type=float, default=1.4)
    parser.add_argument("--steps", type=int, default=8, help="Supertonic denoising steps.")
    parser.add_argument("--timeline-mode", choices=("planned", "speech"), default="planned")
    parser.add_argument("--limit", type=int, help="Generate only the first N scenes for a smoke test.")
    parser.add_argument("--force", action="store_true", help="Regenerate existing scene audio files.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without loading models.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    episode_path = Path(args.episode).expanduser()
    episode = load_episode(episode_path)
    episode_id = slugify(episode_path.stem)
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else Path("output/audio") / args.provider / episode_id
    manifest_path = Path(args.manifest).expanduser() if args.manifest else Path("output/manifests") / f"{episode_id}.{args.provider}.tts.json"
    segments = episode["segments"][: args.limit] if args.limit else episode["segments"]
    plan = [
        {
            "index": index,
            "narration": segment["narration"],
            "planned_duration_sec": float(segment.get("duration_sec", 0)),
            "output": str(output_dir / f"segment-{index:03d}.wav"),
        }
        for index, segment in enumerate(segments, start=1)
    ]
    if args.dry_run:
        print(json.dumps({
            "provider": args.provider,
            "device": "not_loaded",
            "voice": args.voice if args.provider == "supertonic" else args.speaker,
            "output_dir": str(output_dir),
            "manifest": str(manifest_path),
            "segments": plan,
        }, ensure_ascii=False, indent=2))
        return 0

    synthesize, device, voice = build_synthesizer(args)
    save_audio = getattr(synthesize, "save")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_segments = []
    for item in plan:
        output = Path(item["output"])
        started = time.perf_counter()
        generated = args.force or not output.exists()
        if generated:
            try:
                audio, sample_rate = synthesize(item["narration"])
                save_audio(audio, sample_rate, output)
            except Exception as error:
                raise LocalTtsError(f"generation failed for segment {item['index']}: {error}") from error
        else:
            try:
                import soundfile as sf

                info = sf.info(output)
                duration_sec = info.frames / info.samplerate
            except Exception as error:
                raise LocalTtsError(f"could not measure existing audio {output}: {error}") from error
        generation_sec = time.perf_counter() - started
        try:
            audio_validation = validate_wav(output)
        except (OSError, AudioValidationError) as error:
            raise LocalTtsError(f"audio validation failed for segment {item['index']}: {error}") from error
        duration_sec = audio_validation["duration_sec"]
        planned_duration = item["planned_duration_sec"]
        timeline_duration = duration_sec if args.timeline_mode == "speech" else max(planned_duration, duration_sec)
        manifest_segments.append({
            "index": item["index"],
            "audio_path": str(output),
            "speech_duration_sec": round(duration_sec, 3),
            "planned_duration_sec": planned_duration,
            "timeline_duration_sec": round(timeline_duration, 3),
            "generation_time_sec": round(generation_sec, 3),
            "audio_validation": audio_validation,
            "narration": item["narration"],
        })
        print(f"OK segment {item['index']:03d}: {duration_sec:.2f}s speech, {generation_sec:.2f}s generation")

    manifest = {
        "manifest_version": 1,
        "episode_path": str(episode_path),
        "title": episode.get("title"),
        "provider": args.provider,
        "device": device,
        "voice": voice,
        "model": args.model if args.provider == "qwen3_tts" else "supertonic-3",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_duration_sec": episode.get("target_duration_sec", 60),
        "timeline_mode": args.timeline_mode,
        "speech_duration_sec": round(sum(item["speech_duration_sec"] for item in manifest_segments), 3),
        "timeline_duration_sec": round(sum(item["timeline_duration_sec"] for item in manifest_segments), 3),
        "generation_time_sec": round(sum(item["generation_time_sec"] for item in manifest_segments), 3),
        "segments": manifest_segments,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote timing manifest: {manifest_path}")
    if not 50 <= manifest["timeline_duration_sec"] <= 70 and len(segments) == len(episode["segments"]):
        print(f"WARN: timeline is {manifest['timeline_duration_sec']:g}s; expected 50-70s")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LocalTtsError as error:
        print(f"error: {error}")
        raise SystemExit(1)
