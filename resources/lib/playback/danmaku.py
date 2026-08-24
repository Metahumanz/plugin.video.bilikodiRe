"""Fetch Bilibili XML comments and turn them into Kodi-rendered ASS subtitles."""

import os
import re
import xml.etree.ElementTree as ET

COMMENT_URL = "https://comment.bilibili.com/{}.xml"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
    "Chrome/120.0.0.0 Safari/537.36"
)


class DanmakuError(RuntimeError):
    pass


def _setting_bool(addon, name, default):
    value = addon.getSetting(name)
    if not value:
        return bool(default)
    return value.lower() == "true"


def _setting_number(addon, name, default, minimum, maximum):
    try:
        value = float(addon.getSetting(name))
    except (TypeError, ValueError):
        value = float(default)
    return max(float(minimum), min(float(maximum), value))


def danmaku_settings(addon):
    return {
        "enabled": _setting_bool(addon, "danmaku_enabled", False),
        "font_size": _setting_number(addon, "danmaku_font_size", 36, 12, 100),
        "opacity": _setting_number(addon, "danmaku_opacity", 85, 10, 100) / 100.0,
        "display_area": _setting_number(addon, "danmaku_display_area", 50, 20, 100) / 100.0,
        "scroll": _setting_bool(addon, "danmaku_scroll", True),
        "top": _setting_bool(addon, "danmaku_top", True),
        "bottom": _setting_bool(addon, "danmaku_bottom", True),
        "avoid_overlap": _setting_bool(addon, "danmaku_avoid_overlap", True),
    }


def fetch_danmaku_xml(cid, cookies=None, timeout=20):
    import requests

    try:
        response = requests.get(
            COMMENT_URL.format(cid),
            headers={"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"},
            cookies=cookies or {},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DanmakuError("获取弹幕失败: {}".format(exc)) from exc
    return response.content


def parse_danmaku(xml_data):
    if isinstance(xml_data, bytes):
        xml_data = xml_data.decode("utf-8", errors="replace")
    # XML 1.0 rejects control characters occasionally found in old comments.
    xml_data = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml_data)
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        raise DanmakuError("弹幕 XML 无法解析") from exc

    comments = []
    for node in root.findall(".//d"):
        fields = (node.get("p") or "").split(",")
        if len(fields) < 4:
            continue
        try:
            timeline = max(0.0, float(fields[0]))
            mode = int(fields[1])
            size = max(12.0, float(fields[2]))
            color = max(0, min(0xFFFFFF, int(fields[3])))
        except (TypeError, ValueError):
            continue
        text = (node.text or "").strip()
        if text and mode in (1, 2, 3, 4, 5, 6):
            comments.append(
                {"time": timeline, "mode": mode, "size": size, "color": color, "text": text}
            )
    return sorted(comments, key=lambda item: item["time"])


def _ass_time(seconds):
    centiseconds = max(0, int(round(float(seconds) * 100)))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cents = divmod(remainder, 100)
    return "{}:{:02d}:{:02d}.{:02d}".format(hours, minutes, secs, cents)


def _ass_text(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r", "")
        .replace("\n", "\\N")
    )


def _ass_color(rgb):
    red = (rgb >> 16) & 0xFF
    green = (rgb >> 8) & 0xFF
    blue = rgb & 0xFF
    return "{:02X}{:02X}{:02X}".format(blue, green, red)


def _scroll_lane_available(state, candidate, screen_width):
    """Check entry spacing and catch-up risk for two moving comments."""
    if state is None or state["end"] <= candidate["start"]:
        return True
    if state["kind"] != "scroll" or state["direction"] != candidate["direction"]:
        return False

    elapsed = candidate["start"] - state["start"]
    if elapsed < 0:
        return False
    previous_speed = (float(screen_width) + state["width"]) / state["duration"]
    candidate_speed = (
        float(screen_width) + candidate["width"]
    ) / candidate["duration"]

    # The preceding comment's trailing edge must have entered far enough for
    # the next comment to appear at the screen boundary with a visible gap.
    entry_gap = previous_speed * elapsed - state["width"]
    if entry_gap < candidate["gap"]:
        return False

    # A longer following comment moves faster when duration is fixed. Ensure
    # it cannot catch the previous one before the latter leaves the screen.
    if candidate_speed > previous_speed:
        remaining = max(0.0, state["end"] - candidate["start"])
        closing_distance = (candidate_speed - previous_speed) * remaining
        if entry_gap - candidate["gap"] < closing_distance:
            return False
    return True


def _lane_available(state, candidate, screen_width):
    if state is None or state["end"] <= candidate["start"]:
        return True
    if candidate["kind"] == "scroll":
        return _scroll_lane_available(state, candidate, screen_width)
    return False


def _pick_lane(
    lanes, candidate, screen_width, reverse=False, allow_overlap=False
):
    indices = range(len(lanes) - 1, -1, -1) if reverse else range(len(lanes))
    for index in indices:
        if _lane_available(lanes[index], candidate, screen_width):
            return index
    if allow_overlap:
        return min(
            range(len(lanes)),
            key=lambda index: lanes[index]["end"] if lanes[index] else 0.0,
        )
    return None


