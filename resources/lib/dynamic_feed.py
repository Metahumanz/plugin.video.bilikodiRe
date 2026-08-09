"""Small pure helpers for turning Bilibili dynamics into Kodi video items."""

from datetime import datetime
import time


def format_dynamic_time(timestamp, now=None):
    try:
        timestamp = int(timestamp)
    except (TypeError, ValueError):
        return ""
    now = int(time.time() if now is None else now)
    delta = max(0, now - timestamp)
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return "{}分钟前".format(delta // 60)
    if delta < 86400:
        return "{}小时前".format(delta // 3600)
    created = datetime.fromtimestamp(timestamp)
    if delta < 172800:
        return "昨天 {}".format(created.strftime("%H:%M"))
    if delta < 7 * 86400:
        return "{}天前".format(delta // 86400)
    return created.strftime("%Y-%m-%d")


def normalize_dynamic(dynamic, now=None):
    modules = (dynamic or {}).get("modules") or {}
    module_dynamic = modules.get("module_dynamic") or {}
    archive = (module_dynamic.get("major") or {}).get("archive") or {}
    if not archive.get("bvid"):
        return None

    author = modules.get("module_author") or {}
    title = archive.get("title") or "动态视频"
    author_name = author.get("name") or "未知 UP"
    pub_ts = int(author.get("pub_ts") or 0)
    dynamic_desc = (module_dynamic.get("desc") or {}).get("text") or ""
    archive_desc = archive.get("desc") or ""
    descriptions = [text for text in (dynamic_desc, archive_desc) if text]
    if len(descriptions) == 2 and descriptions[0] == descriptions[1]:
        descriptions.pop()
    relative_time = format_dynamic_time(pub_ts, now=now) if pub_ts else ""
    prefix = "{} · {}".format(relative_time, author_name) if relative_time else author_name

    return {
        "label": "{} · {}".format(prefix, title),
        "video": {
            "bvid": archive.get("bvid"),
            "title": title,
            "pic": archive.get("cover") or "",
            "duration_text": archive.get("duration_text") or "0:00",
            "desc": "\n\n".join(descriptions),
            "author": author_name,
            "mid": author.get("mid") or 0,
            "pubdate": pub_ts,
            "stat": archive.get("stat") or {},
        },
    }


__all__ = ["format_dynamic_time", "normalize_dynamic"]
