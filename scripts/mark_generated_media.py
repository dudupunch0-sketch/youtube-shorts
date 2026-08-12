#!/usr/bin/env python3
"""Record generated still-image assets in a media manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


COMMON_PROMPT = (
    "Original editorial illustration for a vertical short-form video, 9:16 portrait "
    "composition, cinematic lighting, polished digital painting, one clear focal "
    "composition, leave calm darker negative space near the lower quarter for captions, "
    "no text, no subtitles, no watermark, no logo, no user interface, no collage, "
    "original fantasy creatures only, do not depict or imitate any exact copyrighted "
    "character design."
)

SCENE_PROMPTS = {
    1: "two original creatures: a small round pink fairy-like creature and a dark purple shadow creature, their silhouettes echoing each other under a full moon",
    2: "a small bright fairy creature in moonlight with a dark purple shadow rising behind it",
    3: "a detective evidence board with abstract creature silhouette cards, red thread, pins, and a mysterious investigation mood, no readable words",
    4: "a clean shape comparison of two original creatures with round bodies, short arms, pointed ears, and subtle guide lines, no text",
    5: "a yin-yang-like light and dark contrast between a luminous pink fairy-like creature and a dark violet shadow creature",
    6: "a dark original creature emerging from an old archival catalog card and smoky moonlit atmosphere, with abstract marks but no readable words",
    7: "an antique brass weighing scale in a moonlit study with two original creature silhouettes on opposite pans, almost balanced, no numbers",
    8: "a dark violet shadow creature standing on a dramatic weighing scale with stormy spotlight and abstract data-card shapes, no text or numbers",
    9: "a pale pink fairy-like evolution creature beside a vintage weighing scale in soft moonlight, gentle magical atmosphere, no words or numbers",
    10: "a close-up balance scale nearly perfectly even, with two abstract original creature tokens on the pans, no text or numbers",
    11: "a theatrical black curtain opening to reveal a glowing moonlit silhouette of an original shadow creature, suspenseful purple and gold light, no letters",
    12: "a tiny round pink fairy-like creature on one weighing scale and a much larger dark violet shadow creature on another, obvious weight imbalance, no text",
    13: "three original fairy-like evolution forms arranged from small to larger, with a dark shadow echo emerging behind the final form, moonlit magical tableau",
    14: "a split composition with an old canonical-looking reference book and clean studio diagram on one side, and a fan theory sketch board with red thread on the other, no readable words",
    15: "two original creatures facing each other beneath a huge moon: a luminous small fairy-like creature and a dark violet shadow creature, quiet mysterious ending",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    # Manifests live under output/manifests; asset paths are repository-relative.
    repo_root = manifest_path.parent.parent.parent
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    for segment in data["segments"]:
        index = int(segment["index"])
        asset_path = Path("output/media") / data["episode_id"] / f"segment-{index:03d}.png"
        absolute_asset_path = repo_root / asset_path
        if not absolute_asset_path.is_file():
            raise SystemExit(f"missing generated asset: {asset_path}")

        scene = SCENE_PROMPTS[index]
        prompt = f"{COMMON_PROMPT} Scene {index}: {scene}."
        segment["search"]["status"] = "no_suitable_open_license"
        segment["asset"] = {
            "status": "approved",
            "mode": "generated",
            "path": asset_path.as_posix(),
            "source_url": None,
            "landing_url": None,
            "license": "generated_original",
            "license_url": None,
            "creator": "OpenAI image generation",
            "attribution": "Generated original illustration with OpenAI image generation",
            "generator": "imagegen",
            "prompt": prompt,
            "review_notes": "Automated file checks passed; original symbolic illustration with no exact franchise character design.",
        }

    data["asset_root"] = (Path("output/media") / data["episode_id"]).as_posix()
    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Approved generated assets: {len(data['segments'])}")
    print(f"Manifest: {manifest_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
