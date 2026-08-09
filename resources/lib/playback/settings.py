"""Small, defensive adapter between Kodi settings and playback code."""

from resources.lib.playback.stream_selector import quality_cap


VALID_QUALITIES = {"auto", "1080p", "1080p60", "4k", "highest"}
VALID_CODECS = {"hevc", "avc"}


def _text(addon, setting_id, default):
    value = addon.getSetting(setting_id)
    return value if value else default


def _boolean(addon, setting_id, default):
    value = addon.getSetting(setting_id)
    if not value:
        return bool(default)
    return value.lower() == "true"


def playback_settings(addon):
    quality = _text(addon, "video_quality", "highest").lower()
    if quality not in VALID_QUALITIES:
        quality = "highest"

    codec = _text(addon, "video_codec", "hevc").lower()
    if codec not in VALID_CODECS:
        codec = "hevc"

    return {
        "quality": quality,
        "request_qn": 127 if quality in ("auto", "highest") else quality_cap(quality),
        "codec_preference": codec,
        "allow_av1": _boolean(addon, "allow_av1", False),
        "auto_compatible": _boolean(addon, "auto_compatible", True),
        "quality_fallback": _boolean(addon, "quality_fallback", True),
    }


__all__ = ["playback_settings"]
