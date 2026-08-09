"""Kodi service that exposes generated DASH manifests on loopback."""

import os
import ast
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
from xbmcswift2 import Plugin

from resources.lib.playback.manifest_server import (
    create_server,
    remove_port_file,
    write_port_file,
)
from resources.lib.playback.progress import read_playback_context, report_progress
from resources.lib.playback.danmaku import danmaku_settings
from resources.lib.playback.live_danmaku import (
    LiveDanmakuClient,
    LiveSubtitleBuffer,
    live_context_matches,
    read_live_context,
)
from resources.lib.navigation_keymap import sync_navigation_keymap
from resources.lib.home_behavior import should_stop_video_on_home


ADDON_ID = "plugin.video.bilikodiRe"
TEMP_DIR = xbmcvfs.translatePath("special://temp/{}/".format(ADDON_ID))
PROFILE_DIR = xbmcvfs.translatePath("special://profile/")


def _stored_cookies():
    # QR login and web-session warm-up run in other plugin interpreters.
    cookies = Plugin().get_storage("user").get("cookies", {})
    if isinstance(cookies, str):
        try:
            cookies = ast.literal_eval(cookies)
        except (SyntaxError, ValueError):
            cookies = {}
    return cookies if isinstance(cookies, dict) else {}


class PlaybackProgressPlayer(xbmc.Player):
    """Report only playback started by this add-on's loopback MPD service."""

    def __init__(self, temp_dir):
        super().__init__()
        self.temp_dir = temp_dir
        self.addon = xbmcaddon.Addon(ADDON_ID)
        self.context = None
        self.last_position = 0
        self.last_report = 0.0
        self.stopped = False

    def _enabled(self):
        return self.addon.getSetting("rec_history").lower() == "true"

    def _cookies(self):
        return _stored_cookies()

    def _activate(self):
        if not self._enabled() or not self.isPlayingVideo():
            return
        try:
            playing_file = self.getPlayingFile()
        except RuntimeError:
            return
        if "/plugin.video.bilikodiRe/manifest/" not in playing_file:
            return
        context = read_playback_context(self.temp_dir)
        if context and ("/{}.mpd".format(context["cid"]) in playing_file):
            self.context = context
            self.last_position = 0
            self.last_report = 0.0
            self.stopped = False

    def _send(self):
        if self.context:
            success = report_progress(self.context, self.last_position, self._cookies())
            xbmc.log(
                "[bilikodiReborn] playback progress cid={} time={} result={}".format(
                    self.context["cid"], self.last_position, success
                ),
                xbmc.LOGINFO,
            )
            self.last_report = time.monotonic()

    def tick(self):
        if self.stopped and self.context:
            self._send()
            self.context = None
            self.stopped = False
            return
        if not self.isPlayingVideo():
            return
        if not self.context:
            self._activate()
        if not self.context:
            return
        try:
            self.last_position = max(0, int(self.getTime()))
        except RuntimeError:
            return
        if time.monotonic() - self.last_report >= 15:
            self._send()

    def onPlayBackStopped(self):
        self.stopped = True

    def onPlayBackEnded(self):
        try:
            self.last_position = max(self.last_position, int(self.getTotalTime()))
        except RuntimeError:
            pass
        self.stopped = True


