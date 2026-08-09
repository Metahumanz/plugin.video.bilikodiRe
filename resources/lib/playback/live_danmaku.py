"""Bilibili live danmaku transport and native Kodi ASS subtitle buffering."""

import base64
import hashlib
import json
import os
import queue
import socket
import ssl
import struct
import threading
import time
import urllib.parse
import zlib

from .danmaku import generate_ass


LIVE_CONTEXT_FILENAME = "live-context.json"
LIVE_DANMAKU_INFO_URL = (
    "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo"
)
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/120.0.0.0 Safari/537.36"
)
MIXIN_KEY_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]
BILI_HEADER = struct.Struct(">IHHII")


class LiveDanmakuError(RuntimeError):
    pass


def _context_path(temp_dir):
    return os.path.join(temp_dir, LIVE_CONTEXT_FILENAME)


def write_live_context(temp_dir, room_id, stream_url):
    """Record just enough of the selected URL for the service to identify it."""
    parsed = urllib.parse.urlsplit(str(stream_url or "").split("|", 1)[0])
    context = {
        "room_id": str(room_id),
        "host": parsed.hostname or "",
        "path": parsed.path or "",
        "created": time.time(),
    }
    os.makedirs(temp_dir, exist_ok=True)
    path = _context_path(temp_dir)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(context, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, path)
    return context


def read_live_context(temp_dir):
    try:
        with open(_context_path(temp_dir), encoding="utf-8") as handle:
            context = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    return context if isinstance(context, dict) else None


def live_context_matches(context, playing_url, now=None, max_age=120):
    if not isinstance(context, dict) or not context.get("room_id"):
        return False
    if max_age is not None:
        now = time.time() if now is None else float(now)
        try:
            if now - float(context.get("created") or 0) > float(max_age):
                return False
        except (TypeError, ValueError):
            return False
    parsed = urllib.parse.urlsplit(str(playing_url or "").split("|", 1)[0])
    return bool(
        parsed.hostname
        and parsed.path
        and parsed.hostname == context.get("host")
        and parsed.path == context.get("path")
    )


def _wbi_params(params, img_key, sub_key, timestamp=None):
    mixin = "".join((img_key + sub_key)[index] for index in MIXIN_KEY_TABLE)[:32]
    values = dict(params)
    values["wts"] = int(time.time() if timestamp is None else timestamp)
    values = {
        key: "".join(char for char in str(value) if char not in "!'()*")
        for key, value in sorted(values.items())
    }
    query = urllib.parse.urlencode(values)
    values["w_rid"] = hashlib.md5((query + mixin).encode("utf-8")).hexdigest()
    return values


