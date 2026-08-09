#!/usr/bin/env python3
"""Install a user-level Estuary variant with a Bilibili Home menu entry.

The system skin is only read.  The derived add-on is written below the Kodi
user profile so package updates and removal remain safe.
"""

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path


CUSTOM_SKIN_ID = "skin.estuary.bilikodi"
PATCH_MARKER = "PiBiliOnKodi home entry"
PLUGIN_URL = "plugin://plugin.video.bilikodiRe/"


BILIBILI_WIDGET = """\
\t\t\t\t<!-- PiBiliOnKodi home entry -->
\t\t\t\t<control type="group" id="22000">
\t\t\t\t\t<visible>String.IsEqual(Container(9000).ListItem.Property(id),bilibili)</visible>
\t\t\t\t\t<include content="Visible_Right_Delayed">
\t\t\t\t\t\t<param name="id" value="bilibili"/>
\t\t\t\t\t</include>
\t\t\t\t\t<include content="CategoryLabel">
\t\t\t\t\t\t<param name="label" value="哔哩哔哩"/>
\t\t\t\t\t\t<param name="list_id" value="22100"/>
\t\t\t\t\t</include>
\t\t\t\t\t<include content="BusyListSpinner">
\t\t\t\t\t\t<param name="list_id" value="22100"/>
\t\t\t\t\t</include>
\t\t\t\t\t<control type="panel" id="22100">
\t\t\t\t\t\t<left>65</left>
\t\t\t\t\t\t<top>170</top>
\t\t\t\t\t\t<right>45</right>
\t\t\t\t\t\t<bottom>55</bottom>
\t\t\t\t\t\t<orientation>vertical</orientation>
\t\t\t\t\t\t<onleft>9000</onleft>
\t\t\t\t\t\t<onright>22100</onright>
\t\t\t\t\t\t<onup>22100</onup>
\t\t\t\t\t\t<ondown>22100</ondown>
\t\t\t\t\t\t<pagecontrol>22010</pagecontrol>
\t\t\t\t\t\t<preloaditems>8</preloaditems>
\t\t\t\t\t\t<scrolltime tween="cubic" easing="out">350</scrolltime>
\t\t\t\t\t\t<visible>Integer.IsGreater(Container(22100).NumItems,0) | Container(22100).IsUpdating</visible>
\t\t\t\t\t\t<itemlayout width="320" height="205">
\t\t\t\t\t\t\t<control type="group">
\t\t\t\t\t\t\t\t<left>8</left>
\t\t\t\t\t\t\t\t<top>8</top>
\t\t\t\t\t\t\t\t<control type="image">
\t\t\t\t\t\t\t\t\t<width>300</width><height>185</height>
\t\t\t\t\t\t\t\t\t<texture>dialogs/dialog-bg-nobo.png</texture>
\t\t\t\t\t\t\t\t\t<bordertexture border="21" infill="false">overlays/shadow.png</bordertexture>
\t\t\t\t\t\t\t\t\t<bordersize>20</bordersize>
\t\t\t\t\t\t\t\t</control>
\t\t\t\t\t\t\t\t<control type="image">
\t\t\t\t\t\t\t\t\t<left>105</left><top>20</top><width>90</width><height>78</height>
\t\t\t\t\t\t\t\t\t<texture fallback="DefaultFolder.png">$INFO[ListItem.Icon]</texture>
\t\t\t\t\t\t\t\t\t<aspectratio>keep</aspectratio>
\t\t\t\t\t\t\t\t</control>
\t\t\t\t\t\t\t\t<control type="textbox">
\t\t\t\t\t\t\t\t\t<left>25</left><top>105</top><width>250</width><height>58</height>
\t\t\t\t\t\t\t\t\t<label>$INFO[ListItem.Label]</label>
\t\t\t\t\t\t\t\t\t<font>font25_narrow</font><align>center</align><aligny>center</aligny>
\t\t\t\t\t\t\t\t\t<shadowcolor>text_shadow</shadowcolor>
\t\t\t\t\t\t\t\t</control>
\t\t\t\t\t\t\t</control>
\t\t\t\t\t\t</itemlayout>
\t\t\t\t\t\t<focusedlayout width="320" height="205">
\t\t\t\t\t\t\t<control type="group">
\t\t\t\t\t\t\t\t<left>8</left><top>8</top><depth>DepthContentPopout</depth>
\t\t\t\t\t\t\t\t<animation type="Focus"><effect type="zoom" start="100" end="108" time="160" center="158,98"/></animation>
\t\t\t\t\t\t\t\t<animation type="Unfocus"><effect type="zoom" start="108" end="100" time="160" center="158,98"/></animation>
\t\t\t\t\t\t\t\t<control type="image">
\t\t\t\t\t\t\t\t\t<width>300</width><height>185</height>
\t\t\t\t\t\t\t\t\t<texture>dialogs/dialog-bg-nobo.png</texture>
\t\t\t\t\t\t\t\t\t<bordertexture border="21" infill="false">overlays/shadow.png</bordertexture><bordersize>20</bordersize>
\t\t\t\t\t\t\t\t</control>
\t\t\t\t\t\t\t\t<control type="image">
\t\t\t\t\t\t\t\t\t<width>300</width><height>185</height>
\t\t\t\t\t\t\t\t\t<texture colordiffuse="button_focus">colors/grey.png</texture><bordersize>20</bordersize>
\t\t\t\t\t\t\t\t\t<include>Animation_FocusTextureFade</include>
\t\t\t\t\t\t\t\t</control>
\t\t\t\t\t\t\t\t<control type="image">
\t\t\t\t\t\t\t\t\t<left>105</left><top>20</top><width>90</width><height>78</height>
\t\t\t\t\t\t\t\t\t<texture fallback="DefaultFolder.png">$INFO[ListItem.Icon]</texture><aspectratio>keep</aspectratio>
\t\t\t\t\t\t\t\t</control>
\t\t\t\t\t\t\t\t<control type="textbox">
\t\t\t\t\t\t\t\t\t<left>25</left><top>105</top><width>250</width><height>58</height>
\t\t\t\t\t\t\t\t\t<label>$INFO[ListItem.Label]</label>
\t\t\t\t\t\t\t\t\t<font>font25_narrow</font><align>center</align><aligny>center</aligny><shadowcolor>text_shadow</shadowcolor>
\t\t\t\t\t\t\t\t</control>
\t\t\t\t\t\t\t</control>
\t\t\t\t\t\t</focusedlayout>
\t\t\t\t\t\t<content target="videos" limit="20">plugin://plugin.video.bilikodiRe/</content>
\t\t\t\t\t</control>
\t\t\t\t\t<include content="ImageWidget">
\t\t\t\t\t\t<param name="text_label" value="哔哩哔哩" />
\t\t\t\t\t\t<param name="button_label" value="打开" />
\t\t\t\t\t\t<param name="button_onclick" value="ActivateWindow(Videos,plugin://plugin.video.bilikodiRe/,return)"/>
\t\t\t\t\t\t<param name="button_id" value="22300"/>
\t\t\t\t\t\t<param name="visible" value="!Integer.IsGreater(Container(22100).NumItems,0) + !Container(22100).IsUpdating"/>
\t\t\t\t\t\t<param name="visible_1" value="false"/>
\t\t\t\t\t</include>
\t\t\t\t\t<include content="WidgetScrollbar" condition="Skin.HasSetting(touchmode)">
\t\t\t\t\t\t<param name="scrollbar_id" value="22010"/>
\t\t\t\t\t</include>
\t\t\t\t</control>
"""


