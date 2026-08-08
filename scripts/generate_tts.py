#!/usr/bin/env python3
"""Generate scene-level ElevenLabs audio and a timing manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import wave
from typing import Any, Optional


DEFAULT_HELPER_RELATIVE = Path(".codex/skills/elevenlabs-tts/scripts/generate_voice.py")


class TtsError(RuntimeError):
    """Raised when the TTS pipeline cannot continue safely."""


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
        raise TtsError(f"episode file not found: {path}")
    try:
        episode = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise TtsError(f"invalid episode JSON: {error}") from error
    if not isinstance(episode, dict) or not isinstance(episode.get("segments"), list):
        raise TtsError("episode must be an object with a segments list")
    if not episode["segments"]:
        raise TtsError("episode has no segments")
    return episode


def resolve_helper(explicit: Optional[str]) -> list[str]:
    configured = explicit or os.environ.get("ELEVENLABS_TTS_HELPER")
    if configured:
        parts = shlex.split(configured)
        if not parts:
            raise TtsError("ELEVENLABS_TTS_HELPER is empty")
        if len(parts) == 1 and Path(parts[0]).suffix == ".py":
            return [sys.executable, parts[0]]
        return parts

    candidates = [Path.home() / DEFAULT_HELPER_RELATIVE]
    windows_users = Path("/mnt/c/Users")
    if windows_users.is_dir():
        candidates.extend(windows_users.glob("*/.codex/skills/elevenlabs-tts/scripts/generate_voice.py"))
    for candidate in candidates:
        if candidate.is_file():
            return [sys.executable, str(candidate)]

    found = shutil.which("generate_voice.py")
    if found:
        return [found]
    raise TtsError(
        "ElevenLabs helper not found. Set ELEVENLABS_TTS_HELPER or pass --helper "
        "with the path to the elevenlabs-tts skill's generate_voice.py."
    )


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_local_env(env_file: Optional[str]) -> dict[str, str]:
    values = dict(os.environ)
    candidates = []
    if env_file:
        candidates.append(Path(env_file).expanduser())
    else:
        current = Path.cwd().resolve()
        candidates.extend(folder / ".env" for folder in [current, *current.parents])
    for candidate in candidates:
        if candidate.is_file():
            for key, value in parse_env_file(candidate).items():
                values.setdefault(key, value)
            break
    return values


def measure_mp3_duration(path: Path) -> float:
    """Measure common MPEG audio files without requiring ffmpeg or mutagen."""

    data = path.read_bytes()
    offset = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        tag_size = sum((data[index] & 0x7F) << (7 * (3 - index)) for index in range(6, 10))
        offset = 10 + tag_size + (10 if data[5] & 0x10 else 0)

    bitrate_tables = {
        3: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
        2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
    }
    sample_rates = {0: [44100, 48000, 32000], 1: [22050, 24000, 16000], 2: [11025, 12000, 8000]}
    version_map = {3: (3, 1), 2: (2, 2), 0: (2, 2)}
    total_samples = 0
    first_sample_rate = 0
    frame_count = 0

    while offset + 4 <= len(data):
        header = int.from_bytes(data[offset : offset + 4], "big")
        if (header >> 21) & 0x7FF != 0x7FF:
            offset += 1
            continue
        version_bits = (header >> 19) & 0x3
        layer_bits = (header >> 17) & 0x3
        bitrate_index = (header >> 12) & 0xF
        sample_index = (header >> 10) & 0x3
        padding = (header >> 9) & 0x1
        if version_bits == 1 or layer_bits != 1 or bitrate_index in (0, 15) or sample_index == 3:
            offset += 1
            continue

        version_group, coefficient = version_map[version_bits]
        table = bitrate_tables[version_group]
        bitrate = table[bitrate_index] * 1000
        sample_rate_group = {3: 0, 2: 1, 0: 2}[version_bits]
        sample_rate = sample_rates[sample_rate_group][sample_index]
        frame_length = (coefficient * bitrate // sample_rate) + (coefficient // 2) * padding
        if frame_length <= 0 or offset + frame_length > len(data):
            offset += 1
            continue
        samples_per_frame = 1152 if version_group == 3 else 576
        total_samples += samples_per_frame
        first_sample_rate = first_sample_rate or sample_rate
        frame_count += 1
        offset += frame_length

    if not frame_count or not first_sample_rate:
        raise TtsError(f"could not measure MP3 duration: {path}")
    return total_samples / first_sample_rate


def measure_duration(path: Path, ffprobe: Optional[str]) -> float:
    if ffprobe:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            try:
                return float(result.stdout.strip())
            except ValueError:
                pass
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as audio:
            return audio.getnframes() / audio.getframerate()
    return measure_mp3_duration(path)


def run_helper(
    helper: list[str],
    narration: str,
    output: Path,
    config: Optional[Path],
    profile: Optional[str],
    env_file: Optional[str],
) -> None:
    command = [*helper, "--text", narration, "--output", str(output)]
    if config:
        command.extend(["--config", str(config)])
    if profile:
        command.extend(["--profile", profile])
    if env_file:
        command.extend(["--env-file", env_file])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise TtsError(f"TTS generation failed for {output.name}: {detail}")


def build_manifest(
    episode_path: Path,
    episode: dict[str, Any],
    profile: Optional[str],
    timeline_mode: str,
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "manifest_version": 1,
        "episode_path": str(episode_path),
        "title": episode.get("title"),
        "provider": "elevenlabs",
        "profile": profile,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_duration_sec": episode.get("target_duration_sec", 60),
        "timeline_mode": timeline_mode,
        "speech_duration_sec": round(sum(item["speech_duration_sec"] for item in segments), 3),
        "timeline_duration_sec": round(sum(item["timeline_duration_sec"] for item in segments), 3),
        "segments": segments,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate scene-level ElevenLabs TTS for an episode JSON.")
    parser.add_argument("episode", help="Episode JSON path.")
    parser.add_argument("--config", help="Local ElevenLabs profile JSON path.")
    parser.add_argument("--profile", help="Profile name in the local profile JSON.")
    parser.add_argument("--env-file", help="Path to a .env file.")
    parser.add_argument("--helper", help="Path or command for generate_voice.py.")
    parser.add_argument("--output-dir", help="Directory for scene audio files.")
    parser.add_argument("--manifest", help="Output timing manifest path.")
    parser.add_argument("--timeline-mode", choices=("planned", "speech"), default="planned")
    parser.add_argument("--ffprobe", help="ffprobe executable, if available.")
    parser.add_argument("--force", action="store_true", help="Regenerate existing scene audio files.")
    parser.add_argument("--keep-going", action="store_true", help="Continue after a failed scene and report failures at the end.")
    parser.add_argument("--dry-run", action="store_true", help="Print the generation plan without calling ElevenLabs.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    episode_path = Path(args.episode).expanduser()
    episode = load_episode(episode_path)
    episode_id = slugify(episode_path.stem)
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else Path("output/audio") / episode_id
    manifest_path = Path(args.manifest).expanduser() if args.manifest else Path("output/manifests") / f"{episode_id}.tts.json"
    local_env = load_local_env(args.env_file)
    config = Path(args.config).expanduser() if args.config else None
    if not config and local_env.get("ELEVENLABS_TTS_CONFIG"):
        config = Path(local_env["ELEVENLABS_TTS_CONFIG"]).expanduser()
    if config and not config.is_file():
        raise TtsError(f"profile config not found: {config}")

    helper = resolve_helper(args.helper) if not args.dry_run else []
    selected_profile = args.profile or local_env.get("ELEVENLABS_TTS_PROFILE")
    if not selected_profile and config:
        try:
            config_data = json.loads(config.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise TtsError(f"invalid profile config JSON: {error}") from error
        if isinstance(config_data, dict) and config_data.get("default_profile"):
            selected_profile = str(config_data["default_profile"])
    plan = []
    for position, segment in enumerate(episode["segments"], start=1):
        output = output_dir / f"segment-{position:03d}.mp3"
        plan.append({
            "index": position,
            "output": str(output),
            "narration": segment["narration"],
            "planned_duration_sec": segment.get("duration_sec"),
        })

    if args.dry_run:
        print(json.dumps({
            "episode": str(episode_path),
            "provider": "elevenlabs",
            "config": str(config) if config else None,
            "profile": selected_profile,
            "output_dir": str(output_dir),
            "manifest": str(manifest_path),
            "timeline_mode": args.timeline_mode,
            "segments": plan,
        }, ensure_ascii=False, indent=2))
        return 0

    ffprobe = args.ffprobe or shutil.which("ffprobe")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_segments = []
    failures = []
    for item, segment in zip(plan, episode["segments"]):
        output = Path(item["output"])
        try:
            if args.force or not output.exists():
                run_helper(helper, segment["narration"], output, config, selected_profile, args.env_file)
            speech_duration = measure_duration(output, ffprobe)
            planned_duration = float(segment.get("duration_sec", 0))
            timeline_duration = speech_duration if args.timeline_mode == "speech" else max(planned_duration, speech_duration)
            manifest_segments.append({
                "index": item["index"],
                "audio_path": str(output),
                "speech_duration_sec": round(speech_duration, 3),
                "planned_duration_sec": planned_duration,
                "timeline_duration_sec": round(timeline_duration, 3),
                "narration": segment["narration"],
            })
            print(f"OK segment {item['index']:03d}: {speech_duration:.2f}s -> {output}")
        except (OSError, TtsError, ValueError) as error:
            failures.append(str(error))
            print(f"ERROR segment {item['index']:03d}: {error}", file=sys.stderr)
            if not args.keep_going:
                raise SystemExit(1) from error

    if failures:
        raise SystemExit(f"{len(failures)} segment(s) failed")
    manifest = build_manifest(episode_path, episode, selected_profile, args.timeline_mode, manifest_segments)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote timing manifest: {manifest_path}")
    total = manifest["timeline_duration_sec"]
    if not 50 <= total <= 70:
        print(f"WARN: timeline is {total:g}s; expected 50-70s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TtsError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
