"""Pi 4 compatible Bilibili DASH stream selection.

The codec preference is deliberately evaluated before quality.  With the
default settings this means that a compatible HEVC representation is chosen
before falling back to AVC.  AV1 is excluded unless explicitly enabled.
"""

from fractions import Fraction
import re


CODECID_TO_CODEC = {
    7: "avc",
    12: "hevc",
    13: "av1",
}

QUALITY_CAPS = {
    # qn=125 is Bilibili's HDR tier.  Dolby Vision (126) and 8K (127) stay
    # above the Pi 4 profile and are intentionally not selected.
    "auto": 125,
    "highest": 125,
    "4k": 120,
    "2160p": 120,
    "1080p60": 116,
    "1080p": 80,
    "720p": 64,
}

# Raspberry Pi 4's validated HEVC playback target is UHD at up to 60 fps.
# Bilibili can expose 120 fps representations under the same qn=120 quality
# id, so qn alone is not a sufficient compatibility check.  Keep a small
# tolerance for sources reported as 60.001 or similar fractional rates.
PI4_MAX_FPS = 60.5
BILIBILI_HDR_QN = 125
PI4_HEVC_HDR_PROFILES = {2}  # ISO/IEC 14496-15 HEVC Main 10


class StreamSelectionError(ValueError):
    """Raised when no Pi 4 compatible representation is available."""


def _get(stream, *names, default=None):
    for name in names:
        value = stream.get(name)
        if value is not None:
            return value
    return default


def codec_name(stream):
    """Return ``hevc``, ``avc``, ``av1`` or ``unknown`` for a stream."""
    codecs = str(_get(stream, "codecs", "codec", default="")).lower()
    if codecs.startswith(("hev1", "hvc1")) or "hevc" in codecs:
        return "hevc"
    if codecs.startswith(("avc1", "avc3")) or "h264" in codecs:
        return "avc"
    if codecs.startswith("av01") or "av1" in codecs:
        return "av1"

    try:
        return CODECID_TO_CODEC.get(int(stream.get("codecid", 0)), "unknown")
    except (TypeError, ValueError):
        return "unknown"


def hevc_profile(stream):
    """Return the HEVC profile_idc from an RFC 6381 codec string."""
    codecs = str(_get(stream, "codecs", "codec", default="")).lower()
    match = re.match(r"^(?:hev1|hvc1)\.(\d+)(?:\.|$)", codecs)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def dynamic_range_name(stream):
    """Return the Bilibili dynamic-range tier represented by qn."""
    qn = quality_id(stream)
    if qn == 125:
        return "hdr"
    if qn == 126:
        return "dolby_vision"
    return "sdr"


def frame_rate(stream):
    """Parse Bilibili frame-rate values such as ``60000/1001``."""
    value = _get(stream, "frameRate", "frame_rate", default=0)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return 0.0


def quality_id(stream):
    """Read qn/id, deriving a conservative value when it is absent."""
    value = _get(stream, "id", "qn", default=0)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0
    if value:
        return value

    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    long_edge = max(width, height)
    fps = frame_rate(stream)
    if long_edge >= 3000:
        return 120
    if long_edge >= 1900:
        return 116 if fps >= 50 else 80
    if long_edge >= 1200:
        return 74 if fps >= 50 else 64
    if long_edge >= 800:
        return 32
    return 16


def _quality_cap(quality):
    if isinstance(quality, int):
        return quality
    normalized = str(quality or "highest").lower().replace(" ", "")
    aliases = {
        "最高": "highest",
        "自动": "auto",
        "1080p60fps": "1080p60",
        "4k60": "4k",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in QUALITY_CAPS:
        raise StreamSelectionError("未知画质设置: {}".format(quality))
    return QUALITY_CAPS[normalized]


def quality_cap(quality):
    """Return the highest Bilibili qn allowed by a user-facing setting."""
    return _quality_cap(quality)


def _codec_order(codec_preference, allow_av1, auto_compatible=True):
    preference = str(codec_preference or "hevc").lower()
    if "avc" in preference or "h264" in preference:
        order = ["avc", "hevc"] if auto_compatible else ["avc"]
    else:
        order = ["hevc", "avc"] if auto_compatible else ["hevc"]
    if allow_av1:
        order.append("av1")
    return order


def _video_sort_key(stream):
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    bandwidth = int(stream.get("bandwidth") or 0)
    return (
        quality_id(stream),
        frame_rate(stream),
        width * height,
        bandwidth,
    )


def _pi4_compatible_stream(stream):
    """Apply the hardware limits that cannot be expressed by qn alone."""
    fps = frame_rate(stream)
    if fps and fps > PI4_MAX_FPS:
        return False

    # Bilibili's qn=125 is HDR.  On Pi 4 only accept a representation that
    # explicitly identifies itself as HEVC Main 10.  This prevents an AV1,
    # AVC, missing-profile, or otherwise ambiguous HDR representation from
    # being handed to the hardware decoder.
    if quality_id(stream) == BILIBILI_HDR_QN:
        return (
            codec_name(stream) == "hevc"
            and hevc_profile(stream) in PI4_HEVC_HDR_PROFILES
        )
    return True


def select_video_stream(
    dash_video,
    quality="highest",
    codec_preference="hevc",
    allow_av1=False,
    quality_fallback=True,
    auto_compatible=True,
):
    """Select one video representation using Pi 4 codec/quality priorities."""
    cap = _quality_cap(quality)
    if quality_fallback:
        streams = [stream for stream in (dash_video or []) if quality_id(stream) <= cap]
    else:
        streams = [stream for stream in (dash_video or []) if quality_id(stream) == cap]

    # Both SDR and HDR tiers can contain frame rates outside the Pi 4 profile.
    # Incompatible representations fall through to the next safe tier.
    streams = [stream for stream in streams if _pi4_compatible_stream(stream)]

    codec_order = _codec_order(codec_preference, allow_av1, auto_compatible)

    # The Pi profile explicitly prefers HEVC down through 720P, then the
    # corresponding AVC ladder.  A stray low-resolution HEVC stream should
    # therefore not beat a 720P-or-better AVC representation.
    if cap >= 64:
        for codec in codec_order:
            candidates = [
                stream
                for stream in streams
                if codec_name(stream) == codec and quality_id(stream) >= 64
            ]
            if candidates:
                return max(candidates, key=_video_sort_key)

    # Below 720P, do not sacrifice another quality tier merely to keep HEVC.
    # Codec preference is only a tie breaker at the best remaining qn.
    if streams:
        best_quality = max(quality_id(stream) for stream in streams)
        best_tier = [stream for stream in streams if quality_id(stream) == best_quality]
        for codec in codec_order:
            candidates = [stream for stream in best_tier if codec_name(stream) == codec]
            if candidates:
                return max(candidates, key=_video_sort_key)

    av1_note = "（AV1 已禁用）" if not allow_av1 else ""
    raise StreamSelectionError(
        "没有可用的 Pi 4 兼容 HEVC/AVC 视频流（最高 60fps）{}".format(av1_note)
    )


def select_audio_stream(dash_audio):
    """Select the highest-bandwidth regular audio representation."""
    streams = list(dash_audio or [])
    if not streams:
        raise StreamSelectionError("没有可用的普通音频流")

    regular = []
    for stream in streams:
        codecs = str(_get(stream, "codecs", "codec", default="")).lower()
        if codecs.startswith("mp4a") or "aac" in codecs:
            regular.append(stream)
    candidates = regular or streams

    def audio_key(stream):
        return (int(stream.get("bandwidth") or 0), int(stream.get("id") or 0))

    return max(candidates, key=audio_key)
