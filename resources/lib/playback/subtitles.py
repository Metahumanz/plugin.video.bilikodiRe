"""Fetch Bilibili official subtitles and convert their JSON format for Kodi."""

import html
import os
import re
import shutil
from urllib.parse import urlsplit


PLAYER_INFO_URL = "https://api.bilibili.com/x/player/wbi/v2"
VIEW_INFO_URL = "https://api.bilibili.com/x/web-interface/view"
REFERER_TEMPLATE = "https://www.bilibili.com/video/{}/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
    "Chrome/120 Safari/537.36"
)
MAX_SUBTITLE_TRACKS = 12
VALID_LANGUAGE_PREFERENCES = {"auto", "zh-hans", "zh-hant", "en"}


class BilibiliSubtitleError(ValueError):
    """Raised when Bilibili subtitle metadata or content is unusable."""


def _setting_bool(addon, setting_id, default):
    value = addon.getSetting(setting_id)
    if not value:
        return bool(default)
    return value.lower() == "true"


def _setting_number(addon, setting_id, default, minimum, maximum):
    try:
        value = float(addon.getSetting(setting_id))
    except (TypeError, ValueError):
        value = float(default)
    return max(float(minimum), min(float(maximum), value))


def subtitle_settings(addon):
    preference = (addon.getSetting("bili_subtitle_language") or "auto").lower()
    if preference not in VALID_LANGUAGE_PREFERENCES:
        preference = "auto"
    return {
        "enabled": _setting_bool(addon, "bili_subtitle_enabled", True),
        "language": preference,
        "font_size": _setting_number(addon, "bili_subtitle_font_size", 42, 16, 96),
    }


def _headers(bvid):
    return {
        "User-Agent": USER_AGENT,
        "Referer": REFERER_TEMPLATE.format(str(bvid or "")),
    }


def _subtitle_url(value):
    url = str(value or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == "hdslb.com" or hostname.endswith(".hdslb.com")
    ):
        raise BilibiliSubtitleError("字幕地址不是受信任的 B站 HTTPS 资源")
    return url


