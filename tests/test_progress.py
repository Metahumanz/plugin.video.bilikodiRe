import tempfile
import unittest

from resources.lib.playback.progress import read_playback_context, write_playback_context


class ProgressContextTests(unittest.TestCase):
    def test_context_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            write_playback_context(temp_dir, "BV1test", 1234)
            context = read_playback_context(temp_dir)
        self.assertEqual("BV1test", context["bvid"])
        self.assertEqual("1234", context["cid"])


if __name__ == "__main__":
    unittest.main()
