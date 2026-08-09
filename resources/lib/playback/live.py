"""Select a Kodi-compatible stream from Bilibili live play information."""


# Bilibili live qn: 15000=2K, 20000=4K.  Higher tiers are HDR/Dolby
# variants that are not part of the validated Pi 4 live profile.
PI4_LIVE_MAX_QN = 20000
PI4_AVC_MAX_QN = 10000


class LivePlaybackError(RuntimeError):
    pass


def _codec_name(value):
    value = str(value or "").lower()
    if value in ("hevc", "h265", "hev1", "hvc1"):
        return "hevc"
    if value in ("avc", "h264", "avc1"):
        return "avc"
    if value in ("av1", "av01"):
        return "av1"
    return value


def _stream_url(codec):
    base_url = codec.get("base_url") or codec.get("baseUrl") or ""
    for url_info in codec.get("url_info") or codec.get("urlInfo") or []:
        host = url_info.get("host") or ""
        if host and base_url:
            return "{}{}{}".format(
                host, base_url, url_info.get("extra") or ""
            )
    return ""


def live_variants(play_info):
    """Flatten Bilibili's protocol/format/codec tree into playable variants."""
    playurl = (play_info or {}).get("playurl_info") or play_info or {}
    playurl = playurl.get("playurl") or playurl
    quality_names = {
        int(item.get("qn") or 0): str(item.get("desc") or "")
        for item in (playurl.get("g_qn_desc") or [])
        if item.get("qn") is not None
    }
    variants = []
    for stream in playurl.get("stream") or []:
        protocol = stream.get("protocol_name") or ""
        for stream_format in (stream.get("format") or []):
            format_name = stream_format.get("format_name") or ""
            for codec in stream_format.get("codec") or []:
                url = _stream_url(codec)
                if not url:
                    continue
                variants.append({
                    "protocol": protocol,
                    "format": format_name,
                    "codec": _codec_name(codec.get("codec_name")),
                    "qn": int(codec.get("current_qn") or 0),
                    "quality_desc": quality_names.get(
                        int(codec.get("current_qn") or 0), ""
                    ),
                    "url": url,
                })
    return variants


def select_live_stream(play_info, codec_preference="hevc"):
    """Prefer HLS and the requested Pi-compatible codec; never select AV1."""
    preference = "avc" if str(codec_preference).lower() == "avc" else "hevc"
    codec_order = [preference, "avc" if preference == "hevc" else "hevc"]
    protocol_order = {"http_hls": 0, "http_stream": 1}
    format_order = {"ts": 0, "fmp4": 1, "flv": 2}
    candidates = [
        item for item in live_variants(play_info)
        if item["codec"] != "av1"
        and 0 < item["qn"] <= PI4_LIVE_MAX_QN
        and not (item["codec"] == "avc" and item["qn"] > PI4_AVC_MAX_QN)
    ]
    if not candidates:
        raise LivePlaybackError("直播接口没有返回 Pi 4 可播放的 HLS/HTTP 流")

    def rank(item):
        try:
            codec_rank = codec_order.index(item["codec"])
        except ValueError:
            codec_rank = len(codec_order) + 1
        return (
            protocol_order.get(item["protocol"], 9),
            codec_rank,
            format_order.get(item["format"], 9),
            -item["qn"],
        )

    return min(candidates, key=rank)


__all__ = [
    "LivePlaybackError",
    "PI4_LIVE_MAX_QN",
    "live_variants",
    "select_live_stream",
]
