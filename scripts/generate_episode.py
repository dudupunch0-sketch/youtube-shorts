#!/usr/bin/env python3
"""Generate a structured Shorts episode from a topic and an active concept."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "pipeline.json"
SKILL_PATH = ROOT / "skills" / "scriptwriter" / "SKILL.md"
API_URL = "https://api.openai.com/v1/chat/completions"


EPISODE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "topic": {"type": "string"},
        "concept_id": {"type": "string"},
        "language": {"type": "string"},
        "target_duration_sec": {"type": "number"},
        "estimated_duration_sec": {"type": "number", "minimum": 55, "maximum": 65},
        "reference_style": {"type": "string"},
        "content_domain": {"type": "string"},
        "segments": {
            "type": "array",
            "minItems": 12,
            "maxItems": 18,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer", "minimum": 1},
                    "narration": {"type": "string"},
                    "visual_query": {"type": "string"},
                    "visual_type": {
                        "type": "string",
                        "enum": ["photo", "video", "illustration", "map", "typography"],
                    },
                    "caption": {"type": "string"},
                    "duration_sec": {"type": "number", "minimum": 2.5, "maximum": 5.0},
                    "claim_type": {
                        "type": "string",
                        "enum": ["official", "secondary_reference", "creative_interpretation"],
                    },
                    "source": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "status": {"type": "string", "enum": ["pending", "ready", "generated"]},
                            "source_url": {"type": ["string", "null"]},
                            "license": {"type": ["string", "null"]},
                            "creator": {"type": ["string", "null"]},
                        },
                        "required": ["status", "source_url", "license", "creator"],
                    },
                },
                "required": [
                    "index",
                    "narration",
                    "visual_query",
                    "visual_type",
                    "caption",
                    "duration_sec",
                    "claim_type",
                    "source",
                ],
            },
        },
    },
    "required": [
        "title",
        "topic",
        "concept_id",
        "language",
        "target_duration_sec",
        "estimated_duration_sec",
        "reference_style",
        "content_domain",
        "segments",
    ],
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc


def load_concept(requested_id: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    config = read_json(CONFIG_PATH)
    registry = read_json(ROOT / config["concepts"]["registry"])
    concept_id = requested_id or registry["active_concept"]
    concept = next((item for item in registry["concepts"] if item["id"] == concept_id), None)
    if concept is None:
        known = ", ".join(item["id"] for item in registry["concepts"])
        raise SystemExit(f"unknown concept '{concept_id}'. Known concepts: {known}")
    return config, concept


def read_input(args: argparse.Namespace) -> tuple[str, str, list[str], list[str]]:
    if args.note and args.topic:
        raise SystemExit("use either --note or --topic, not both")
    if not args.note and not args.topic:
        raise SystemExit("provide --topic or --note")
    topic = args.topic or ""
    note = ""
    if args.note:
        note_path = Path(args.note)
        try:
            note = note_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise SystemExit(f"note file not found: {note_path}") from exc
        if not note:
            raise SystemExit(f"note file is empty: {note_path}")
    return topic.strip(), note, args.must_include, args.avoid


def build_prompts(
    config: dict[str, Any],
    concept: dict[str, Any],
    topic: str,
    note: str,
    must_include: list[str],
    avoid: list[str],
) -> tuple[str, str]:
    definition = (ROOT / concept["definition"]).read_text(encoding="utf-8")
    profile = (ROOT / concept["style_profile"]).read_text(encoding="utf-8")
    skill = SKILL_PATH.read_text(encoding="utf-8")
    video = config["video"]
    content = config["content"]
    system_prompt = f"""You are the scriptwriter for a YouTube Shorts production pipeline.

Use the selected concept and its saved style profile. The profile is a reusable style guide, not text to copy. Create original content and do not reproduce any reference video's sentences, ordering, shots, or assets.

Return only JSON matching the supplied schema. Do not use Markdown fences.

Selected concept definition:
{definition}

Saved style profile:
{profile}

Scriptwriter rules:
{skill}

