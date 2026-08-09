"""Playback context and Bilibili heartbeat helpers."""

import json
import os
import time

CONTEXT_FILENAME = "playback-context.json"
HEARTBEAT_URL = "https://api.bilibili.com/x/click-interface/web/heartbeat"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}


def context_path(temp_dir):
    return os.path.join(temp_dir, CONTEXT_FILENAME)


def write_playback_context(temp_dir, bvid, cid):
    os.makedirs(temp_dir, exist_ok=True)
    target = context_path(temp_dir)
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8") as output:
        json.dump(
            {"bvid": str(bvid), "cid": str(cid), "created": time.time()},
            output,
            ensure_ascii=True,
        )
    os.replace(temporary, target)
    return target


def read_playback_context(temp_dir, max_age=120):
    try:
        with open(context_path(temp_dir), "r", encoding="utf-8") as source:
            context = json.load(source)
        if time.time() - float(context.get("created", 0)) > float(max_age):
            return None
        if not context.get("bvid") or not context.get("cid"):
            return None
        return context
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def report_progress(context, played_time, cookies):
    import requests

    if not context or not isinstance(cookies, dict) or not cookies:
        return False
    csrf = cookies.get("bili_jct")
    if not csrf:
        return False
    data = {
        "bvid": context["bvid"],
        "cid": context["cid"],
        "played_time": max(0, int(float(played_time))),
        "csrf": csrf,
    }
    try:
        response = requests.post(
            HEARTBEAT_URL,
            data=data,
            cookies=cookies,
            headers=HEADERS,
            timeout=10,
        )
        payload = response.json()
        return response.ok and payload.get("code") == 0
    except (requests.RequestException, ValueError, TypeError):
        return False


__all__ = [
    "context_path",
    "read_playback_context",
    "report_progress",
    "write_playback_context",
]
