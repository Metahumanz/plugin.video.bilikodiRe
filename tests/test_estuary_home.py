import tempfile
import unittest
from pathlib import Path

from tools.install_estuary_bilikodi import CUSTOM_SKIN_ID, install_skin


HOME_XML = """<window>
\t<controls>
\t\t\t\t<control type="group" id="15000">
\t\t\t\t</control>
\t\t\t\t\t\t<item>
\t\t\t\t\t\t\t<label>$LOCALIZE[3]</label>
\t\t\t\t\t\t\t<property name="id">video</property>
\t\t\t\t\t\t</item>
\t\t\t\t\t\t<item>
\t\t\t\t\t\t\t<label>$LOCALIZE[10134]</label>
\t\t\t\t\t\t\t<property name="id">favorites</property>
\t\t\t\t\t\t</item>
\t\t\t\t\t\t<item>
\t\t\t\t\t\t\t<label>$LOCALIZE[8]</label>
\t\t\t\t\t\t</item>
\t</controls>
</window>
"""


class EstuaryHomeInstallerTests(unittest.TestCase):
    def test_installs_user_skin_and_preserves_menu_order_and_settings(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "skin.estuary"
            (source / "xml").mkdir(parents=True)
            (source / "addon.xml").write_text(
                '<addon id="skin.estuary" version="4.0.0" name="Estuary"/>',
                encoding="utf-8",
            )
            (source / "xml" / "Home.xml").write_text(HOME_XML, encoding="utf-8")
            source_settings = root / "old-settings.xml"
            source_settings.write_text("<settings/>", encoding="utf-8")
            target = root / CUSTOM_SKIN_ID
            target_settings = root / "addon_data" / CUSTOM_SKIN_ID / "settings.xml"

            installed, backup = install_skin(
                source, target, source_settings, target_settings
            )

            self.assertEqual(installed, target.resolve())
            self.assertIsNone(backup)
            addon_xml = (target / "addon.xml").read_text(encoding="utf-8")
            self.assertIn('id="{}"'.format(CUSTOM_SKIN_ID), addon_xml)
            home_xml = (target / "xml" / "Home.xml").read_text(encoding="utf-8")
            self.assertIn('name="id">bilibili</property>', home_xml)
            self.assertIn("plugin://plugin.video.bilikodiRe/", home_xml)
            self.assertIn('<control type="panel" id="22100">', home_xml)
            self.assertIn('<property name="menu_id">$NUMBER[22100]</property>', home_xml)
            self.assertNotIn('content="WidgetListCategories"', home_xml)
            favorites_position = home_xml.index(
                '<property name="id">favorites</property>'
            )
            bilibili_position = home_xml.rindex(
                '<property name="id">bilibili</property>'
            )
            weather_position = home_xml.index("$LOCALIZE[8]")
            self.assertLess(favorites_position, bilibili_position)
            self.assertLess(bilibili_position, weather_position)
            self.assertEqual(target_settings.read_text(encoding="utf-8"), "<settings/>")

            _, backup = install_skin(
                source, target, source_settings, target_settings
            )
            self.assertIsNotNone(backup)
            self.assertNotEqual(backup.parent, target.parent)
            self.assertTrue((backup / "addon.xml").is_file())


if __name__ == "__main__":
    unittest.main()
