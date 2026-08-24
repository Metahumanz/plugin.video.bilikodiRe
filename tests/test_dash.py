import os
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from xml.etree import ElementTree as ET

from resources.lib.playback.dash import (
    DashPlaybackError,
    build_stream_headers,
    generate_mpd,
    play_dash,
)
from resources.lib.playback.manifest_server import (
    create_server,
    remove_port_file,
    write_port_file,
)
from urllib.request import urlopen


def sample_dash():
    segment = {"Initialization": "0-999", "indexRange": "1000-1200"}
    return {
        "duration": 123.456,
        "minBufferTime": 1.5,
        "video": [
            {
                "id": 120,
                "codecid": 12,
                "codecs": "hev1.1.6.L153.90",
                "width": 3840,
                "height": 2160,
                "frameRate": "60000/1001",
                "bandwidth": 20_000_000,
                "baseUrl": "https://example.test/video.m4s?a=1&b=2",
                "SegmentBase": segment,
            },
            {
                "id": 120,
                "codecid": 13,
                "codecs": "av01.0.12M.08",
                "width": 3840,
                "height": 2160,
                "frameRate": "60",
                "bandwidth": 18_000_000,
                "baseUrl": "https://example.test/av1.m4s",
                "SegmentBase": segment,
            },
        ],
        "audio": [
            {
                "id": 30280,
                "codecs": "mp4a.40.2",
                "bandwidth": 192_000,
                "base_url": "https://example.test/audio.m4s?x=1&y=2",
                "segment_base": {
                    "initialization": "0-900",
                    "index_range": "901-1100",
                },
            }
        ],
    }


class DashTests(unittest.TestCase):
    def test_generate_mpd_has_one_video_and_one_audio(self):
        mpd = generate_mpd(sample_dash())
        root = ET.fromstring(mpd)
        ns = {"d": "urn:mpeg:dash:schema:mpd:2011"}
        representations = root.findall(".//d:Representation", ns)
        self.assertEqual(2, len(representations))
        self.assertEqual("hev1.1.6.L153.90", representations[0].attrib["codecs"])
        self.assertEqual("mp4a.40.2", representations[1].attrib["codecs"])
        urls = [element.text for element in root.findall(".//d:BaseURL", ns)]
        self.assertEqual("https://example.test/video.m4s?a=1&b=2", urls[0])
        self.assertEqual("https://example.test/audio.m4s?x=1&y=2", urls[1])
        self.assertEqual("PT123.456S", root.attrib["mediaPresentationDuration"])

    def test_generate_mpd_rejects_missing_segment_base(self):
        dash = sample_dash()
        del dash["video"][0]["SegmentBase"]
        with self.assertRaises(DashPlaybackError):
            generate_mpd(dash)

    def test_headers_are_url_encoded_and_include_cookie(self):
        parsed = parse_qs(build_stream_headers({"SESSDATA": "a+b/c=="}))
        self.assertEqual(["https://www.bilibili.com/"], parsed["Referer"])
        self.assertEqual(["SESSDATA=a+b/c=="], parsed["Cookie"])

    def test_play_dash_resolves_a_kodi_list_item(self):
        captured = {}

        class KodiListItem:
            def __init__(self, path):
                self.path = path
                self.properties = {}
                self.subtitles = []

            def setMimeType(self, value):
                self.mime_type = value

            def setContentLookup(self, value):
                self.content_lookup = value

            def setProperty(self, name, value):
                self.properties[name] = value

            def setSubtitles(self, paths):
                self.subtitles = list(paths)

        class SwiftListItem:
            def __init__(self, path, offscreen=False):
                self.path = path
                self.offscreen = offscreen
                self.native = KodiListItem(path)

            def as_xbmc_listitem(self):
                return self.native

            def as_tuple(self):
                return self.path, self.native, False

        class Plugin:
            def __init__(self):
                self.end_of_directory = False

            def set_resolved_url(self, item, subtitles=None):
                self.end_of_directory = True
                captured.update(item=item, subtitles=subtitles)

        xbmcswift2 = types.ModuleType("xbmcswift2")
        xbmcswift2.ListItem = SwiftListItem
        plugin = Plugin()

        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server(temp_dir)
            port = server.server_address[1]
            write_port_file(temp_dir, port)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            try:
                with patch.dict("sys.modules", {"xbmcswift2": xbmcswift2}):
                    result = play_dash(
                        sample_dash(), temp_dir, 12345, plugin=plugin,
                        subtitles=["/tmp/comments.ass", "/tmp/official.zh.srt"]
                    )
                self.assertTrue(os.path.exists(result["mpd_path"]))
                self.assertEqual("sdr", result["dynamic_range"])
                with urlopen(captured["item"].path, timeout=2) as response:
                    self.assertEqual("application/dash+xml", response.headers.get_content_type())
                    ET.fromstring(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)
                remove_port_file(temp_dir, expected_port=port)

        item = captured["item"]
        kodi_item = item.as_xbmc_listitem()
        self.assertTrue(plugin.end_of_directory)
        self.assertTrue(item.path.startswith("http://127.0.0.1:"))
        self.assertEqual("application/dash+xml", kodi_item.mime_type)
        self.assertFalse(kodi_item.content_lookup)
        self.assertEqual("inputstream.adaptive", kodi_item.properties["inputstream"])
        self.assertNotIn("inputstream.adaptive.manifest_type", kodi_item.properties)
        self.assertIsNone(captured["subtitles"])
        self.assertEqual(
            ["/tmp/comments.ass", "/tmp/official.zh.srt"], kodi_item.subtitles
        )


if __name__ == "__main__":
    unittest.main()