BILIBILI_MENU_ITEM = """\
\t\t\t\t\t\t<!-- PiBiliOnKodi home entry -->
\t\t\t\t\t\t<item>
\t\t\t\t\t\t\t<label>哔哩哔哩</label>
\t\t\t\t\t\t\t<onclick>ActivateWindow(Videos,plugin://plugin.video.bilikodiRe/,return)</onclick>
\t\t\t\t\t\t\t<property name="menu_id">$NUMBER[22100]</property>
\t\t\t\t\t\t\t<thumb>icons/sidemenu/videos.png</thumb>
\t\t\t\t\t\t\t<property name="id">bilibili</property>
\t\t\t\t\t\t</item>
"""


def patch_addon_xml(text):
    old = '<addon id="skin.estuary" version='
    new = '<addon id="{}" version='.format(CUSTOM_SKIN_ID)
    if old not in text:
        raise ValueError("Unexpected Estuary addon.xml: add-on id was not found")
    text = text.replace(old, new, 1)
    text = text.replace('name="Estuary"', 'name="Estuary + 哔哩哔哩"', 1)
    return text


def patch_home_xml(text):
    if PATCH_MARKER in text:
        return text

    widget_marker = '\t\t\t\t<control type="group" id="15000">'
    if widget_marker not in text:
        raise ValueError("Unexpected Home.xml: weather widget marker was not found")
    text = text.replace(widget_marker, BILIBILI_WIDGET + widget_marker, 1)

    menu_marker = (
        '\t\t\t\t\t\t<item>\n'
        '\t\t\t\t\t\t\t<label>$LOCALIZE[8]</label>'
    )
    if menu_marker not in text:
        raise ValueError("Unexpected Home.xml: weather menu marker was not found")
    return text.replace(menu_marker, BILIBILI_MENU_ITEM + menu_marker, 1)


