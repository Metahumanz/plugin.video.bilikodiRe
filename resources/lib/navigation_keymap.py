"""Install the add-on's narrow Videos-window navigation keymap."""

import os
from xml.etree import ElementTree as ET


KEYMAP_SOURCE = os.path.join("resources", "keymaps", "bilikodi-navigation.xml")
KEYMAP_FILENAME = "plugin.video.bilikodiRe-navigation.xml"


def _render_keymap(source_path, parent_back_enabled, stop_video_on_exit):
    tree = ET.parse(source_path)
    root = tree.getroot()
    if not parent_back_enabled:
        videos = root.find("Videos")
        if videos is not None:
            root.remove(videos)
    if not stop_video_on_exit:
        fullscreen = root.find("FullscreenVideo")
        if fullscreen is not None:
            root.remove(fullscreen)
    if not list(root):
        return None
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def sync_navigation_keymap(
    addon_dir, profile_dir, enabled=True, stop_video_on_exit=True
):
    """Create/update our dedicated userdata keymap and return ``(changed, path)``."""
    target_dir = os.path.join(profile_dir, "keymaps")
    target_path = os.path.join(target_dir, KEYMAP_FILENAME)

    source_path = os.path.join(addon_dir, KEYMAP_SOURCE)
    desired = _render_keymap(source_path, enabled, stop_video_on_exit)
    if desired is None:
        try:
            os.remove(target_path)
            return True, target_path
        except FileNotFoundError:
            return False, target_path

    try:
        with open(target_path, "rb") as target_file:
            if target_file.read() == desired:
                return False, target_path
    except FileNotFoundError:
        pass

    os.makedirs(target_dir, exist_ok=True)
    temporary_path = target_path + ".tmp"
    with open(temporary_path, "wb") as target_file:
        target_file.write(desired)
    os.replace(temporary_path, target_path)
    return True, target_path


__all__ = ["KEYMAP_FILENAME", "sync_navigation_keymap"]