def _fetch_video_aid(bvid, cid, cookies=None, timeout=20):
    """Verify that ``cid`` belongs to ``bvid`` and return the current aid."""
    import requests

    try:
        response = requests.get(
            VIEW_INFO_URL,
            params={"bvid": str(bvid)},
            headers=_headers(bvid),
            cookies=cookies or {},
            timeout=timeout,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise BilibiliSubtitleError(
                "视频身份接口 HTTP {}".format(response.status_code)
            )
        payload = response.json()
    except BilibiliSubtitleError:
        raise
    except (requests.RequestException, ValueError) as exc:
        # Do not include request URLs in errors: subtitle URLs contain auth_key.
        raise BilibiliSubtitleError("视频身份接口请求失败") from exc

    if not isinstance(payload, dict) or payload.get("code") != 0:
        code = payload.get("code") if isinstance(payload, dict) else "invalid"
        raise BilibiliSubtitleError("视频身份接口返回错误 {}".format(code))

    data = payload.get("data") or {}
    aid = data.get("aid")
    pages = data.get("pages") or []
    if not aid or not any(
        isinstance(page, dict) and str(page.get("cid")) == str(cid)
        for page in pages
    ):
        raise BilibiliSubtitleError("当前 CID 不属于请求的 BVID")
    return str(aid)


def _signed_player_params(bvid, cid, wbi_signer):
    if not callable(wbi_signer):
        raise BilibiliSubtitleError("播放器字幕接口缺少 WBI 签名器")
    raw = {"bvid": str(bvid), "cid": str(cid)}
    try:
        signed = wbi_signer(dict(raw))
    except Exception as exc:
        raise BilibiliSubtitleError("播放器字幕接口 WBI 签名失败") from exc
    if not isinstance(signed, dict) or any(
        str(signed.get(key)) != value for key, value in raw.items()
    ):
        raise BilibiliSubtitleError("播放器字幕接口 WBI 参数无效")
    if not signed.get("w_rid") or not signed.get("wts"):
        raise BilibiliSubtitleError("播放器字幕接口 WBI 签名不完整")
    return signed


def fetch_subtitle_tracks(
    bvid, cid, cookies=None, timeout=20, wbi_signer=None
):
    """Return tracks from the WBI player API after binding BVID and CID."""
    import requests

    # The legacy /x/player/v2 endpoint can return unrelated cached tracks for
    # authenticated requests.  Never use it as a fallback: first prove that
    # this CID belongs to the requested BVID, then query the signed endpoint.
    _fetch_video_aid(bvid, cid, cookies=cookies, timeout=timeout)
    params = _signed_player_params(bvid, cid, wbi_signer)

    try:
        response = requests.get(
            PLAYER_INFO_URL,
            params=params,
            headers=_headers(bvid),
            cookies=cookies or {},
            timeout=timeout,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise BilibiliSubtitleError(
                "播放器字幕接口 HTTP {}".format(response.status_code)
            )
        payload = response.json()
    except BilibiliSubtitleError:
        raise
    except (requests.RequestException, ValueError) as exc:
        raise BilibiliSubtitleError("播放器字幕接口请求失败") from exc

    if not isinstance(payload, dict) or payload.get("code") != 0:
        code = payload.get("code") if isinstance(payload, dict) else "invalid"
        raise BilibiliSubtitleError("播放器字幕接口返回错误 {}".format(code))

    data = payload.get("data") or {}
    subtitle = data.get("subtitle") or {}
    raw_tracks = subtitle.get("subtitles") or []
    tracks = []
    for index, track in enumerate(raw_tracks[:MAX_SUBTITLE_TRACKS]):
        if not isinstance(track, dict) or not track.get("subtitle_url"):
            continue
        try:
            url = _subtitle_url(track.get("subtitle_url"))
        except BilibiliSubtitleError:
            continue
        raw_language = str(track.get("lan") or "und")
        ai_type = track.get("ai_type")
        tracks.append(
            {
                "index": index,
                "id": str(track.get("id_str") or track.get("id") or index),
                "language": raw_language,
                "language_name": str(track.get("lan_doc") or ""),
                "is_ai": raw_language.lower().replace("_", "-").startswith("ai-")
                or ai_type not in (None, 0, "0"),
                "url": url,
            }
        )
    return tracks


def fetch_subtitle_document(track, bvid, cookies=None, timeout=20):
    """Download one subtitle JSON document without exposing its signed URL."""
    import requests

    try:
        response = requests.get(
            track["url"],
            headers=_headers(bvid),
            cookies=cookies or {},
            timeout=timeout,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise BilibiliSubtitleError(
                "字幕文件 HTTP {}".format(response.status_code)
            )
        payload = response.json()
    except BilibiliSubtitleError:
        raise
    except (requests.RequestException, ValueError, KeyError) as exc:
        raise BilibiliSubtitleError("字幕文件下载或解析失败") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("body"), list):
        raise BilibiliSubtitleError("字幕文件缺少 body 列表")
    return payload


def _srt_time(seconds):
    milliseconds = max(0, int(round(float(seconds) * 1000.0)))
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, millis = divmod(remainder, 1000)
    return "{:02d}:{:02d}:{:02d},{:03d}".format(hours, minutes, secs, millis)


def _srt_text(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = text.replace("\\N", "\n").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def subtitle_json_to_srt(payload):
    """Convert Bilibili's ``body`` cues to a UTF-8 SubRip document."""
    cues = _subtitle_cues(payload)

    lines = []
    for number, (start, end, text) in enumerate(cues, 1):
        lines.extend(
            [
                str(number),
                "{} --> {}".format(_srt_time(start), _srt_time(end)),
                text,
                "",
            ]
        )
    return "\n".join(lines)


def _subtitle_cues(payload):
    body = payload.get("body") if isinstance(payload, dict) else None
    if not isinstance(body, list):
        raise BilibiliSubtitleError("字幕文件缺少 body 列表")

    cues = []
    for cue in body:
        if not isinstance(cue, dict):
            continue
        try:
            start = max(0.0, float(cue.get("from")))
            end = float(cue.get("to"))
        except (TypeError, ValueError):
            continue
        text = _srt_text(cue.get("content"))
        if not text or end <= start:
            continue
        cues.append((start, end, text))

    if not cues:
        raise BilibiliSubtitleError("字幕文件没有有效条目")
    return cues


def _ass_time(seconds):
    centiseconds = max(0, int(round(float(seconds) * 100.0)))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cents = divmod(remainder, 100)
    return "{}:{:02d}:{:02d}.{:02d}".format(hours, minutes, secs, cents)


def _ass_text(value):
    return (
        _srt_text(value)
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", "\\N")
    )


def _official_subtitle_style(font_size):
    size = max(16.0, min(96.0, float(font_size)))
    return (
        "Style: BilibiliSubtitle,Arial,{:.0f},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        "&H64000000,0,0,0,0,100,100,0,0,1,2.5,0,2,60,60,48,1"
    ).format(size)


def _standalone_ass(font_size):
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            _official_subtitle_style(font_size),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
            "Effect, Text",
        ]
    ) + "\n"


def subtitle_json_to_ass(payload, danmaku_ass=None, font_size=42):
    """Render an official subtitle as ASS, optionally extending danmaku ASS."""
    document = str(danmaku_ass or "").lstrip("\ufeff")
    marker = "[Events]"
    if document:
        if marker not in document:
            raise BilibiliSubtitleError("弹幕 ASS 缺少 Events 段")
        style = _official_subtitle_style(font_size) + "\n\n"
        document = document.replace(marker, style + marker, 1).rstrip() + "\n"
    else:
        document = _standalone_ass(font_size)
    for start, end, text in _subtitle_cues(payload):
        document += "Dialogue: 5,{},{},BilibiliSubtitle,,0,0,0,,{}\n".format(
            _ass_time(start), _ass_time(end), _ass_text(text)
        )
    return document


def _language_family(language):
    normalized = str(language or "").lower().replace("_", "-")
    if normalized.startswith("ai-"):
        normalized = normalized[3:]
    if normalized in ("zh", "zh-hans", "zh-cn", "zh-sg"):
        return "zh-hans"
    if normalized in ("zh-hant", "zh-tw", "zh-hk", "zh-mo"):
        return "zh-hant"
    if normalized.startswith("en"):
        return "en"
    return normalized.split("-", 1)[0] or "und"


def _track_sort_key(track, preference):
    family = _language_family(track.get("language"))
    if preference == "auto":
        preferred = ("zh-hans", "zh-hant", "en")
    else:
        preferred = (preference, "zh-hans", "zh-hant", "en")
    ordered = []
    for value in preferred:
        if value not in ordered:
            ordered.append(value)
    try:
        priority = ordered.index(family)
    except ValueError:
        priority = len(ordered)
    return priority, int(track.get("index", 0))


def _filename_language(language):
    family = _language_family(language)
    aliases = {"zh-hans": "zh", "zh-hant": "zh", "en": "en"}
    token = aliases.get(family, family)
    if not re.fullmatch(r"[a-z]{2,3}", token):
        return "und"
    return token


def _safe_token(value, fallback):
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-")
    return (token or fallback)[:80]


def _clear_cid_output_dir(temp_dir, cid):
    """Remove only this video's stale generated subtitle tracks."""
    root = os.path.realpath(os.path.join(temp_dir, "bilibili-subtitles"))
    target = os.path.realpath(os.path.join(root, _safe_token(cid, "unknown-cid")))
    try:
        owned = os.path.commonpath((root, target)) == root and target != root
    except ValueError:
        owned = False
    if not owned:
        raise BilibiliSubtitleError("字幕临时目录超出插件范围")
    if os.path.isdir(target):
        shutil.rmtree(target)


def _track_name(track):
    name = html.unescape(str(track.get("language_name") or "")).strip()
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        family = _language_family(track.get("language"))
        name = {
            "zh-hans": "中文（简体）",
            "zh-hant": "中文（繁体）",
            "en": "English",
        }.get(family, str(track.get("language") or "未知字幕"))
    return name[:80]


def _track_output_dir(temp_dir, cid, track, ordinal):
    cid_token = _safe_token(cid, "unknown-cid")
    track_token = _safe_token(
        track.get("id"), "track-{}".format(int(ordinal) + 1)
    )
    path = os.path.join(
        temp_dir, "bilibili-subtitles", cid_token, track_token
    )
    os.makedirs(path, exist_ok=True)
    return path


def write_subtitle_srt(payload, temp_dir, cid, track, ordinal=0):
    language = _filename_language(track.get("language"))
    filename = "{}.{}.srt".format(_track_name(track), language)
    path = os.path.join(
        _track_output_dir(temp_dir, cid, track, ordinal), filename
    )
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8-sig", newline="\n") as subtitle_file:
        subtitle_file.write(subtitle_json_to_srt(payload))
    os.replace(temporary, path)
    return path


def write_subtitle_ass(payload, temp_dir, cid, track, font_size=42, ordinal=0):
    language = _filename_language(track.get("language"))
    filename = "{}.{}.ass".format(_track_name(track), language)
    path = os.path.join(
        _track_output_dir(temp_dir, cid, track, ordinal), filename
    )
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8-sig", newline="\n") as output:
        output.write(subtitle_json_to_ass(payload, font_size=font_size))
    os.replace(temporary, path)
    return path


def write_subtitle_with_danmaku(
    payload, temp_dir, cid, track, danmaku_path, ordinal=0, font_size=42
):
    language = _filename_language(track.get("language"))
    filename = "{}.{}.ass".format(_track_name(track), language)
    path = os.path.join(
        _track_output_dir(temp_dir, cid, track, ordinal), filename
    )
    with open(danmaku_path, encoding="utf-8-sig") as source:
        combined = subtitle_json_to_ass(
            payload, source.read(), font_size=font_size
        )
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8-sig", newline="\n") as output:
        output.write(combined)
    os.replace(temporary, path)
    return path


def prepare_bilibili_subtitles(
    bvid,
    cid,
    temp_dir,
    addon,
    cookies=None,
    danmaku_path=None,
    wbi_signer=None,
):
    """Download available official tracks and return ordered local ASS paths."""
    settings = subtitle_settings(addon)
    if not settings["enabled"]:
        return []

    tracks = fetch_subtitle_tracks(
        bvid, cid, cookies=cookies, wbi_signer=wbi_signer
    )
    _clear_cid_output_dir(temp_dir, cid)
    tracks.sort(key=lambda track: _track_sort_key(track, settings["language"]))
    paths = []
    for ordinal, track in enumerate(tracks):
        try:
            payload = fetch_subtitle_document(track, bvid, cookies=cookies)
            if danmaku_path:
                paths.append(
                    write_subtitle_with_danmaku(
                        payload,
                        temp_dir,
                        cid,
                        track,
                        danmaku_path,
                        ordinal,
                        settings["font_size"],
                    )
                )
            else:
                paths.append(
                    write_subtitle_ass(
                        payload,
                        temp_dir,
                        cid,
                        track,
                        settings["font_size"],
                        ordinal,
                    )
                )
        except (BilibiliSubtitleError, OSError):
            # A single expired/removed language must not discard other tracks.
            continue
    if tracks and not paths:
        raise BilibiliSubtitleError(
            "发现 {} 条官方字幕，但下载或转换均失败".format(len(tracks))
        )
    return paths


__all__ = [
    "BilibiliSubtitleError",
    "fetch_subtitle_document",
    "fetch_subtitle_tracks",
    "prepare_bilibili_subtitles",
    "subtitle_json_to_ass",
    "subtitle_json_to_srt",
    "subtitle_settings",
    "write_subtitle_ass",
    "write_subtitle_srt",
    "write_subtitle_with_danmaku",
]
