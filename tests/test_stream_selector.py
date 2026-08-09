import unittest

from resources.lib.playback.stream_selector import (
    StreamSelectionError,
    codec_name,
    dynamic_range_name,
    frame_rate,
    hevc_profile,
    quality_cap,
    select_audio_stream,
    select_video_stream,
)


def video(qn, codec, codecid, height, fps, bandwidth):
    return {
        "id": qn,
        "codecid": codecid,
        "codecs": codec,
        "width": 3840 if height == 2160 else 1920 if height == 1080 else 1280,
        "height": height,
        "frameRate": fps,
        "bandwidth": bandwidth,
    }


class StreamSelectorTests(unittest.TestCase):
    def setUp(self):
        self.streams = [
            video(120, "avc1.640033", 7, 2160, "60000/1001", 25_000_000),
            video(116, "hev1.1.6.L150.90", 12, 1080, "60", 8_000_000),
            video(120, "hev1.1.6.L153.90", 12, 2160, "30", 18_000_000),
            video(120, "hev1.1.6.L153.90", 12, 2160, "60000/1001", 28_000_000),
            video(120, "av01.0.12M.08", 13, 2160, "60", 20_000_000),
        ]

    def test_highest_prefers_4k60_hevc(self):
        selected = select_video_stream(self.streams)
        self.assertEqual("hevc", codec_name(selected))
        self.assertEqual(2160, selected["height"])
        self.assertGreater(frame_rate(selected), 59)

    def test_highest_selects_qn125_hevc_main10_hdr(self):
        hdr = video(125, "hvc1.2.4.L153.0", 12, 2160, "60", 18_000_000)
        selected = select_video_stream(self.streams + [hdr])
        self.assertEqual(hdr, selected)
        self.assertEqual("hevc", codec_name(selected))
        self.assertEqual(2, hevc_profile(selected))
        self.assertEqual("hdr", dynamic_range_name(selected))

    def test_highest_cap_includes_hdr_but_4k_remains_sdr_tier(self):
        hdr = video(125, "hev1.2.4.L153.90", 12, 2160, "30", 18_000_000)
        self.assertEqual(125, quality_cap("highest"))
        self.assertEqual(125, quality_cap("auto"))
        self.assertEqual(120, quality_cap("4k"))
        selected = select_video_stream(self.streams + [hdr], quality="4k")
        self.assertEqual(120, selected["id"])
        self.assertEqual("sdr", dynamic_range_name(selected))

    def test_qn125_av1_is_never_treated_as_pi4_hdr(self):
        hdr_av1 = video(125, "av01.0.12M.10", 13, 2160, "60", 18_000_000)
        selected = select_video_stream(
            [hdr_av1, self.streams[2]], allow_av1=True
        )
        self.assertEqual(self.streams[2], selected)

    def test_qn125_requires_an_explicit_hevc_main10_profile(self):
        hdr_main = video(125, "hev1.1.6.L153.90", 12, 2160, "30", 18_000_000)
        selected = select_video_stream([hdr_main, self.streams[2]])
        self.assertEqual(self.streams[2], selected)

    def test_qn125_over_60fps_falls_back(self):
        hdr_too_fast = video(
            125, "hev1.2.4.L153.90", 12, 2160, "62.5", 18_000_000
        )
        selected = select_video_stream([hdr_too_fast, self.streams[2]])
        self.assertEqual(self.streams[2], selected)

    def test_hevc_preference_is_before_avc_quality(self):
        streams = [self.streams[0], self.streams[1]]
        selected = select_video_stream(streams)
        self.assertEqual("hevc", codec_name(selected))
        self.assertEqual(1080, selected["height"])

    def test_sub_720_hevc_does_not_beat_4k_avc(self):
        low_hevc = video(32, "hev1.1.6.L90.90", 12, 480, "30", 1_000_000)
        selected = select_video_stream([low_hevc, self.streams[0]])
        self.assertEqual("avc", codec_name(selected))
        self.assertEqual(2160, selected["height"])

    def test_below_720_uses_quality_before_codec(self):
        low_hevc = video(16, "hev1.1.6.L90.90", 12, 360, "30", 300_000)
        higher_avc = video(32, "avc1.64001F", 7, 480, "30", 700_000)
        selected = select_video_stream([low_hevc, higher_avc])
        self.assertEqual("avc", codec_name(selected))
        self.assertEqual(32, selected["id"])

    def test_avc_preference_can_be_selected(self):
        selected = select_video_stream(self.streams, codec_preference="avc")
        self.assertEqual("avc", codec_name(selected))
        self.assertEqual(2160, selected["height"])

    def test_1080p60_cap_downgrades_from_4k(self):
        selected = select_video_stream(self.streams, quality="1080p60")
        self.assertEqual(116, selected["id"])

    def test_1080p_means_normal_qn_80(self):
        streams = self.streams + [
            video(80, "hev1.1.6.L120.90", 12, 1080, "30", 5_000_000),
        ]
        selected = select_video_stream(streams, quality="1080p")
        self.assertEqual(80, selected["id"])

    def test_4k120_falls_back_to_1080p60_hevc(self):
        too_fast = video(
            120, "hev1.1.6.L183.90", 12, 2160, "120", 20_000_000
        )
        selected = select_video_stream([too_fast, self.streams[1]])
        self.assertEqual(116, selected["id"])
        self.assertEqual(60.0, frame_rate(selected))

    def test_slightly_over_60_report_is_tolerated(self):
        near_sixty = video(
            120, "hev1.1.6.L153.90", 12, 2160, "60.001", 18_000_000
        )
        selected = select_video_stream([near_sixty])
        self.assertEqual(near_sixty, selected)

    def test_only_120fps_streams_are_rejected(self):
        too_fast = video(
            120, "hev1.1.6.L183.90", 12, 2160, "120", 20_000_000
        )
        with self.assertRaises(StreamSelectionError):
            select_video_stream([too_fast])

    def test_quality_fallback_can_be_disabled(self):
        with self.assertRaises(StreamSelectionError):
            select_video_stream(
                [self.streams[1]], quality="4k", quality_fallback=False
            )

    def test_codec_compatibility_fallback_can_be_disabled(self):
        with self.assertRaises(StreamSelectionError):
            select_video_stream(
                [self.streams[0]], codec_preference="hevc", auto_compatible=False
            )

    def test_av1_is_disabled_by_default(self):
        with self.assertRaises(StreamSelectionError):
            select_video_stream([self.streams[-1]])

    def test_av1_can_only_be_enabled_explicitly(self):
        selected = select_video_stream([self.streams[-1]], allow_av1=True)
        self.assertEqual("av1", codec_name(selected))

    def test_audio_selects_highest_regular_aac(self):
        streams = [
            {"id": 30216, "codecs": "mp4a.40.2", "bandwidth": 64_000},
            {"id": 30280, "codecs": "mp4a.40.2", "bandwidth": 192_000},
            {"id": 30250, "codecs": "ec-3", "bandwidth": 384_000},
        ]
        self.assertEqual(30280, select_audio_stream(streams)["id"])


if __name__ == "__main__":
    unittest.main()