Production constraints:
- target duration: {video['target_duration_seconds']} seconds
- accepted duration: {video['accepted_duration_range_seconds'][0]}-{video['accepted_duration_range_seconds'][1]} seconds
- recommended segment count: {video['recommended_segment_count'][0]}-{video['recommended_segment_count'][1]}
- segment duration: {video['segment_duration_seconds'][0]}-{video['segment_duration_seconds'][1]} seconds
- content domain: {content['domain']}
- claim types: {', '.join(content['claim_types'])}
- all media sources start with status 'pending'
- use 'creative_interpretation' when a claim is an interpretation, not an official fact
"""
    must_text = "\n".join(f"- {item}" for item in must_include) or "- 없음"
    avoid_text = "\n".join(f"- {item}" for item in avoid) or "- 없음"
    user_prompt = f"""Create one original Shorts episode.

Topic:
{topic or '(extract the topic from the note)'}

User note:
{note or '(none)'}

Information that must be included:
{must_text}

Directions to avoid:
{avoid_text}

The output must be a complete episode JSON with 12-18 segments and a total duration between 55 and 65 seconds. Keep each narration unit short enough for TTS. Set concept_id to '{concept['id']}', reference_style to '{concept['style_profile']}', and target_duration_sec to {video['target_duration_seconds']}.
"""
    return system_prompt, user_prompt


def call_openai(model: str, api_key: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "shorts_episode",
                "strict": True,
                "schema": EPISODE_SCHEMA,
            },
        },
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI API error {exc.code}: {detail[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"could not reach OpenAI API: {exc.reason}") from exc
    try:
        message = result["choices"][0]["message"]
        if message.get("refusal"):
            raise SystemExit(f"model refused the request: {message['refusal']}")
        episode = json.loads(message["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"unexpected OpenAI response shape: {json.dumps(result)[:1000]}") from exc
    if not isinstance(episode, dict):
        raise SystemExit("model response was not a JSON object")
    return episode


def safe_name(value: str) -> str:
    value = re.sub(r"[^\w가-힣]+", "-", value, flags=re.UNICODE).strip("-").lower()
    return value[:80] or "episode"


def output_path(requested: str | None, topic: str, concept_id: str) -> Path:
    if requested:
        path = Path(requested)
        return path if path.is_absolute() else ROOT / path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ROOT / "output" / "episodes" / f"{stamp}-{safe_name(topic or concept_id)}.json"


def validate_and_write(episode: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validator = ROOT / "scripts" / "validate_episode.py"
    result = subprocess.run([sys.executable, str(validator), str(temporary)], capture_output=True, text=True)
    if result.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise SystemExit(result.stdout.strip() or result.stderr.strip())
    temporary.replace(destination)
    print(result.stdout.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--topic", help="short topic or premise")
    source.add_argument("--note", help="path to a UTF-8 note file")
    parser.add_argument("--must-include", action="append", default=[], help="claim to include; repeatable")
    parser.add_argument("--avoid", action="append", default=[], help="direction to avoid; repeatable")
    parser.add_argument("--concept", help="concept id; defaults to the registry active concept")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.6"))
    parser.add_argument("--output", help="output JSON path; defaults to output/episodes/<timestamp>-<topic>.json")
    parser.add_argument("--dry-run", action="store_true", help="print resolved prompts without calling the API")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config, concept = load_concept(args.concept)
    topic, note, must_include, avoid = read_input(args)
    system_prompt, user_prompt = build_prompts(config, concept, topic, note, must_include, avoid)
    if args.dry_run:
        print(f"concept: {concept['id']}")
        print(f"style_profile: {concept['style_profile']}")
        print("--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("--- USER PROMPT ---")
        print(user_prompt)
        return
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set. Export it, or run with --dry-run to inspect the prompt.")
    episode = call_openai(args.model, api_key, system_prompt, user_prompt)
    episode["concept_id"] = concept["id"]
    episode["reference_style"] = concept["style_profile"]
    episode["content_domain"] = config["content"]["domain"]
    episode["target_duration_sec"] = config["video"]["target_duration_seconds"]
    destination = output_path(args.output, topic, concept["id"])
    validate_and_write(episode, destination)
    print(f"saved: {destination}")


if __name__ == "__main__":
    main()

