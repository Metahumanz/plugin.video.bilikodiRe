import os
import tempfile
import unittest
from unittest.mock import patch

from resources.lib.playback.danmaku import generate_ass, parse_danmaku, prepare_danmaku


SAMPLE = b'''<?xml version="1.0" encoding="UTF-8"?>
<i>
  <d p="1.25,1,25,16711680,0,0,user,1">scroll {one}</d>
  <d p="2.0,5,25,65280,0,0,user,2">top</d>
  <d p="3.0,4,25,255,0,0,user,3">bottom</d>
  <d p="4.0,7,25,255,0,0,user,4">advanced ignored</d>
</i>'''


class DanmakuTests(unittest.TestCase):
    def test_parse_supported_modes(self):
        comments = parse_danmaku(SAMPLE)
        self.assertEqual([1, 5, 4], [comment["mode"] for comment in comments])

    def test_generate_ass_uses_kodi_subtitle_primitives(self):
        ass = generate_ass(
            parse_danmaku(SAMPLE), scroll=True, top=True, bottom=False, opacity=0.5
        )
        self.assertIn("[V4+ Styles]", ass)
        self.assertIn("\\move(", ass)
        self.assertIn("\\an8\\pos", ass)
        self.assertIn("\\alpha&H80&", ass)
        self.assertIn("&H80000000", ass)
        self.assertNotIn("bottom", ass)
        self.assertIn("scroll \\{one\\}", ass)

    def test_all_modes_share_lanes_and_overflow_is_discarded(self):
        comments = [
            {"time": 1.0, "mode": 1, "size": 25, "color": 0xFFFFFF, "text": "scroll"},
            {"time": 1.1, "mode": 5, "size": 25, "color": 0xFFFFFF, "text": "top"},
            {"time": 1.2, "mode": 4, "size": 25, "color": 0xFFFFFF, "text": "bottom"},
        ]
        ass = generate_ass(
            comments,
            height=100,
            font_size=60,
            display_area=0.2,
            avoid_overlap=True,
        )
        dialogues = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(1, len(dialogues))

    def test_overlap_can_be_disabled_for_compatibility(self):
        comments = [
            {"time": 1.0, "mode": 1, "size": 25, "color": 0xFFFFFF, "text": "one"},
            {"time": 1.1, "mode": 1, "size": 25, "color": 0xFFFFFF, "text": "two"},
        ]
        ass = generate_ass(
            comments,
            height=100,
            font_size=60,
            display_area=0.2,
            avoid_overlap=False,
        )
        self.assertEqual(2, ass.count("Dialogue:"))

    def test_same_lane_accepts_multiple_non_colliding_scrolling_comments(self):
        comments = [
            {"time": 1.0, "mode": 1, "size": 25, "color": 0xFFFFFF, "text": "one"},
            {"time": 3.0, "mode": 1, "size": 25, "color": 0xFFFFFF, "text": "two"},
        ]
        ass = generate_ass(
            comments,
            width=1000,
            height=100,
            font_size=60,
            display_area=0.2,
            avoid_overlap=True,
            scroll_duration=8.0,
        )
        dialogues = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(2, len(dialogues))
        self.assertIn("\\move(1000,10", dialogues[0])
        self.assertIn("\\move(1000,10", dialogues[1])

    def test_same_lane_still_rejects_entry_and_catchup_collisions(self):
        comments = [
            {"time": 1.0, "mode": 1, "size": 25, "color": 0xFFFFFF, "text": "short"},
            {
                "time": 1.2,
                "mode": 1,
                "size": 25,
                "color": 0xFFFFFF,
                "text": "a much longer following comment",
            },
        ]
        ass = generate_ass(
            comments,
            width=1000,
            height=100,
            font_size=60,
            display_area=0.2,
            avoid_overlap=True,
        )
        self.assertEqual(1, ass.count("Dialogue:"))

    def test_prepared_track_has_a_stable_kodi_name_and_language(self):
        class Addon:
            def getSetting(self, setting_id):
                return "true" if setting_id == "danmaku_enabled" else ""

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "resources.lib.playback.danmaku.fetch_danmaku_xml", return_value=SAMPLE
        ):
            path = prepare_danmaku(12345, temp_dir, Addon())
            self.assertEqual("Bilibili Danmaku.zh.ass", os.path.basename(path))
            self.assertEqual(
                os.path.join("bilibili-danmaku", "12345"),
                os.path.relpath(os.path.dirname(path), temp_dir),
            )
            self.assertTrue(os.path.isfile(path))

if __name__ == "__main__":
    unittest.main()