class LiveDanmakuController:
    """Attach a periodically refreshed native ASS track to Bilibili live video."""

    def __init__(self, temp_dir):
        self.temp_dir = temp_dir
        self.addon = xbmcaddon.Addon(ADDON_ID)
        self.player = xbmc.Player()
        self.context = None
        self.client = None
        self.buffer = None
        self.last_reload = 0.0
        self.subtitle_enable_at = 0.0

    @staticmethod
    def _log(message, level=xbmc.LOGINFO):
        xbmc.log("[bilikodiReborn] {}".format(message), level)

    def _stop(self):
        if self.client:
            self.client.stop()
        if self.context:
            self._log(
                "Live danmaku stopped: room={}".format(self.context.get("room_id"))
            )
        self.context = None
        self.client = None
        self.buffer = None
        self.last_reload = 0.0
        self.subtitle_enable_at = 0.0

    def close(self):
        self._stop()

    def _start_if_needed(self):
        if self.client or not self.player.isPlayingVideo():
            return
        settings = danmaku_settings(self.addon)
        if not settings.get("enabled"):
            return
        try:
            playing_file = self.player.getPlayingFile()
        except RuntimeError:
            return
        context = read_live_context(self.temp_dir)
        if not live_context_matches(context, playing_file):
            return
        room_id = context["room_id"]
        self.context = context
        self.buffer = LiveSubtitleBuffer(room_id)
        self.client = LiveDanmakuClient(
            room_id,
            cookies=_stored_cookies(),
            log=lambda message: self._log(message, xbmc.LOGWARNING),
        )
        self.client.start()
        self._log("Live danmaku started: room={}".format(room_id))

    def tick(self):
        if self.client and not self.player.isPlayingVideo():
            self._stop()
            return
        if self.client and self.addon.getSetting("danmaku_enabled").lower() == "false":
            self._stop()
            return
        self._start_if_needed()
        if not self.client:
            return
        try:
            playing_file = self.player.getPlayingFile()
        except RuntimeError:
            self._stop()
            return
        # The age limit protects initial attachment from a stale context file.
        # Once this controller has attached to the exact stream URL, keeping a
        # live programme open for more than two minutes must not stop danmaku.
        if not live_context_matches(self.context, playing_file, max_age=None):
            self._stop()
            return
        comments = self.client.drain()
        try:
            playback_time = max(0.0, float(self.player.getTime()))
        except RuntimeError:
            return
        if comments:
            self.buffer.add(comments, playback_time)
        now = time.monotonic()
        if self.subtitle_enable_at and now >= self.subtitle_enable_at:
            try:
                # setSubtitles() loads asynchronously. Enabling on the next
                # service tick ensures the new external track already exists.
                self.player.showSubtitles(True)
                self._log(
                    "Live danmaku subtitles enabled: room={}".format(
                        self.context["room_id"]
                    )
                )
            except RuntimeError as exc:
                self._log(
                    "Live danmaku subtitle enable failed: {}".format(exc),
                    xbmc.LOGWARNING,
                )
            self.subtitle_enable_at = 0.0
        if not self.buffer.dirty or now - self.last_reload < 1.5:
            return
        settings = danmaku_settings(self.addon)
        settings.pop("enabled", None)
        try:
            path = self.buffer.render(
                self.temp_dir, playback_time, settings
            )
            self.player.setSubtitles(path)
            self.subtitle_enable_at = now + 0.5
            self.last_reload = now
            self._log(
                "Live danmaku updated: room={} received={} buffered={}".format(
                    self.context["room_id"], len(comments), len(self.buffer.comments)
                )
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self._log("Live danmaku subtitle update failed: {}".format(exc), xbmc.LOGWARNING)


def run():
    addon = xbmcaddon.Addon(ADDON_ID)
    addon_dir = xbmcvfs.translatePath(addon.getAddonInfo("path"))
    navigation_enabled = addon.getSetting("navigation_parent_back").lower() != "false"
    stop_video_on_back = addon.getSetting("stop_video_on_back").lower() != "false"
    keymap_changed, keymap_path = sync_navigation_keymap(
        addon_dir,
        PROFILE_DIR,
        enabled=navigation_enabled,
        stop_video_on_exit=stop_video_on_back,
    )
    if keymap_changed:
        xbmc.log(
            "[bilikodiReborn] Navigation keymap updated: {}".format(keymap_path),
            xbmc.LOGINFO,
        )
        xbmc.executebuiltin("ReloadKeymaps")

    os.makedirs(TEMP_DIR, exist_ok=True)
    server = create_server(TEMP_DIR)
    port = server.server_address[1]
    write_port_file(TEMP_DIR, port)
    xbmc.log(
        "[bilikodiReborn] MPD service listening on 127.0.0.1:{}".format(port),
        xbmc.LOGINFO,
    )

    thread = threading.Thread(target=server.serve_forever, name="bilikodi-mpd")
    thread.daemon = True
    thread.start()
    monitor = xbmc.Monitor()
    progress = PlaybackProgressPlayer(TEMP_DIR)
    live_danmaku = LiveDanmakuController(TEMP_DIR)
    previous_window_id = xbmcgui.getCurrentWindowId()
    try:
        while not monitor.waitForAbort(1):
            progress.tick()
            live_danmaku.tick()
            stop_video_on_home = (
                addon.getSetting("stop_video_on_home").lower() != "false"
            )
            current_window_id = xbmcgui.getCurrentWindowId()
            if should_stop_video_on_home(
                current_window_id,
                previous_window_id,
                progress.isPlayingVideo(),
                enabled=stop_video_on_home,
            ):
                xbmc.log(
                    "[bilikodiReborn] Stopping video after Kodi entered Home",
                    xbmc.LOGINFO,
                )
                progress.stop()
            previous_window_id = current_window_id
    finally:
        live_danmaku.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        remove_port_file(TEMP_DIR, expected_port=port)


if __name__ == "__main__":
    run()
