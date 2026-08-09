import unittest
from pathlib import Path

from resources.lib.dynamic_feed import format_dynamic_time, normalize_dynamic


class DynamicFeedTests(unittest.TestCase):
    def test_relative_time(self):
        self.assertEqual("刚刚", format_dynamic_time(995, now=1000))
        self.assertEqual("5分钟前", format_dynamic_time(700, now=1000))
        self.assertEqual("2小时前", format_dynamic_time(1000, now=8200))

    def test_normalizes_archive_and_makes_remote_friendly_label(self):
        dynamic = {"modules": {
            "module_author": {"name": "测试UP", "mid": 42, "pub_ts": 1000},
            "module_dynamic": {
                "desc": {"text": "动态附言"},
                "major": {"archive": {
                    "bvid": "BV1TEST",
                    "title": "测试视频",
                    "cover": "https://example/cover.jpg",
                    "duration_text": "3:20",
                    "desc": "视频简介",
                    "stat": {"play": 123},
                }},
            },
        }}
        result = normalize_dynamic(dynamic, now=1060)
        self.assertEqual("1分钟前 · 测试UP · 测试视频", result["label"])
        self.assertEqual(1000, result["video"]["pubdate"])
        self.assertEqual("动态附言\n\n视频简介", result["video"]["desc"])

    def test_first_dynamic_page_includes_followed_live_rooms(self):
        source = Path("addon.py").read_text(encoding="utf-8")
        dynamic_source = source[source.index("def dynamic_feed"):source.index("#  User/用户/Up主 路由")]
        self.assertIn("_following_live_rooms()", dynamic_source)
        self.assertIn('ts.ctxt("直播中", color="red")', dynamic_source)


if __name__ == "__main__":
    unittest.main()
