#!/usr/bin/env python3
"""Render a 9:16 Shorts draft/final from media, captions, and local WAV timing."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


CANVAS = (1080, 1920)
FPS = 30
CAPTION_BAND_HEIGHT = 320
BACKGROUND = (10, 10, 18)
DIVIDER = (230, 230, 235)
TRANSITIONS = {"fade", "slide_left", "slide_up", "cut"}
LAYOUT_ALIASES = {"split_2up": "split_2up_left_right"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"could not read JSON {path}: {error}") from error


@lru_cache(maxsize=16)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        ("/mnt/c/Windows/Fonts/malgunbd.ttf", "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc")
        if bold
        else ("/mnt/c/Windows/Fonts/malgun.ttf", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc")
    )
    names += ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",)
    for name in names:
        if Path(name).is_file():
            try:
                return ImageFont.truetype(name, size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, typeface: ImageFont.ImageFont, max_width: int) -> str:
    lines: list[str] = []
    current = ""
    for char in text.strip():
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + char
        if current and draw.textlength(candidate, font=typeface) > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def fit_image(source: Image.Image, size: tuple[int, int], fit: str = "cover") -> Image.Image:
    source = source.convert("RGB")
    if fit == "contain":
        content = ImageOps.contain(source, size, method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", size, (245, 245, 248))
        canvas.paste(content, ((size[0] - content.width) // 2, (size[1] - content.height) // 2))
        return canvas
    return ImageOps.fit(source, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def text_card(segment: dict[str, Any], label: str = "") -> Image.Image:
    image = Image.new("RGB", CANVAS, (18, 19, 30))
    draw = ImageDraw.Draw(image)
    draw.rectangle((64, 120, 1016, 132), fill=(246, 205, 64))
    title = str(segment.get("caption") or segment.get("narration") or "자료를 준비 중입니다")
    title_font = font(64, True)
    body_font = font(32)
    title_text = wrap_text(draw, title, title_font, 900)
    draw.multiline_text((72, 250), title_text, font=title_font, fill=(255, 255, 255), spacing=18)
    if label:
        draw.text((72, 1100), label, font=body_font, fill=(190, 195, 210))
    draw.text((72, 1780), "SOURCE REVIEW PENDING", font=font(24, True), fill=(160, 165, 180))
    return image


class FrameRenderer:
    def __init__(self, manifest: dict[str, Any], repo_root: Path, draft: bool) -> None:
        self.manifest = manifest
        self.repo_root = repo_root
        self.draft = draft
        self.cache: dict[str, Image.Image] = {}

    def asset_image(self, segment: dict[str, Any], selected: dict[str, Any], label: str) -> Image.Image:
        path_value = selected.get("path")
        status = selected.get("status")
        if status != "approved" and not self.draft:
            raise SystemExit(
                f"segment {segment['index']} asset {selected.get('candidate_index')} is {status}; "
                "use --draft for review output or approve the asset first"
            )
        if not path_value:
            if self.draft:
                return text_card(segment, label or "No local candidate selected")
            raise SystemExit(f"segment {segment['index']} has no local asset path")
        path = (self.repo_root / path_value).resolve()
        if not path.is_file():
            if self.draft:
                return text_card(segment, label or "Selected candidate is not downloaded")
            raise SystemExit(f"missing selected asset: {path}")
        key = str(path)
        if key not in self.cache:
            self.cache[key] = Image.open(path).convert("RGB")
        return self.cache[key]

    def render_asset_full(self, segment: dict[str, Any], selected: dict[str, Any], label: str) -> Image.Image:
        visual = segment.get("visual") or {}
        fit_mode = visual.get("fit", "cover")
        return fit_image(
            self.asset_image(segment, selected, label),
            (CANVAS[0], CANVAS[1] - CAPTION_BAND_HEIGHT),
            fit_mode,
        )

    def render_layout(self, segment: dict[str, Any], at_sec: float, duration: float, first: bool = False) -> Image.Image:
        visual = segment.get("visual") or {}
        layout = LAYOUT_ALIASES.get(visual.get("layout", "full_frame"), visual.get("layout", "full_frame"))
        selected = list(visual.get("assets") or [])
        content_height = CANVAS[1] - CAPTION_BAND_HEIGHT
        if layout == "full_frame":
            base = self.render_asset_full(segment, selected[0], "full_frame") if selected else text_card(segment, "No candidate selected")
        elif layout in {"split_2up_left_right", "split_2up_top_bottom"}:
            if len(selected) != 2 and not self.draft:
                raise SystemExit(f"segment {segment['index']} {layout} requires two selected assets")
            selected = selected[:2]
            if len(selected) < 2:
                return text_card(segment, "Two-up candidates pending")
            fit_mode = visual.get("fit", "contain")
            if layout == "split_2up_left_right":
                panel_size = ((CANVAS[0] - 8) // 2, content_height)
                panels = [fit_image(self.asset_image(segment, item, item.get("position", "")), panel_size, fit_mode) for item in selected]
                base = Image.new("RGB", (CANVAS[0], content_height), (245, 245, 248))
                base.paste(panels[0], (0, 0))
                base.paste(Image.new("RGB", (8, content_height), DIVIDER), (panel_size[0], 0))
                base.paste(panels[1], (panel_size[0] + 8, 0))
            else:
                panel_size = (CANVAS[0], (content_height - 8) // 2)
                panels = [fit_image(self.asset_image(segment, item, item.get("position", "")), panel_size, fit_mode) for item in selected]
                base = Image.new("RGB", (CANVAS[0], content_height), (245, 245, 248))
                base.paste(panels[0], (0, 0))
                base.paste(Image.new("RGB", (CANVAS[0], 8), DIVIDER), (0, panel_size[1]))
                base.paste(panels[1], (0, panel_size[1] + 8))
        elif layout == "sequence":
            if len(selected) < 2 and not self.draft:
                raise SystemExit(f"segment {segment['index']} sequence requires two or more assets")
            selected = sorted(selected, key=lambda item: item.get("order", 0))
            if not selected:
                return text_card(segment, "Sequence candidates pending")
            sub_duration = duration / len(selected)
            current_index = min(len(selected) - 1, int(at_sec / max(sub_duration, 0.001)))
            current = self.render_asset_full(segment, selected[current_index], f"sequence {current_index + 1}")
            if current_index == 0:
                base = current
            else:
                boundary = current_index * sub_duration
                effect_list = (visual.get("transition") or {}).get("sequence") or ["fade"]
                effect = effect_list[min(current_index - 1, len(effect_list) - 1)] if effect_list else "fade"
                progress = min(1.0, max(0.0, (at_sec - boundary) / max(float((visual.get("transition") or {}).get("duration_sec", 0.28)), 0.001)))
                previous = self.render_asset_full(segment, selected[current_index - 1], f"sequence {current_index}")
                base = transition(previous, current, effect, progress)
        else:
            raise SystemExit(f"unsupported layout: {layout}")
        return add_caption(base, segment, first=first)


def transition(old: Image.Image, new: Image.Image, effect: str, progress: float) -> Image.Image:
    progress = max(0.0, min(1.0, progress))
    if effect == "cut":
        return new.copy()
    if effect == "fade":
        return Image.blend(old, new, progress)
    canvas = Image.new("RGB", old.size, BACKGROUND)
    if effect == "slide_up":
        offset = int(old.height * progress)
        canvas.paste(old, (0, -offset))
        canvas.paste(new, (0, old.height - offset))
    else:
        offset = int(old.width * progress)
        canvas.paste(old, (-offset, 0))
        canvas.paste(new, (old.width - offset, 0))
    return canvas


def add_caption(base: Image.Image, segment: dict[str, Any], first: bool) -> Image.Image:
    if base.size != CANVAS:
        full = Image.new("RGB", CANVAS, BACKGROUND)
        full.paste(base.convert("RGB"), (0, 0))
        base = full
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    top = CANVAS[1] - CAPTION_BAND_HEIGHT
    draw.rectangle((0, top, CANVAS[0], CANVAS[1]), fill=(5, 7, 14, 225))
    caption_font = font(54, True)
    caption = str(segment.get("caption") or "")
    caption = wrap_text(draw, caption, caption_font, 920)
    bbox = draw.multiline_textbbox((0, 0), caption, font=caption_font, spacing=12, align="center")
    y = top + 42
    draw.multiline_text(((CANVAS[0] - (bbox[2] - bbox[0])) // 2, y), caption, font=caption_font, fill=(255, 255, 255, 255), spacing=12, align="center")
    draw.text((54, 42), f"#{int(segment.get('index', 0)):02d}", font=font(28, True), fill=(246, 205, 64, 255))
    if first:
        disclosure = "AI 음성 사용"
        disclosure_font = font(24, True)
        disclosure_box = (CANVAS[0] - 286, 30, CANVAS[0] - 30, 92)
        draw.rounded_rectangle(disclosure_box, radius=14, fill=(5, 7, 14, 190))
        draw.text((CANVAS[0] - 258, 47), disclosure, font=disclosure_font, fill=(255, 255, 255, 255))
    return Image.alpha_composite(base.convert("RGBA"), canvas).convert("RGB")


def read_wav(path: Path) -> tuple[wave._wave_params, bytes]:
    with wave.open(str(path), "rb") as wav:
        params = wav.getparams()
        return params, wav.readframes(params.nframes)


def build_audio(timing: dict[str, Any], repo_root: Path, output: Path) -> tuple[Path, float, list[dict[str, Any]]]:
    chunks: list[bytes] = []
    scene_timing: list[dict[str, Any]] = []
    params: wave._wave_params | None = None
    cursor = 0.0
    for item in timing.get("segments", []):
        audio_path = Path(item["audio_path"])
        if not audio_path.is_absolute():
            audio_path = repo_root / audio_path
        current_params, audio_bytes = read_wav(audio_path)
        if params is None:
            params = current_params
        elif current_params[:3] != params[:3]:
            raise SystemExit(f"WAV format mismatch at segment {item.get('index')}")
        speech_duration = float(item.get("speech_duration_sec") or 0)
        timeline_duration = max(float(item.get("timeline_duration_sec") or 0), speech_duration)
        chunks.append(audio_bytes)
        silence_frames = max(0, round((timeline_duration - speech_duration) * params.framerate))
        chunks.append(b"\x00" * silence_frames * params.nchannels * params.sampwidth)
        scene_timing.append({"index": item["index"], "start_sec": round(cursor, 3), "duration_sec": round(timeline_duration, 3)})
        cursor += timeline_duration
    if params is None:
        raise SystemExit("timing manifest has no audio segments")
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(params.nchannels)
        wav.setsampwidth(params.sampwidth)
        wav.setframerate(params.framerate)
        wav.writeframes(b"".join(chunks))
    return output, cursor, scene_timing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("timing_manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--draft", action="store_true", help="Allow needs_review or missing candidates for a review draft")
    parser.add_argument("--fps", type=int, default=FPS)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    repo_root = manifest_path.parent.parent.parent
    manifest = load_json(manifest_path)
    timing = load_json(args.timing_manifest.resolve())
    output = args.output or repo_root / "output" / "video" / f"{manifest.get('episode_id', 'episode')}{'-draft' if args.draft else ''}.mp4"
    audio_output = repo_root / "output" / "audio" / manifest.get("episode_id", "episode") / "mix.wav"
    _, total_duration, scene_timing = build_audio(timing, repo_root, audio_output)
    scenes = {item["index"]: item for item in manifest.get("segments", [])}
    renderer = FrameRenderer(manifest, repo_root, args.draft)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise SystemExit("imageio-ffmpeg is required; install requirements-tts-local.txt in .venv-tts") from error
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{CANVAS[0]}x{CANVAS[1]}",
        "-pix_fmt", "rgb24",
        "-r", str(args.fps),
        "-i", "-",
        "-i", str(audio_output),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame_index in range(math.ceil(total_duration * args.fps)):
            at = frame_index / args.fps
            scene = next((item for item in reversed(scene_timing) if item["start_sec"] <= at), scene_timing[0])
            segment = scenes.get(scene["index"])
            if segment is None:
                raise SystemExit(f"missing episode scene {scene['index']}")
            local_at = at - scene["start_sec"]
            frame = renderer.render_layout(segment, local_at, scene["duration_sec"], first=scene["index"] == 1)
            assert process.stdin is not None
            process.stdin.write(frame.tobytes())
        assert process.stdin is not None
        process.stdin.close()
    except Exception:
        process.kill()
        raise
    process.wait()
    stdout = process.stdout.read() if process.stdout is not None else b""
    stderr = process.stderr.read() if process.stderr is not None else b""
    if process.returncode != 0:
        raise SystemExit(f"ffmpeg failed: {stderr.decode(errors='replace')[-2000:]}")
    report = {
        "manifest": str(manifest_path),
        "timing_manifest": str(args.timing_manifest),
        "output": str(output),
        "draft": args.draft,
        "width": CANVAS[0],
        "height": CANVAS[1],
        "fps": args.fps,
        "duration_sec": round(total_duration, 3),
        "audio_path": str(audio_output),
        "scene_timing": scene_timing,
    }
    report_path = repo_root / "output" / "manifests" / f"{manifest.get('episode_id', 'episode')}.render.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote video: {output}")
    print(f"Wrote render report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
