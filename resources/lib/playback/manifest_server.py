"""Loopback-only HTTP transport for generated InputStream Adaptive MPDs."""

import os
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlparse


ADDON_ID = "plugin.video.bilikodiRe"
PORT_FILENAME = "manifest-server.port"
URL_PREFIX = "/{}/manifest/".format(ADDON_ID)


class ManifestServerError(RuntimeError):
    """Raised when the Kodi manifest service is unavailable."""


def port_file_path(temp_dir):
    return os.path.join(temp_dir, PORT_FILENAME)


def write_port_file(temp_dir, port):
    os.makedirs(temp_dir, exist_ok=True)
    path = port_file_path(temp_dir)
    temporary_path = path + ".tmp"
    with open(temporary_path, "w", encoding="ascii") as port_file:
        port_file.write(str(int(port)))
    os.replace(temporary_path, path)
    return path


def remove_port_file(temp_dir, expected_port=None):
    path = port_file_path(temp_dir)
    try:
        if expected_port is not None:
            with open(path, "r", encoding="ascii") as port_file:
                if port_file.read().strip() != str(int(expected_port)):
                    return
        os.remove(path)
    except (FileNotFoundError, OSError, ValueError):
        pass


def _handler_for(temp_dir):
    root = os.path.realpath(temp_dir)

    class ManifestRequestHandler(BaseHTTPRequestHandler):
        server_version = "BilikodiManifest/1.0"

        def _manifest_path(self):
            request_path = unquote(urlparse(self.path).path)
            if not request_path.startswith(URL_PREFIX):
                return None
            filename = request_path[len(URL_PREFIX):]
            if not filename or filename != os.path.basename(filename):
                return None
            if not filename.endswith(".mpd"):
                return None
            candidate = os.path.realpath(os.path.join(root, filename))
            try:
                if os.path.commonpath((root, candidate)) != root:
                    return None
            except ValueError:
                return None
            return candidate

        def _serve(self, include_body):
            path = self._manifest_path()
            if not path or not os.path.isfile(path):
                self.send_error(404, "MPD not found")
                return
            try:
                size = os.path.getsize(path)
                self.send_response(200)
                self.send_header("Content-Type", "application/dash+xml")
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if include_body:
                    with open(path, "rb") as manifest:
                        while True:
                            chunk = manifest.read(64 * 1024)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
            except (OSError, BrokenPipeError):
                return

        def do_GET(self):
            self._serve(include_body=True)

        def do_HEAD(self):
            self._serve(include_body=False)

        def log_message(self, message_format, *args):
            try:
                import xbmc

                xbmc.log(
                    "[bilikodiReborn] MPD HTTP " + (message_format % args),
                    xbmc.LOGINFO,
                )
            except ImportError:
                # Unit tests and standalone validation run outside Kodi.
                return

    return ManifestRequestHandler


def create_server(temp_dir):
    """Bind a manifest server to a random loopback port."""
    return ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(temp_dir))


def _read_port(temp_dir):
    try:
        with open(port_file_path(temp_dir), "r", encoding="ascii") as port_file:
            port = int(port_file.read().strip())
        if not 1 <= port <= 65535:
            raise ValueError
        return port
    except (FileNotFoundError, OSError, ValueError):
        return None


def manifest_url(mpd_path, temp_dir, timeout=2.0):
    """Return the service URL after confirming its loopback port is live."""
    deadline = time.monotonic() + max(float(timeout), 0.0)
    while True:
        port = _read_port(temp_dir)
        if port:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    filename = quote(os.path.basename(mpd_path))
                    return "http://127.0.0.1:{}{}{}".format(port, URL_PREFIX, filename)
            except OSError:
                pass
        if time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    raise ManifestServerError("本地 MPD 服务未启动，请重启 Kodi 后重试")


__all__ = [
    "ManifestServerError",
    "create_server",
    "manifest_url",
    "remove_port_file",
    "write_port_file",
]
