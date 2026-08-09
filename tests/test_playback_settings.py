import unittest

from resources.lib.playback.settings import playback_settings


class FakeAddon:
    def __init__(self, values=None):
        self.values = values or {}

    def getSetting(self, name):
        return self.values.get(name, "")


class PlaybackSettingsTests(unittest.TestCase):
    def test_pi4_safe_defaults(self):
        settings = playback_settings(FakeAddon())
        self.assertEqual("highest", settings["quality"])
        self.assertEqual(127, settings["request_qn"])
        self.assertEqual("hevc", settings["codec_preference"])
        self.assertFalse(settings["allow_av1"])
        self.assertTrue(settings["quality_fallback"])

    def test_user_choices_are_mapped_to_api_values(self):
        settings = playback_settings(
            FakeAddon({"video_quality": "1080p", "video_codec": "avc", "allow_av1": "true"})
        )
        self.assertEqual(80, settings["request_qn"])
        self.assertEqual("avc", settings["codec_preference"])
        self.assertTrue(settings["allow_av1"])


if __name__ == "__main__":
    unittest.main()
