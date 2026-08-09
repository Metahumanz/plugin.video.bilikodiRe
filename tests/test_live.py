import unittest

from resources.lib.playback.live import (
    LivePlaybackError,
    PI4_LIVE_MAX_QN,
    live_variants,
    select_live_stream,
)


def play_info():
    def codec(name, qn, suffix):
        return {
            "codec_name": name,
            "current_qn": qn,
            "base_url": "/live/{}.m3u8".format(suffix),
            "url_info": [{"host": "https://cdn.example", "extra": "?token=ok"}],
        }

    return {
        "playurl_info": {"playurl": {
            "g_qn_desc": [
                {"qn": 20000, "desc": "4K"},
                {"qn": 15000, "desc": "2K"},
                {"qn": 10000, "desc": "原画"},
            ],
            "stream": [
            {
                "protocol_name": "http_stream",
                "format": [{"format_name": "flv", "codec": [codec("hevc", 10000, "flv-hevc")]}],
            },
            {
                "protocol_name": "http_hls",
                "format": [{
                    "format_name": "ts",
                    "codec": [
                        codec("avc", 10000, "ts-avc"),
                        codec("hevc", 400, "ts-hevc"),
                        codec("av1", 10000, "ts-av1"),
                    ],
                }],
            },
        ]}}
    }


class LiveStreamTests(unittest.TestCase):
    def test_flattens_signed_urls(self):
        variants = live_variants(play_info())
        self.assertEqual(4, len(variants))
        self.assertTrue(variants[0]["url"].endswith("?token=ok"))

    def test_prefers_hls_then_requested_codec_and_never_av1(self):
        hevc = select_live_stream(play_info(), "hevc")
        self.assertEqual(("http_hls", "hevc", "ts"), (
            hevc["protocol"], hevc["codec"], hevc["format"]
        ))
        avc = select_live_stream(play_info(), "avc")
        self.assertEqual("avc", avc["codec"])

    def test_rejects_empty_play_information(self):
        with self.assertRaises(LivePlaybackError):
            select_live_stream({})

    def test_selects_4k_hevc_and_labels_the_quality(self):
        info = play_info()
        codecs = info["playurl_info"]["playurl"]["stream"][1]["format"][0]["codec"]
        codecs.append({
            "codec_name": "hevc",
            "current_qn": PI4_LIVE_MAX_QN,
            "base_url": "/live/4k-hevc.m3u8",
            "url_info": [{"host": "https://cdn.example", "extra": "?token=ok"}],
        })
        selected = select_live_stream(info, "hevc")
        self.assertEqual(20000, selected["qn"])
        self.assertEqual("4K", selected["quality_desc"])

    def test_high_resolution_avc_is_not_pi4_compatible(self):
        info = play_info()
        codecs = info["playurl_info"]["playurl"]["stream"][1]["format"][0]["codec"]
        codecs.append({
            "codec_name": "avc",
            "current_qn": 20000,
            "base_url": "/live/4k-avc.m3u8",
            "url_info": [{"host": "https://cdn.example", "extra": "?token=ok"}],
        })
        selected = select_live_stream(info, "avc")
        self.assertEqual(10000, selected["qn"])
        self.assertEqual("avc", selected["codec"])


if __name__ == "__main__":
    unittest.main()
