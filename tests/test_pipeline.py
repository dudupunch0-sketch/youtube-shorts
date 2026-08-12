import tempfile
import unittest
import wave
from pathlib import Path

from scripts.audio_validation import AudioValidationError, validate_wav
from scripts.plan_presentation import recommend_layout, stable_candidate_id


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


if __name__ == "__main__":
    unittest.main()
