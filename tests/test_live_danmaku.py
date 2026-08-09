import json
import os
import tempfile
import unittest
import zlib

from resources.lib.playback.live_danmaku import (
    LiveSubtitleBuffer,
    decode_bili_messages,
    encode_bili_packet,
    extract_live_comments,
    live_context_matches,
    read_live_context,
    write_live_context,
)


class LiveDanmakuTests(unittest.TestCase):
    def test_decodes_zlib_danmu_messages(self):
        message = {
            "cmd": "DANMU_MSG:4:0:2:2:2:0",
            "info": [[0, 1, 25, 0x12ABEF], "直播测试弹幕"],
        }
        inner = encode_bili_packet(
            json.dumps(message, ensure_ascii=False).encode("utf-8"), 5, 0
        )
        outer = encode_bili_packet(zlib.compress(inner), 5, 2)
        decoded = decode_bili_messages(outer)
        comments = extract_live_comments(decoded)
        self.assertEqual(1, len(comments))
        self.assertEqual("直播测试弹幕", comments[0]["text"])
        self.assertEqual(0x12ABEF, comments[0]["color"])

    def test_live_context_matches_only_the_recent_selected_stream(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = write_live_context(
                temp_dir,
                12345,
                "https://live-cdn.example/live/room.m3u8?token=secret",
            )
            loaded = read_live_context(temp_dir)
            self.assertEqual("12345", loaded["room_id"])
            self.assertNotIn("token", loaded)
            self.assertTrue(live_context_matches(
                context,
                "https://live-cdn.example/live/room.m3u8?token=changed",
                now=context["created"] + 10,
            ))
            self.assertFalse(live_context_matches(
                context,
                "https://other.example/live/room.m3u8",
                now=context["created"] + 10,
            ))
            self.assertFalse(live_context_matches(
                context,
                "https://live-cdn.example/live/room.m3u8",
                now=context["created"] + 121,
            ))
            self.assertTrue(live_context_matches(
                context,
                "https://live-cdn.example/live/room.m3u8",
                now=context["created"] + 3600,
                max_age=None,
            ))

    def test_alternating_native_ass_tracks_use_overlap_settings(self):
        comments = [
            {"mode": 1, "size": 25, "color": 0xFFFFFF, "text": "one"},
            {"mode": 1, "size": 25, "color": 0xFFFFFF, "text": "two"},
            {"mode": 1, "size": 25, "color": 0xFFFFFF, "text": "three"},
        ]
        settings = {
            "font_size": 60,
            "opacity": 0.85,
            "display_area": 0.2,
            "scroll": True,
            "top": True,
            "bottom": True,
            "avoid_overlap": True,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            buffer = LiveSubtitleBuffer(12345)
            buffer.add(comments, 10)
            first = buffer.render(temp_dir, 10, settings)
            buffer.add(comments, 20)
            second = buffer.render(temp_dir, 20, settings)
            self.assertNotEqual(first, second)
            self.assertTrue(os.path.isfile(first))
            with open(first, encoding="utf-8-sig") as handle:
                text = handle.read()
            self.assertEqual(2, text.count("Dialogue:"))

    def test_service_uses_native_subtitles_without_a_window(self):
        with open("service.py", encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("LiveDanmakuController", source)
        self.assertIn("setSubtitles(path)", source)
        self.assertIn("showSubtitles(True)", source)
        self.assertIn("self.subtitle_enable_at = now + 0.5", source)
        self.assertIn("max_age=None", source)
        self.assertNotIn("WindowXML", source)


if __name__ == "__main__":
    unittest.main()
