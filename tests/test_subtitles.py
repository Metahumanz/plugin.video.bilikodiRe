import os
import tempfile
import unittest
from unittest.mock import patch

from resources.lib.playback.subtitles import (
    BilibiliSubtitleError,
    fetch_subtitle_tracks,
    prepare_bilibili_subtitles,
    subtitle_json_to_ass,
    subtitle_json_to_srt,
)


SAMPLE_SUBTITLE = {
    "body": [
        {"from": 0.125, "to": 1.5, "content": "第一行<br>第二行"},
        {"from": "65.2", "to": "67.004", "content": "Tom &amp; Jerry"},
        {"from": 70, "to": 69, "content": "invalid"},
        {"from": 80, "to": 81, "content": ""},
    ]
}


def view_payload(cid=456):
    return {
        "code": 0,
        "data": {"aid": 123456, "pages": [{"cid": cid, "part": "P1"}]},
    }


def fake_wbi_signer(params):
    signed = dict(params)
    signed.update({"wts": 1234567890, "w_rid": "signed-for-test"})
    return signed


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeAddon:
    def __init__(self, values=None):
        self.values = values or {}

    def getSetting(self, setting_id):
        return self.values.get(setting_id, "")


class BilibiliSubtitleTests(unittest.TestCase):
    def test_converts_bilibili_json_to_valid_srt(self):
        srt = subtitle_json_to_srt(SAMPLE_SUBTITLE)
        self.assertIn("00:00:00,125 --> 00:00:01,500", srt)
        self.assertIn("第一行\n第二行", srt)
        self.assertIn("00:01:05,200 --> 00:01:07,004", srt)
        self.assertIn("Tom & Jerry", srt)
        self.assertNotIn("invalid", srt)
        self.assertEqual(2, srt.count(" --> "))

    def test_player_api_uses_cookies_and_protocol_relative_urls(self):
        payload = {
            "code": 0,
            "data": {
                "subtitle": {
                    "subtitles": [
                        {
                            "id_str": "123",
                            "lan": "zh-Hans",
                            "lan_doc": "中文（简体）",
                            "subtitle_url": "//aisubtitle.hdslb.com/bfs/subtitle/a.json?auth_key=redacted",
                        }
                    ]
                }
            },
        }
        with patch(
            "requests.get",
            side_effect=[FakeResponse(view_payload()), FakeResponse(payload)],
        ) as request:
            tracks = fetch_subtitle_tracks(
                "BV-test",
                456,
                cookies={"SESSDATA": "secret"},
                wbi_signer=fake_wbi_signer,
            )
        self.assertEqual(1, len(tracks))
        self.assertEqual("中文（简体）", tracks[0]["language_name"])
        self.assertTrue(tracks[0]["url"].startswith("https://aisubtitle.hdslb.com/"))
        self.assertEqual(2, request.call_count)
        player_call = request.call_args_list[1]
        self.assertEqual(
            "https://api.bilibili.com/x/player/wbi/v2", player_call.args[0]
        )
        self.assertEqual(
            {"SESSDATA": "secret"}, player_call.kwargs["cookies"]
        )
        self.assertEqual(
            {
                "bvid": "BV-test",
                "cid": "456",
                "wts": 1234567890,
                "w_rid": "signed-for-test",
            },
            player_call.kwargs["params"],
        )

    def test_untrusted_subtitle_hosts_are_ignored(self):
        payload = {
            "code": 0,
            "data": {
                "subtitle": {
                    "subtitles": [
                        {
                            "lan": "zh-Hans",
                            "subtitle_url": "https://example.invalid/subtitle.json",
                        }
                    ]
                }
            },
        }
        with patch(
            "requests.get",
            side_effect=[FakeResponse(view_payload()), FakeResponse(payload)],
        ):
            self.assertEqual(
                [],
                fetch_subtitle_tracks(
                    "BV-test", 456, wbi_signer=fake_wbi_signer
                ),
            )

    def test_ai_language_prefix_maps_to_kodi_language(self):
        payload = {
            "code": 0,
            "data": {
                "subtitle": {
                    "subtitles": [
                        {
                            "id_str": "ai",
                            "lan": "ai-zh",
                            "lan_doc": "中文（自动生成）",
                            "ai_type": 1,
                            "subtitle_url": "//aisubtitle.hdslb.com/ai.json",
                        }
                    ]
                }
            },
        }
        with patch(
            "requests.get",
            side_effect=[FakeResponse(view_payload()), FakeResponse(payload)],
        ):
            tracks = fetch_subtitle_tracks(
                "BV-test", 456, wbi_signer=fake_wbi_signer
            )
        self.assertTrue(tracks[0]["is_ai"])
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "resources.lib.playback.subtitles.fetch_subtitle_tracks",
            return_value=tracks,
        ), patch(
            "resources.lib.playback.subtitles.fetch_subtitle_document",
            return_value=SAMPLE_SUBTITLE,
        ):
            paths = prepare_bilibili_subtitles(
                "BV-test", 456, temp_dir, FakeAddon()
            )
            self.assertEqual("中文（自动生成）.zh.srt", os.path.basename(paths[0]))
            self.assertEqual(
                os.path.join("bilibili-subtitles", "456", "ai"),
                os.path.relpath(os.path.dirname(paths[0]), temp_dir),
            )

    def test_prepare_writes_all_tracks_with_preferred_language_first(self):
        tracks = [
            {
                "index": 0,
                "id": "english",
                "language": "en-US",
                "language_name": "English",
                "url": "https://aisubtitle.hdslb.com/en.json",
            },
            {
                "index": 1,
                "id": "chinese",
                "language": "zh-Hans",
                "language_name": "中文",
                "url": "https://aisubtitle.hdslb.com/zh.json",
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "resources.lib.playback.subtitles.fetch_subtitle_tracks",
                return_value=tracks,
            ), patch(
                "resources.lib.playback.subtitles.fetch_subtitle_document",
                return_value=SAMPLE_SUBTITLE,
            ):
                paths = prepare_bilibili_subtitles(
                    "BV-test", 456, temp_dir, FakeAddon()
                )

            self.assertEqual(2, len(paths))
            self.assertEqual("中文.zh.srt", os.path.basename(paths[0]))
            self.assertEqual("English.en.srt", os.path.basename(paths[1]))
            for path in paths:
                self.assertTrue(os.path.isfile(path))
                with open(path, "r", encoding="utf-8-sig") as subtitle_file:
                    self.assertEqual(2, subtitle_file.read().count(" --> "))

    def test_official_track_keeps_native_danmaku_ass(self):
        danmaku = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Danmaku,Arial,36,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1.5,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 2,0:00:01.00,0:00:09.00,Danmaku,,0,0,0,,{\\move(1920,10,-100,10)}弹幕
"""
        combined = subtitle_json_to_ass(SAMPLE_SUBTITLE, danmaku)
        self.assertIn("Style: BilibiliSubtitle", combined)
        self.assertIn(",Danmaku,", combined)
        self.assertIn(",BilibiliSubtitle,", combined)
        self.assertIn("第一行\\N第二行", combined)
        self.assertEqual(3, combined.count("Dialogue:"))

    def test_prepare_combines_every_named_track_and_isolates_each_cid(self):
        tracks = [
            {
                "index": 0,
                "id": "human-zh",
                "language": "zh-Hans",
                "language_name": "中文（简体）",
                "url": "https://aisubtitle.hdslb.com/zh.json",
            }
        ]
        danmaku = """[Script Info]
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Danmaku,Arial,36,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1.5,0,7,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            danmaku_path = os.path.join(temp_dir, "danmaku.ass")
            with open(danmaku_path, "w", encoding="utf-8") as output:
                output.write(danmaku)
            with patch(
                "resources.lib.playback.subtitles.fetch_subtitle_tracks",
                return_value=tracks,
            ), patch(
                "resources.lib.playback.subtitles.fetch_subtitle_document",
                return_value=SAMPLE_SUBTITLE,
            ):
                first = prepare_bilibili_subtitles(
                    "BV-test", 456, temp_dir, FakeAddon(), danmaku_path=danmaku_path
                )[0]
                second = prepare_bilibili_subtitles(
                    "BV-test", 789, temp_dir, FakeAddon(), danmaku_path=danmaku_path
                )[0]
            self.assertEqual("中文（简体）.zh.ass", os.path.basename(first))
            self.assertEqual(os.path.basename(first), os.path.basename(second))
            self.assertNotEqual(os.path.dirname(first), os.path.dirname(second))
            with open(first, encoding="utf-8-sig") as source:
                combined = source.read()
            self.assertIn("Style: Danmaku", combined)
            self.assertIn("Style: BilibiliSubtitle", combined)

    def test_prepare_removes_stale_tracks_for_the_same_cid_only(self):
        track = {
            "index": 0,
            "id": "current",
            "language": "zh-Hans",
            "language_name": "中文（简体）",
            "url": "https://aisubtitle.hdslb.com/current.json",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            stale_dir = os.path.join(
                temp_dir, "bilibili-subtitles", "456", "stale"
            )
            other_cid_dir = os.path.join(
                temp_dir, "bilibili-subtitles", "789", "keep"
            )
            os.makedirs(stale_dir)
            os.makedirs(other_cid_dir)
            with open(os.path.join(stale_dir, "wrong.ass"), "w") as output:
                output.write("wrong video")
            with open(os.path.join(other_cid_dir, "keep.ass"), "w") as output:
                output.write("other video")
            with patch(
                "resources.lib.playback.subtitles.fetch_subtitle_tracks",
                return_value=[track],
            ), patch(
                "resources.lib.playback.subtitles.fetch_subtitle_document",
                return_value=SAMPLE_SUBTITLE,
            ):
                paths = prepare_bilibili_subtitles(
                    "BV-test", 456, temp_dir, FakeAddon()
                )
            self.assertFalse(os.path.exists(stale_dir))
            self.assertTrue(os.path.isfile(paths[0]))
            self.assertTrue(os.path.isfile(os.path.join(other_cid_dir, "keep.ass")))

    def test_disabled_setting_skips_network(self):
        with patch(
            "resources.lib.playback.subtitles.fetch_subtitle_tracks"
        ) as fetch:
            result = prepare_bilibili_subtitles(
                "BV-test",
                456,
                "unused",
                FakeAddon({"bili_subtitle_enabled": "false"}),
            )
        self.assertEqual([], result)
        fetch.assert_not_called()

    def test_rejects_cid_not_owned_by_current_bvid_before_player_request(self):
        with patch(
            "requests.get", return_value=FakeResponse(view_payload(cid=999))
        ) as request:
            with self.assertRaisesRegex(
                BilibiliSubtitleError, "CID 不属于请求的 BVID"
            ):
                fetch_subtitle_tracks(
                    "BV-test", 456, wbi_signer=fake_wbi_signer
                )
        self.assertEqual(1, request.call_count)

    def test_rejects_unsigned_player_request_without_legacy_fallback(self):
        with patch(
            "requests.get", return_value=FakeResponse(view_payload())
        ) as request:
            with self.assertRaisesRegex(BilibiliSubtitleError, "WBI 签名器"):
                fetch_subtitle_tracks("BV-test", 456)
        self.assertEqual(1, request.call_count)

    def test_playback_builds_official_tracks_from_current_danmaku(self):
        with open("addon.py", encoding="utf-8") as source:
            entrypoint = source.read()
        self.assertIn("danmaku_path=danmaku_subtitle", entrypoint)
        self.assertIn("wbi_signer=srt.getwbikey", entrypoint)
        self.assertIn(
            "([danmaku_subtitle] if danmaku_subtitle else []) + official_subtitles",
            entrypoint,
        )

    def test_empty_document_is_reported(self):
        with self.assertRaises(BilibiliSubtitleError):
            subtitle_json_to_srt({"body": []})


if __name__ == "__main__":
    unittest.main()
