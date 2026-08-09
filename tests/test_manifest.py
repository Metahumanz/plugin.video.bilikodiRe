import unittest
from xml.etree import ElementTree as ET


class AddonManifestTests(unittest.TestCase):
    def test_kodi_entrypoint_and_dependencies(self):
        root = ET.parse("addon.xml").getroot()
        extension = root.find("./extension[@point='xbmc.python.pluginsource']")
        self.assertIsNotNone(extension)
        self.assertEqual("addon.py", extension.attrib["library"])
        service = root.find("./extension[@point='xbmc.service']")
        self.assertIsNotNone(service)
        self.assertEqual("service.py", service.attrib["library"])
        imports = {
            item.attrib["addon"]: item.attrib["version"]
            for item in root.findall("./requires/import")
        }
        self.assertIn("inputstream.adaptive", imports)
        self.assertGreaterEqual(tuple(map(int, imports["xbmc.python"].split("."))), (3, 0, 0))

    def test_settings_xml_is_well_formed(self):
        root = ET.parse("resources/settings.xml").getroot()
        defaults = {
            setting.attrib["id"]: setting.findtext("default")
            for setting in root.findall(".//setting")
        }
        self.assertEqual("highest", defaults["video_quality"])
        self.assertEqual("hevc", defaults["video_codec"])
        self.assertEqual("false", defaults["allow_av1"])
        self.assertEqual("true", defaults["danmaku_enabled"])
        self.assertEqual("true", defaults["danmaku_avoid_overlap"])
        self.assertEqual("true", defaults["rec_history"])
        self.assertEqual("true", defaults["stop_video_on_home"])
        self.assertEqual("true", defaults["stop_video_on_back"])


if __name__ == "__main__":
    unittest.main()
