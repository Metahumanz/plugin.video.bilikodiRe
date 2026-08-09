import ast
import unittest
from xml.etree import ElementTree as ET


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("addon.py", "r", encoding="utf-8") as addon_file:
            cls.addon_source = addon_file.read()
        with open("core/core.py", "r", encoding="utf-8") as core_file:
            cls.core_source = core_file.read()
        cls.addon_tree = ast.parse(cls.addon_source)
        cls.core_tree = ast.parse(cls.core_source)

    def test_all_video_lists_follow_the_global_click_setting(self):
        functions = {
            node.name: node
            for node in self.addon_tree.body
            if isinstance(node, ast.FunctionDef)
        }
        for function_name in ("fav_con", "feed_home"):
            function_source = ast.get_source_segment(
                self.addon_source, functions[function_name]
            )
            self.assertNotIn("direct_play=True", function_source)
        self.assertIn(
            'direct_play = ts.getSet("video_click_action") == "play"',
            self.core_source,
        )

    def test_direct_play_keeps_details_in_context_menu(self):
        functions = {
            node.name: node
            for node in self.core_tree.body
            if isinstance(node, ast.FunctionDef)
        }
        function = functions["get_viditem"]
        self.assertEqual(function.args.args[1].arg, "direct_play")
        self.assertIsNone(function.args.defaults[0].value)
        self.assertIn('("视频详情", "Container.Update({})".format(detail_url))', self.core_source)
        self.assertIn('"path": play_url if direct_play else detail_url', self.core_source)
        self.assertIn('"is_playable": bool(direct_play)', self.core_source)

    def test_click_setting_defaults_to_details(self):
        root = ET.parse("resources/settings.xml").getroot()
        setting = root.find(".//setting[@id='video_click_action']")
        self.assertIsNotNone(setting)
        self.assertEqual(setting.findtext("default"), "detail")
        values = [option.text for option in setting.findall("constraints/options/option")]
        self.assertEqual(values, ["detail", "play"])

    def test_detail_page_starts_with_native_play_item(self):
        self.assertIn('ts.ctxt("▶ 立即播放 · ", color="yellow")', self.addon_source)

    def test_favourites_skip_invalid_video_entries_without_aborting_page(self):
        functions = {
            node.name: node
            for node in self.addon_tree.body
            if isinstance(node, ast.FunctionDef)
        }
        function_source = ast.get_source_segment(
            self.addon_source, functions["fav_con"]
        )
        self.assertIn('_append_video(items, x)', function_source)
        self.assertIn('res.get("medias") or []', function_source)
        self.assertNotIn('items.append(c.get_viditem(x))', function_source)


if __name__ == "__main__":
    unittest.main()
