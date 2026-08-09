import os
import tempfile
import unittest
from xml.etree import ElementTree as ET

from resources.lib.navigation_keymap import (
    KEYMAP_FILENAME,
    sync_navigation_keymap,
)


class NavigationKeymapTests(unittest.TestCase):
    def test_keymap_only_changes_video_browser_back_actions(self):
        tree = ET.parse("resources/keymaps/bilikodi-navigation.xml")
        root = tree.getroot()
        self.assertIsNotNone(root.find("Videos"))
        self.assertEqual(root.findtext("Videos/remote/back"), "ParentDir")
        for key in ("backspace", "browser_back", "escape"):
            self.assertEqual(root.findtext("Videos/keyboard/{}".format(key)), "ParentDir")
        self.assertEqual(root.findtext("FullscreenVideo/remote/back"), "Stop")
        for key in ("backspace", "browser_back", "escape"):
            self.assertEqual(root.findtext("FullscreenVideo/keyboard/{}".format(key)), "Stop")

    def test_keymap_install_is_idempotent_and_can_be_disabled(self):
        addon_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as profile_dir:
            changed, target = sync_navigation_keymap(addon_dir, profile_dir)
            self.assertTrue(changed)
            self.assertEqual(os.path.basename(target), KEYMAP_FILENAME)
            self.assertTrue(os.path.isfile(target))

            changed, same_target = sync_navigation_keymap(addon_dir, profile_dir)
            self.assertFalse(changed)
            self.assertEqual(same_target, target)

            changed, _ = sync_navigation_keymap(
                addon_dir,
                profile_dir,
                enabled=False,
                stop_video_on_exit=False,
            )
            self.assertTrue(changed)
            self.assertFalse(os.path.exists(target))

    def test_parent_and_fullscreen_behaviors_can_be_configured_separately(self):
        addon_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as profile_dir:
            _, target = sync_navigation_keymap(
                addon_dir, profile_dir, enabled=False, stop_video_on_exit=True
            )
            root = ET.parse(target).getroot()
            self.assertIsNone(root.find("Videos"))
            self.assertIsNotNone(root.find("FullscreenVideo"))

            sync_navigation_keymap(
                addon_dir, profile_dir, enabled=True, stop_video_on_exit=False
            )
            root = ET.parse(target).getroot()
            self.assertIsNotNone(root.find("Videos"))
            self.assertIsNone(root.find("FullscreenVideo"))


if __name__ == "__main__":
    unittest.main()
