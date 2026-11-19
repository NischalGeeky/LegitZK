from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from exposure import ExposureHistory


class ExposureTests(TestCase):
    def test_overlapping_masks_are_recipient_scoped_and_durable(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.db"
            key = bytes(32)
            history = ExposureHistory(path, key)
            manifest = {"pages": [[64, 64]], "source_sha256": "a" * 64, "profile": "profile"}
            policy = {"audience": "Reviewer"}
            left, top = [[0, 0, 0, 32, 64]], [[0, 0, 0, 64, 32]]
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda mask: history.evaluate(manifest, policy, mask, record=True), (left, top)))
            self.assertEqual({result["recorded_exports"] for result in results}, {0, 1})
            report = ExposureHistory(path, key).evaluate(manifest, policy, left)
            self.assertEqual(report["recorded_exports"], 2)
            self.assertEqual(report["pages"][0]["hidden_across_releases"], 1024)
            self.assertEqual(report["pages"][0]["previously_visible_but_now_hidden"], 1024)
            for other_manifest, other_policy in (
                (manifest, {"audience": "Another reviewer"}),
                ({**manifest, "source_sha256": "b" * 64}, policy),
            ):
                isolated = history.evaluate(other_manifest, other_policy, left)
                self.assertEqual(isolated["recorded_exports"], 0)
                self.assertEqual(isolated["pages"][0]["previously_visible_but_now_hidden"], 0)
