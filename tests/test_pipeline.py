import json
import tempfile
import unittest
import wave
from pathlib import Path

from scripts.audio_validation import AudioValidationError, validate_wav
from scripts.plan_presentation import recommend_layout, stable_candidate_id
from scripts.publish_licensing import classify_license
from scripts.publish_metadata import (
    attribution_entries,
    selected_assets,
    tags_length,
    utf8_length,
)
from scripts.publish_validation import check_manifest, check_render


def approved_publish_manifest(**overrides):
    """A publish manifest that passes every filesystem-independent check."""
    disclosure = "이 영상의 내레이션은 AI 음성으로 생성되었습니다."
    manifest = {
        "segment_count": 1,
        "limits": {
            "title_max_chars": 100,
            "description_max_bytes": 5000,
            "tags_max_total_chars": 500,
            "shorts_max_duration_seconds": 180,
        },
        "metadata": {
            "title": "테스트 제목",
            "description": f"훅\n\n{disclosure}\n\n출처 및 라이선스\n- 장면 1: 작가 / CC BY 4.0",
            "description_blocks": {"interpretation_notice": ""},
            "tags": ["태그"],
            "category_id": "24",
            "default_language": "ko",
            "default_audio_language": "ko",
        },
        "status": {
            "privacy_status": "private",
            "publish_at": None,
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": True,
        },
        "disclosure": {"description_sentence_ko": disclosure},
        "claim_summary": {"official": 1},
        "attribution": [
            {
                "segments": [1],
                "source_url": "https://example.test/image.jpg",
                "landing_url": "https://example.test/page",
                "license": "CC BY 4.0",
                "creator": "작가",
                "review_status": "approved",
                "license_decision": "allow",
                "license_reason": "ok",
                "license_conditions": [],
                "commercial_use_allowed": True,
            }
        ],
        "review": {
            "status": "approved",
            "approved_by": "tester",
            "approved_at": "2026-08-13T00:00:00+00:00",
        },
        "upload": {"state": "not_uploaded", "video_id": None},
    }
    manifest.update(overrides)
    return manifest


class PipelineTests(unittest.TestCase):
    def test_comparison_recommends_left_right_split(self):
        segment = {
            "narration": "두 포켓몬은 비슷한 실루엣을 가졌다.",
            "caption": "닮은 점 비교",
            "visual_query": "팬텀 픽시 비교",
            "candidates": [{"asset_url": "a"}, {"asset_url": "b"}],
        }
        layout, confidence, reason = recommend_layout(segment, {})
        self.assertEqual(layout, "split_2up_left_right")
        self.assertGreaterEqual(confidence, 0.8)
        self.assertIn("Comparison", reason)

    def test_candidate_id_is_stable_for_same_source(self):
        candidate = {
            "provider": "namuwiki_capture",
            "asset_url": "https://example.test/page",
            "landing_url": "https://example.test/page",
            "capture_path": "output/playwright/segment-1.png",
            "title": "context",
            "query": "weight",
        }
        self.assertEqual(stable_candidate_id(candidate, 1), stable_candidate_id(candidate, 1))
        changed = dict(candidate, query="height")
        self.assertNotEqual(stable_candidate_id(candidate, 1), stable_candidate_id(changed, 1))

    def test_audio_validator_rejects_constant_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silent.wav"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(22050)
                output.writeframes(b"\x00\x00" * 22050)
            with self.assertRaises(AudioValidationError):
                validate_wav(path)

    def test_audio_validator_accepts_non_constant_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice.wav"
            samples = b"".join(value.to_bytes(2, "little", signed=True) for value in (1000, -1000) * 11025)
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(22050)
                output.writeframes(samples)
            metrics = validate_wav(path)
            self.assertTrue(metrics["non_silent"])
            self.assertFalse(metrics["constant_signal"])


class PublishLicensingTests(unittest.TestCase):
    def test_unknown_license_is_blocked(self):
        for value in (None, "", "unknown", "미기록"):
            self.assertEqual(classify_license(value, commercial_use=False)["decision"], "block")

    def test_no_derivatives_is_blocked_even_without_monetization(self):
        verdict = classify_license("by-nc-nd", commercial_use=False)
        self.assertEqual(verdict["decision"], "block")
        self.assertIn("NoDerivatives", verdict["reason"])

    def test_noncommercial_depends_on_channel_setting(self):
        recorded = "CC BY-NC-SA 2.0 KR (text; verify document and media exclusions)"
        self.assertEqual(classify_license(recorded, commercial_use=True)["decision"], "block")
        allowed = classify_license(recorded, commercial_use=False)
        self.assertEqual(allowed["decision"], "allow")
        self.assertFalse(allowed["commercial_use_allowed"])
        self.assertTrue(any("ShareAlike" in item for item in allowed["conditions"]))

    def test_public_domain_carries_no_conditions(self):
        verdict = classify_license("Public domain", commercial_use=True)
        self.assertEqual(verdict["decision"], "allow")
        self.assertEqual(verdict["conditions"], [])

    def test_prose_containing_by_is_not_creative_commons(self):
        verdict = classify_license("used by permission", commercial_use=False)
        self.assertEqual(verdict["decision"], "block")
        self.assertIn("인식할 수 없는", verdict["reason"])