def fetch_live_danmaku_info(room_id, cookies=None, timeout=20, session=None):
    """Return the signed live danmaku token and WebSocket hosts."""
    import requests

    client = session or requests.Session()
    if cookies:
        client.cookies.update(cookies)
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://live.bilibili.com/{}/".format(room_id),
        "Origin": "https://live.bilibili.com",
    }
    try:
        nav = client.get(NAV_URL, headers=headers, timeout=timeout).json()
        wbi = (nav.get("data") or {}).get("wbi_img") or {}
        img_key = str(wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
        sub_key = str(wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
        if not img_key or not sub_key:
            raise LiveDanmakuError("无法获取直播弹幕 WBI 密钥")
        params = _wbi_params(
            {"id": room_id, "type": 0, "web_location": "444.8"},
            img_key,
            sub_key,
        )
        raw = client.get(
            LIVE_DANMAKU_INFO_URL,
            params=params,
            headers=headers,
            timeout=timeout,
        ).json()
    except (requests.RequestException, ValueError) as exc:
        raise LiveDanmakuError("获取直播弹幕连接信息失败: {}".format(exc)) from exc
    if raw.get("code") != 0:
        raise LiveDanmakuError(
            "直播弹幕接口失败 {}: {}".format(raw.get("code"), raw.get("message"))
        )
    data = raw.get("data") or {}
    hosts = [
        host for host in (data.get("host_list") or [])
        if host.get("host") and int(host.get("wss_port") or 0) > 0
    ]
    if not data.get("token") or not hosts:
        raise LiveDanmakuError("直播弹幕接口没有返回 token 或 WSS 主机")
    return {"token": data["token"], "hosts": hosts}


def encode_bili_packet(payload, operation, protocol_version=1, sequence=1):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    payload = bytes(payload or b"")
    return BILI_HEADER.pack(
        BILI_HEADER.size + len(payload),
        BILI_HEADER.size,
        int(protocol_version),
        int(operation),
        int(sequence),
    ) + payload


def _json_message(payload):
    try:
        value = json.loads(payload.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeDecodeError):
        return []
    return [value] if isinstance(value, dict) else []


def decode_bili_messages(packet):
    """Decode operation-5 JSON messages, including zlib-compressed envelopes."""
    messages = []
    offset = 0
    packet = bytes(packet or b"")
    while offset + BILI_HEADER.size <= len(packet):
        total, header_size, protocol, operation, _ = BILI_HEADER.unpack_from(packet, offset)
        if total < header_size or header_size < BILI_HEADER.size or offset + total > len(packet):
            break
        payload = packet[offset + header_size:offset + total]
        if operation == 5:
            if protocol == 2:
                try:
                    messages.extend(decode_bili_messages(zlib.decompress(payload)))
                except zlib.error:
                    pass
            elif protocol == 3:
                try:
                    import brotli
                    messages.extend(decode_bili_messages(brotli.decompress(payload)))
                except (ImportError, RuntimeError, ValueError):
                    pass
            else:
                messages.extend(_json_message(payload))
        offset += total
    return messages


def extract_live_comments(messages):
    comments = []
    for message in messages or []:
        command = str((message or {}).get("cmd") or "").split(":", 1)[0]
        if command != "DANMU_MSG":
            continue
        info = message.get("info") or []
        if len(info) < 2:
            continue
        metadata = info[0] if isinstance(info[0], list) else []
        text = str(info[1] or "").strip()
        if not text:
            continue
        try:
            mode = int(metadata[1])
        except (IndexError, TypeError, ValueError):
            mode = 1
        try:
            size = float(metadata[2])
        except (IndexError, TypeError, ValueError):
            size = 25
        try:
            color = int(metadata[3])
        except (IndexError, TypeError, ValueError):
            color = 0xFFFFFF
        comments.append({
            "mode": mode if mode in (1, 2, 3, 4, 5, 6) else 1,
            "size": size,
            "color": max(0, min(0xFFFFFF, color)),
            "text": text,
        })
    return comments


def _websocket_frame(payload, opcode=2):
    payload = bytes(payload or b"")
    mask = os.urandom(4)
    length = len(payload)
    header = bytearray([0x80 | int(opcode)])
    if length < 126:
        header.append(0x80 | length)
    elif length <= 0xFFFF:
        header.append(0x80 | 126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack(">Q", length))
    header.extend(mask)
    header.extend(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes(header)


def _read_exact(connection, length, stop_event):
    chunks = bytearray()
    while len(chunks) < length:
        if stop_event.is_set():
            raise LiveDanmakuError("直播弹幕连接已停止")
        try:
            chunk = connection.recv(length - len(chunks))
        except socket.timeout:
            if chunks:
                continue
            raise
        if not chunk:
            raise LiveDanmakuError("直播弹幕连接已关闭")
        chunks.extend(chunk)
    return bytes(chunks)


def _read_websocket_frame(connection, stop_event):
    header = _read_exact(connection, 2, stop_event)
    first, second = header
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", _read_exact(connection, 2, stop_event))[0]
    elif length == 127:
        length = struct.unpack(">Q", _read_exact(connection, 8, stop_event))[0]
    mask = _read_exact(connection, 4, stop_event) if second & 0x80 else None
    payload = _read_exact(connection, length, stop_event)
    if mask:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bool(first & 0x80), opcode, payload


class LiveDanmakuClient:
    """Reconnectable WSS reader that exposes parsed live comments via a queue."""

    def __init__(self, room_id, cookies=None, log=None, queue_size=500):
        self.room_id = int(room_id)
        self.cookies = dict(cookies or {})
        self.log = log or (lambda message: None)
        self.messages = queue.Queue(maxsize=max(10, int(queue_size)))
        self.stop_event = threading.Event()
        self.thread = None
        self.connection = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            name="bilikodi-live-danmaku-{}".format(self.room_id),
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        connection = self.connection
        self.connection = None
        if connection:
            try:
                connection.close()
            except OSError:
                pass
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
        self.thread = None

    def drain(self, maximum=250):
        output = []
        for _ in range(max(1, int(maximum))):
            try:
                output.append(self.messages.get_nowait())
            except queue.Empty:
                break
        return output

    def _queue_comment(self, comment):
        try:
            self.messages.put_nowait(comment)
        except queue.Full:
            try:
                self.messages.get_nowait()
            except queue.Empty:
                pass
            try:
                self.messages.put_nowait(comment)
            except queue.Full:
                pass

    def _handshake(self, host, port):
        raw = socket.create_connection((host, port), timeout=10)
        context = ssl.create_default_context()
        connection = context.wrap_socket(raw, server_hostname=host)
        connection.settimeout(1)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET /sub HTTP/1.1\r\n"
            "Host: {}:{}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Origin: https://live.bilibili.com\r\n"
            "User-Agent: {}\r\n\r\n"
        ).format(host, port, key, USER_AGENT)
        connection.sendall(request.encode("utf-8"))
        response = bytearray()
        while b"\r\n\r\n" not in response and len(response) < 16384:
            response.extend(_read_exact(connection, 1, self.stop_event))
        if not response.startswith(b"HTTP/1.1 101"):
            connection.close()
            raise LiveDanmakuError("直播弹幕 WebSocket 握手失败")
        return connection

    def _connect_and_read(self):
        info = fetch_live_danmaku_info(self.room_id, self.cookies)
        connection = None
        last_error = None
        for host_info in info["hosts"]:
            host = str(host_info["host"])
            port = int(host_info["wss_port"])
            try:
                connection = self._handshake(host, port)
                break
            except (OSError, LiveDanmakuError) as exc:
                last_error = exc
        if connection is None:
            raise LiveDanmakuError(
                "所有直播弹幕 WSS 主机均连接失败: {}".format(last_error)
            )
        self.connection = connection
        try:
            auth = json.dumps({
                "uid": int(self.cookies.get("DedeUserID") or 0),
                "roomid": self.room_id,
                "protover": 2,
                "platform": "web",
                "type": 2,
                "key": info["token"],
            }, separators=(",", ":")).encode("utf-8")
            connection.sendall(_websocket_frame(encode_bili_packet(auth, 7), 2))
            last_heartbeat = 0.0
            fragments = bytearray()
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now - last_heartbeat >= 25:
                    heartbeat = encode_bili_packet(b"[object Object]", 2)
                    connection.sendall(_websocket_frame(heartbeat, 2))
                    last_heartbeat = now
                try:
                    final, opcode, payload = _read_websocket_frame(
                        connection, self.stop_event
                    )
                except socket.timeout:
                    continue
                if opcode == 8:
                    raise LiveDanmakuError("直播弹幕 WebSocket 已关闭")
                if opcode == 9:
                    connection.sendall(_websocket_frame(payload, 10))
                    continue
                if opcode in (0, 2):
                    fragments.extend(payload)
                    if final:
                        for comment in extract_live_comments(
                            decode_bili_messages(bytes(fragments))
                        ):
                            self._queue_comment(comment)
                        fragments.clear()
        finally:
            self.connection = None
            try:
                connection.close()
            except OSError:
                pass

    def _run(self):
        delay = 1
        while not self.stop_event.is_set():
            try:
                self._connect_and_read()
                delay = 1
            except Exception as exc:
                if not self.stop_event.is_set():
                    self.log("直播弹幕连接失败，将重试: {}".format(exc))
            if self.stop_event.wait(delay):
                break
            delay = min(delay * 2, 30)


class LiveSubtitleBuffer:
    """Assign live comments Kodi times and write alternating ASS tracks."""

    def __init__(self, room_id, lead_time=2.0, history=12.0):
        self.room_id = str(room_id)
        self.lead_time = float(lead_time)
        self.history = float(history)
        self.comments = []
        self.sequence = 0
        self.dirty = False

    def add(self, comments, playback_time):
        base = max(0.0, float(playback_time) + self.lead_time)
        for index, comment in enumerate(comments or []):
            value = dict(comment)
            value["time"] = base + min(index * 0.04, 1.0)
            self.comments.append(value)
        if comments:
            self.dirty = True

    def render(self, temp_dir, playback_time, settings):
        cutoff = max(0.0, float(playback_time) - self.history)
        self.comments = [comment for comment in self.comments if comment["time"] >= cutoff]
        ass = generate_ass(self.comments, **settings)
        os.makedirs(temp_dir, exist_ok=True)
        suffix = "a" if self.sequence % 2 == 0 else "b"
        path = os.path.join(temp_dir, "live-{}-{}.ass".format(self.room_id, suffix))
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8-sig", newline="\n") as handle:
            handle.write(ass)
        os.replace(temporary, path)
        self.sequence += 1
        self.dirty = False
        return path


__all__ = [
    "LiveDanmakuClient",
    "LiveDanmakuError",
    "LiveSubtitleBuffer",
    "decode_bili_messages",
    "encode_bili_packet",
    "extract_live_comments",
    "fetch_live_danmaku_info",
    "live_context_matches",
    "read_live_context",
    "write_live_context",
]