def generate_ass(
    comments,
    width=1920,
    height=1080,
    font_size=36,
    opacity=0.85,
    display_area=0.5,
    scroll=True,
    top=True,
    bottom=True,
    avoid_overlap=True,
    scroll_duration=8.0,
    still_duration=4.0,
):
    font_size = max(12.0, float(font_size))
    area_height = max(int(font_size * 1.5), int(height * float(display_area)))
    line_height = max(18, int(font_size * 1.25))
    lane_count = max(1, area_height // line_height)
    # All comment modes share absolute visual rows. This prevents a fixed
    # comment from occupying the same area as a scrolling comment.
    lanes = [None] * lane_count
    alpha = int(round(255 * (1.0 - max(0.0, min(1.0, float(opacity))))))

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "Collisions: Normal",
        "PlayResX: {}".format(int(width)),
        "PlayResY: {}".format(int(height)),
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Danmaku,Arial,{:.0f},&H{:02X}FFFFFF,&H{:02X}FFFFFF,&H{:02X}000000,&H{:02X}000000,"
        "0,0,0,0,100,100,0,0,1,1.5,0,7,0,0,0,1".format(
            font_size, alpha, alpha, alpha, alpha
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for comment in comments:
        mode = int(comment["mode"])
        start = float(comment["time"])
        color = _ass_color(int(comment["color"]))
        size = font_size * (float(comment["size"]) / 25.0)
        size = max(font_size * 0.65, min(font_size * 1.8, size))
        text = _ass_text(comment["text"])
        # Explicit alpha keeps colour, glyph and outline opacity in sync in
        # libass; previously the half-opaque fixed outline hid most changes.
        common = "\\fs{:.0f}\\c&H{}&\\alpha&H{:02X}&".format(size, color, alpha)

        if mode in (1, 2, 3, 6) and scroll:
            duration = float(scroll_duration)
            estimated_width = max(size, len(comment["text"]) * size)
            candidate = {
                "kind": "scroll",
                "start": start,
                "end": start + duration,
                "duration": duration,
                "width": estimated_width,
                "direction": "ltr" if mode == 6 else "rtl",
                "gap": max(12.0, size * 0.35),
            }
            lane = _pick_lane(
                lanes, candidate, width, allow_overlap=not avoid_overlap
            )
            if lane is None:
                continue
            lanes[lane] = candidate
            y = 10 + lane * line_height
            if mode == 6:
                movement = "\\move({:.0f},{},{},{},0,{:.0f})".format(
                    -estimated_width, y, width, y, duration * 1000
                )
            else:
                movement = "\\move({},{},{:.0f},{},0,{:.0f})".format(
                    width, y, -estimated_width, y, duration * 1000
                )
        elif mode == 5 and top:
            duration = float(still_duration)
            candidate = {"kind": "fixed", "start": start, "end": start + duration}
            lane = _pick_lane(
                lanes, candidate, width, allow_overlap=not avoid_overlap
            )
            if lane is None:
                continue
            lanes[lane] = candidate
            movement = "\\an8\\pos({},{})".format(width // 2, 10 + lane * line_height)
        elif mode == 4 and bottom:
            duration = float(still_duration)
            candidate = {"kind": "fixed", "start": start, "end": start + duration}
            lane = _pick_lane(
                lanes,
                candidate,
                width,
                reverse=True,
                allow_overlap=not avoid_overlap,
            )
            if lane is None:
                continue
            lanes[lane] = candidate
            movement = "\\an2\\pos({},{})".format(
                width // 2, min(area_height, 10 + (lane + 1) * line_height)
            )
        else:
            continue

        lines.append(
            "Dialogue: 2,{},{},Danmaku,,0,0,0,,{{{}{}}}{}".format(
                _ass_time(start), _ass_time(start + duration), common, movement, text
            )
        )

    return "\n".join(lines) + "\n"


def prepare_danmaku(cid, temp_dir, addon, cookies=None):
    settings = danmaku_settings(addon)
    if not settings.pop("enabled"):
        return None
    xml_data = fetch_danmaku_xml(cid, cookies=cookies)
    comments = parse_danmaku(xml_data)
    ass = generate_ass(comments, **settings)
    safe_cid = "".join(
        char for char in str(cid) if char.isalnum() or char in ("-", "_")
    ) or "unknown"
    output_dir = os.path.join(temp_dir, "bilibili-danmaku", safe_cid)
    os.makedirs(output_dir, exist_ok=True)
    # A descriptive, language-tagged filename gives Kodi a stable stream name
    # and lets it reselect this first Chinese track after an ISA stream reset.
    # The previous numeric-only filename appeared as an unnamed/unknown track.
    path = os.path.join(output_dir, "Bilibili Danmaku.zh.ass")
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8-sig", newline="\n") as subtitle:
        subtitle.write(ass)
    os.replace(temporary, path)
    return path


__all__ = [
    "DanmakuError",
    "danmaku_settings",
    "fetch_danmaku_xml",
    "generate_ass",
    "parse_danmaku",
    "prepare_danmaku",
]