class PublishMetadataTests(unittest.TestCase):
    def test_description_length_is_measured_in_utf8_bytes(self):
        korean = "가" * 10
        self.assertEqual(len(korean), 10)
        self.assertEqual(utf8_length(korean), 30)

    def test_tag_length_counts_separators(self):
        self.assertEqual(tags_length(["가", "나"]), 4)
        self.assertEqual(tags_length([]), 0)

    def test_candidates_are_never_treated_as_selected_assets(self):
        segment = {
            "candidates": [{"asset_url": "https://example.test/candidate.jpg"}],
            "visual": {"assets": []},
            "asset": {"status": "pending", "path": None, "source_url": None},
        }
        self.assertEqual(selected_assets(segment), [])

    def test_same_page_with_different_encoding_is_one_attribution(self):
        def asset(landing):
            return {
                "position": "full",
                "status": "approved",
                "landing_url": landing,
                "source_url": landing,
                "license": "CC BY-SA 4.0",
                "creator": "contributors",
            }

        media = {
            "segments": [
                {"index": 6, "visual": {"assets": [asset("https://example.test/w/A%29")]}},
                {"index": 8, "visual": {"assets": [asset("https://example.test/w/A)")]}},
            ]
        }
        entries = attribution_entries(media, commercial_use=False)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["segments"], [6, 8])
        self.assertTrue(entries[0]["line"].startswith("장면 6, 8:"))

    def test_recorded_attribution_keeps_the_scene_prefix(self):
        media = {
            "segments": [
                {
                    "index": 3,
                    "visual": {
                        "assets": [
                            {
                                "status": "approved",
                                "landing_url": "https://example.test/page",
                                "source_url": "https://example.test/page",
                                "license": "CC BY 4.0",
                                "creator": "작가",
                                "attribution": "\"제목\" by 작가, CC BY 4.0",
                            }
                        ]
                    },
                }
            ]
        }
        entries = attribution_entries(media, commercial_use=True)
        self.assertEqual(entries[0]["line"], '장면 3: "제목" by 작가, CC BY 4.0')


class PublishValidationTests(unittest.TestCase):
    def test_fully_approved_manifest_passes(self):
        result = check_manifest(approved_publish_manifest())
        self.assertTrue(result["passed"], result["failures"])

    def test_missing_disclosure_sentence_fails(self):
        manifest = approved_publish_manifest()
        manifest["metadata"]["description"] = "훅만 있는 설명문"
        result = check_manifest(manifest)
        self.assertFalse(result["passed"])
        self.assertTrue(any("고지 문장" in item for item in result["failures"]))

    def test_unapproved_plan_fails_the_gate(self):
        manifest = approved_publish_manifest()
        manifest["review"] = {"status": "needs_review", "approved_by": None, "approved_at": None}
        result = check_manifest(manifest)
        self.assertFalse(result["passed"])
        self.assertTrue(any("게시 계획이 승인되지" in item for item in result["failures"]))

    def test_already_uploaded_manifest_fails(self):
        manifest = approved_publish_manifest()
        manifest["upload"] = {"state": "uploaded", "video_id": "abc123"}
        result = check_manifest(manifest)
        self.assertFalse(result["passed"])
        self.assertTrue(any("이미 업로드된" in item for item in result["failures"]))

    def test_scene_without_a_selected_asset_fails(self):
        manifest = approved_publish_manifest(segment_count=3)
        result = check_manifest(manifest)
        self.assertFalse(result["passed"])
        self.assertTrue(any("선택된 자산이 없는" in item for item in result["failures"]))

    def test_scheduled_publish_requires_private_and_a_future_time(self):
        manifest = approved_publish_manifest()
        manifest["status"]["publish_at"] = "2020-01-01T00:00:00+00:00"
        failures = check_manifest(manifest)["failures"]
        self.assertTrue(any("과거 시각" in item for item in failures))

        manifest["status"]["publish_at"] = "2099-01-01T00:00:00+00:00"
        self.assertTrue(check_manifest(manifest)["passed"])

        manifest["status"]["privacy_status"] = "public"
        failures = check_manifest(manifest)["failures"]
        self.assertTrue(any("private일 때만" in item for item in failures))

    def test_draft_render_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "output" / "video" / "test.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"0" * 20_000)
            report = root / "report.json"
            report.write_text(
                json.dumps(
                    {
                        "draft": True,
                        "duration_sec": 63.321,
                        "width": 1080,
                        "height": 1920,
                        "output": "output/video/test.mp4",
                    }
                ),
                encoding="utf-8",
            )
            manifest = {
                "render_report": "report.json",
                "video_path": "output/video/test.mp4",
                "limits": {},
            }
            result = check_render(manifest, root)
            self.assertFalse(result["passed"])
            self.assertTrue(any("draft" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
