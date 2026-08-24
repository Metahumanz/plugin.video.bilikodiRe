"""Build a small Bilibili SegmentBase MPD and resolve it through Kodi ISA."""

import os
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

from .manifest_server import ManifestServerError, manifest_url
from .stream_selector import (
    StreamSelectionError,
    codec_name,
    dynamic_range_name,
    frame_rate,
    quality_id,
    select_audio_stream,
    select_video_stream,
)


REFERER = "https://www.bilibili.com/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
    "Chrome/120 Safari/537.36"
)


class DashPlaybackError(ValueError):
    """Raised when Bilibili DASH data cannot produce a playable MPD."""


def _get(mapping, *names, default=None):
    for name in names:
        value = mapping.get(name)
        if value is not None:
            return value
    return default


def _segment_base(stream):
    segment = _get(stream, "SegmentBase", "segment_base") or {}
    index_range = _get(segment, "indexRange", "index_range")
    initialization = _get(segment, "Initialization", "initialization")
    if not index_range or not initialization:
        raise DashPlaybackError("DASH Representation 缺少 SegmentBase")
    return str(index_range), str(initialization)


def _base_url(stream):
    url = _get(stream, "baseUrl", "base_url")
    if not url:
        backups = _get(stream, "backupUrl", "backup_url", default=[]) or []
        url = backups[0] if backups else None
    if not url:
        raise DashPlaybackError("DASH Representation 缺少 BaseURL")
    return str(url)