def _write_text(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")


def install_skin(
    source_skin,
    target_skin,
    source_settings=None,
    target_settings=None,
    backup_root=None,
):
    source_skin = Path(source_skin).resolve()
    target_skin = Path(target_skin).resolve()
    if not (source_skin / "addon.xml").is_file():
        raise FileNotFoundError("Estuary source add-on was not found: {}".format(source_skin))
    if source_skin == target_skin or source_skin in target_skin.parents:
        raise ValueError("Target skin must not be inside the system source skin")

    target_skin.parent.mkdir(parents=True, exist_ok=True)
    staging = target_skin.with_name(target_skin.name + ".installing")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(source_skin, staging, symlinks=True)

    addon_path = staging / "addon.xml"
    home_path = staging / "xml" / "Home.xml"
    _write_text(addon_path, patch_addon_xml(addon_path.read_text(encoding="utf-8")))
    _write_text(home_path, patch_home_xml(home_path.read_text(encoding="utf-8")))

    backup = None
    if target_skin.exists():
        if backup_root is None:
            backup_root = target_skin.parent.parent / "addon_backups" / "PiBiliOnKodi"
        backup_root = Path(backup_root).resolve()
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = backup_root / (target_skin.name + ".backup-" + stamp)
        os.replace(target_skin, backup)
    os.replace(staging, target_skin)

    if source_settings and target_settings:
        source_settings = Path(source_settings).resolve()
        target_settings = Path(target_settings).resolve()
        if source_settings.is_file():
            target_settings.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_settings, target_settings)
    return target_skin, backup


def main():
    home = Path.home()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", default="/usr/share/kodi/addons/skin.estuary", type=Path
    )
    parser.add_argument(
        "--target",
        default=home / ".kodi" / "addons" / CUSTOM_SKIN_ID,
        type=Path,
    )
    parser.add_argument(
        "--source-settings",
        default=home / ".kodi" / "userdata" / "addon_data" / "skin.estuary" / "settings.xml",
        type=Path,
    )
    parser.add_argument(
        "--target-settings",
        default=home
        / ".kodi"
        / "userdata"
        / "addon_data"
        / CUSTOM_SKIN_ID
        / "settings.xml",
        type=Path,
    )
    args = parser.parse_args()
    target, backup = install_skin(
        args.source,
        args.target,
        source_settings=args.source_settings,
        target_settings=args.target_settings,
    )
    print("Installed {}".format(target))
    if backup:
        print("Previous copy preserved at {}".format(backup))


if __name__ == "__main__":
    main()