def _duration(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    text = ("{:.3f}".format(max(number, 0.0))).rstrip("0").rstrip(".")
    return "PT{}S".format(text or "0")


def _add_segment_base(parent, stream):
    index_range, initialization = _segment_base(stream)
    segment = ET.SubElement(parent, "SegmentBase", {"indexRange": index_range})
    ET.SubElement(segment, "Initialization", {"range": initialization})


def generate_mpd(
    dash,
    video_stream=None,
    audio_stream=None,
    quality="highest",
    codec_preference="hevc",
    allow_av1=False,
    quality_fallback=True,
    auto_compatible=True,
):
    """Generate a static MPD containing one selected video and audio stream."""
    if not isinstance(dash, dict):
        raise DashPlaybackError("playurl 未返回有效 DASH 数据")

    try:
        video = video_stream or select_video_stream(
            dash.get("video"), quality, codec_preference, allow_av1,
            quality_fallback, auto_compatible
        )
        audio = audio_stream or select_audio_stream(dash.get("audio"))
    except StreamSelectionError as exc:
        raise DashPlaybackError(str(exc)) from exc

    root = ET.Element(
        "MPD",
        {
            "xmlns": "urn:mpeg:dash:schema:mpd:2011",
            "profiles": "urn:mpeg:dash:profile:isoff-on-demand:2011",
            "type": "static",
            "mediaPresentationDuration": _duration(dash.get("duration")),
            "minBufferTime": _duration(dash.get("minBufferTime", 1.5)),
        },
    )
    period = ET.SubElement(root, "Period")

    video_set = ET.SubElement(
        period,
        "AdaptationSet",
        {
            "contentType": "video",
            "mimeType": "video/mp4",
            "startWithSAP": "1",
            "scanType": "progressive",
            "segmentAlignment": "true",
        },
    )
    video_attrs = {
        "id": str(_get(video, "id", "qn", default=quality_id(video))),
        "bandwidth": str(video.get("bandwidth") or 0),
        "codecs": str(video.get("codecs") or ""),
        "width": str(video.get("width") or 0),
        "height": str(video.get("height") or 0),
    }
    raw_frame_rate = _get(video, "frameRate", "frame_rate")
    if raw_frame_rate:
        video_attrs["frameRate"] = str(raw_frame_rate)
    video_representation = ET.SubElement(video_set, "Representation", video_attrs)
    ET.SubElement(video_representation, "BaseURL").text = _base_url(video)
    _add_segment_base(video_representation, video)

    audio_set = ET.SubElement(
        period,
        "AdaptationSet",
        {
            "contentType": "audio",
            "mimeType": "audio/mp4",
            "startWithSAP": "1",
            "segmentAlignment": "true",
            "lang": "und",
        },
    )
    audio_attrs = {
        "id": str(audio.get("id") or 0),
        "bandwidth": str(audio.get("bandwidth") or 0),
        "codecs": str(audio.get("codecs") or ""),
    }
    sampling_rate = _get(audio, "audioSamplingRate", "audio_sampling_rate")
    if sampling_rate:
        audio_attrs["audioSamplingRate"] = str(sampling_rate)
    audio_representation = ET.SubElement(audio_set, "Representation", audio_attrs)
    ET.SubElement(audio_representation, "BaseURL").text = _base_url(audio)
    _add_segment_base(audio_representation, audio)

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def build_stream_headers(cookies=None, referer=REFERER, user_agent=USER_AGENT):
    """Build URL-encoded InputStream Adaptive request headers."""
    headers = {"Referer": referer, "User-Agent": user_agent}
    if cookies:
        headers["Cookie"] = "; ".join(
            "{}={}".format(name, value) for name, value in cookies.items()
        )
    return urlencode(headers)


def write_mpd(mpd, temp_dir, cid):
    os.makedirs(temp_dir, exist_ok=True)
    safe_cid = "".join(
        char for char in str(cid) if char.isalnum() or char in ("-", "_")
    ) or "playback"
    path = os.path.join(temp_dir, "{}.mpd".format(safe_cid))
    with open(path, "w", encoding="utf-8", newline="\n") as mpd_file:
        mpd_file.write(mpd)
    return path


def attach_subtitles(kodi_item, subtitles):
    """Attach one or more local subtitle tracks to a native Kodi ListItem."""
    if not subtitles:
        return []
    if isinstance(subtitles, (str, bytes, os.PathLike)):
        paths = [os.fspath(subtitles)]
    else:
        paths = [os.fspath(path) for path in subtitles if path]
    if paths:
        kodi_item.setSubtitles(paths)
    return paths


def play_dash(
    dash,
    temp_dir,
    cid,
    quality="highest",
    codec_preference="hevc",
    allow_av1=False,
    quality_fallback=True,
    auto_compatible=True,
    cookies=None,
    plugin=None,
    subtitles=None,
):
    """Resolve selected DASH streams to Kodi without creating another player."""
    video = select_video_stream(
        dash.get("video"), quality, codec_preference, allow_av1,
        quality_fallback, auto_compatible
    )
    audio = select_audio_stream(dash.get("audio"))
    mpd = generate_mpd(dash, video_stream=video, audio_stream=audio)
    mpd_path = write_mpd(mpd, temp_dir, cid)
    mpd_uri = manifest_url(mpd_path, temp_dir)

    if plugin is None:
        raise DashPlaybackError("缺少 Kodi 插件 resolver")

    # Use xbmcswift2's resolver so its _end_of_directory state is updated.
    # Calling xbmcplugin.setResolvedUrl directly here makes xbmcswift2 finish
    # the same handle with succeeded=False after the route returns.
    from xbmcswift2 import ListItem

    item = ListItem(path=mpd_uri, offscreen=True)
    kodi_item = item.as_xbmc_listitem()
    kodi_item.setMimeType("application/dash+xml")
    kodi_item.setContentLookup(False)
    kodi_item.setProperty("inputstream", "inputstream.adaptive")
    kodi_item.setProperty(
        "inputstream.adaptive.stream_headers",
        build_stream_headers(cookies=cookies),
    )
    attach_subtitles(kodi_item, subtitles)
    plugin.set_resolved_url(item)
    return {
        "mpd_path": mpd_path,
        "video": video,
        "audio": audio,
        "codec": codec_name(video),
        "dynamic_range": dynamic_range_name(video),
        "quality": quality_id(video),
        "fps": frame_rate(video),
    }


__all__ = [
    "DashPlaybackError",
    "ManifestServerError",
    "build_stream_headers",
    "attach_subtitles",
    "generate_mpd",
    "play_dash",
    "select_audio_stream",
    "select_video_stream",
    "write_mpd",
]
