"""Local API for the pinned Stream Deck native background bridge."""
import argparse
import ctypes
from ctypes import wintypes
import datetime
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import msvcrt
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from canvas_transport import CanvasAssembler, decode_canvas, MAX_DATAGRAM

ROOT = Path(__file__).resolve().parent
FRAME_BYTES = 15 * 72 * 72 * 4
HASHES = {
    "StreamDeck.exe": "9B2E3D0069052F18F372B9C9AEA46E925CB463ACBA443A1075E68EC5648F769D",
    "Qt6Gui.dll": "8FCEEE959A670372AAA5763287C2EF7924CD9ECDBE2C29CF4B6C12A63079C503",
    "Qt6Core.dll": "FAE4778A42E93ADC82B831C879C886A05147E9CC26760808D21116BE5547259B",
}


def validate_lease(value):
    if type(value) is not int or not 500 <= value <= 10000:
        raise ValueError("lease_ms must be an integer from500 to10000")
    return value


def validate_colors(value):
    if not isinstance(value, list) or len(value) != 15:
        raise ValueError("Expected15 RGB triplets")
    if any(not isinstance(c, list) or len(c) != 3 or
           any(type(v) is not int or not 0 <= v <= 255 for v in c) for c in value):
        raise ValueError("Expected15 RGB triplets of integers0..255")
    return value


def validate_frame(data):
    if len(data) != FRAME_BYTES:
        raise ValueError("Expected311040 BGRA bytes")
    if set(data[3::4]) != {255}:
        raise ValueError("BGRA pixels must be opaque")
    return data


def session_active(deadline, stop_file, detached, faulted):
    """An unlimited lifetime never bypasses stop requests or native failures."""
    return (not stop_file.exists() and not detached.is_set() and not faulted.is_set()
            and (deadline is None or time.monotonic() < deadline))


def query_process_image(pid):
    """Read-only Windows query that includes elevated processes when permitted."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return Path(buffer.value)
    finally:
        kernel.CloseHandle(handle)


def absolute_runtime_directory(value):
    path = Path(os.path.expandvars(value))
    if not path.is_absolute() or any(char in str(path) for char in ('"', '\r', '\n')):
        raise argparse.ArgumentTypeError("runtime-directory must be an absolute path without quotes or line breaks")
    return path.resolve()


def runtime_locations(runtime_directory):
    if runtime_directory is not None:
        return runtime_directory / "locks", runtime_directory / "signalrgb-backups"
    return Path(os.environ["LOCALAPPDATA"]) / "CodexLocalBridges" / "StreamDeck" / "locks", None


class Api:
    def __init__(self, exports, token):
        self.exports, self.token = exports, token
        self.accepted = 0
        self.http_lease_until = 0.0
        self.canvas = CanvasAssembler()
        self.canvas_frames = 0
        self.canvas_rejected = 0
        self.canvas_decode_ms = 0.0
        self.canvas_sample_colors = []
        self.cached_layout = None

    def auth(self, supplied):
        return isinstance(supplied, str) and hmac.compare_digest(supplied, self.token)

    def colors(self, payload, *, udp=False):
        if not isinstance(payload, dict):
            raise ValueError("ExpectedJSON object")
        value = validate_colors(payload.get("colors"))
        lease = validate_lease(payload.get("lease_ms", 2000))
        if udp and time.monotonic() < self.http_lease_until:
            return {"accepted": False, "reason": "http-lease-active"}
        result = self.exports.setcolors(value, lease)
        if not udp:
            self.http_lease_until = time.monotonic() + lease / 1000
        self.accepted += 1
        return result

    def frame(self, body, lease):
        result = self.exports.setframe(validate_lease(lease), validate_frame(body))
        self.http_lease_until = time.monotonic() + lease / 1000
        self.accepted += 1
        return result

    def canvas_jpeg(self, jpeg, lease):
        if time.monotonic() < self.http_lease_until:
            return {"accepted": False, "reason": "http-lease-active"}
        if self.cached_layout is None:
            self.cached_layout = self.exports.layout()
        started = time.monotonic()
        body = decode_canvas(jpeg, self.cached_layout)
        if body is None:
            return {"accepted": False, "reason": "waiting-native-target"}
        self.canvas_decode_ms = (time.monotonic() - started) * 1000
        self.canvas_sample_colors = [len({body[tile*20736+p*4:tile*20736+p*4+3]
            for p in range(0, 5184, 257)}) for tile in range(15)]
        result = self.exports.setframe(lease, body)
        self.accepted += 1
        self.canvas_frames += 1
        return result

    def stop(self):
        self.http_lease_until = 0.0
        return self.exports.stop()


def handler_for(api):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalBackground/1"

        def log_message(self, *_):
            pass  # Never log authorization headers or payloads.

        def setup(self):
            super().setup()
            self.connection.settimeout(2)

        def reply(self, code, result):
            data = json.dumps(result).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            if self.headers.get("Origin"):
                self.reply(403, {"error": "Browser origins are not accepted"})
                return False
            if not api.auth(self.headers.get("Authorization", "").removeprefix("Bearer ")):
                self.reply(401, {"error": "Session token required"})
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            try:
                if self.path == "/health":
                    status = api.exports.status()
                    self.reply(200, {"ready": status["ready"] and status["errors"] == 0,
                                     "status": status, "accepted": api.accepted,
                                     "canvas": {"frames": api.canvas_frames, "rejected": api.canvas_rejected,
                                                "assembled": api.canvas.completed, "discarded": api.canvas.discarded,
                                                "decode_ms": round(api.canvas_decode_ms, 3),
                                                "distinct_sample_colors_per_key": api.canvas_sample_colors}})
                elif self.path == "/layout":
                    layout = api.exports.layout()
                    self.reply(200 if layout else 409, layout or {"error": "Waiting for native target"})
                else:
                    self.reply(404, {"error": "Unknown endpoint"})
            except Exception as error:
                self.reply(503, {"error": str(error)})

        def do_POST(self):
            if not self.authorized():
                return
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Chunked uploads are not accepted")
                length = int(self.headers.get("Content-Length", "-1"))
                if not 0 <= length <= FRAME_BYTES:
                    raise ValueError("Invalid body length")
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("Incomplete body")
                if self.path == "/stop":
                    result = api.stop()
                elif self.path == "/colors":
                    if length > 2048:
                        raise ValueError("Color payload too large")
                    result = api.colors(json.loads(body))
                elif self.path == "/frame":
                    if self.headers.get("Content-Type") != "application/octet-stream":
                        raise ValueError("Expected application/octet-stream")
                    lease = validate_lease(int(self.headers.get("X-Lease-Ms", "2000")))
                    result = api.frame(body, lease)
                else:
                    self.reply(404, {"error": "Unknown endpoint"})
                    return
                self.reply(200, result)
            except (ValueError, TypeError) as error:
                self.reply(400, {"error": str(error)})
            except Exception as error:
                self.reply(503, {"error": str(error)})
    return Handler


def run(args):
    sys.path.insert(0, str(ROOT / "tools/python"))
    import frida
    folder = Path(r"C:\Program Files\Elgato\StreamDeck")
    for name, expected in HASHES.items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest().upper() != expected:
            raise RuntimeError("Unsupported build: " + name)
    # Enumeration is incomplete for the elevated Stream Deck process on this
    # host. Query its image directly, then independently verify Process.mainModule
    # and its full path inside the script before it installs any hooks.
    image = query_process_image(args.pid)
    if image != folder / "StreamDeck.exe":
        raise RuntimeError("PID image is not the pinned StreamDeck.exe")
    stop_file = Path(args.stop_file or str(args.output) + ".stop")
    if stop_file.exists():
        raise RuntimeError("Stop file already exists; choose a fresh path")
    lock_folder, backup_directory = runtime_locations(args.runtime_directory)
    lock_folder.mkdir(parents=True, exist_ok=True)
    lock = (lock_folder / f"observer-{args.pid}.lock").open("a+b")
    if lock.tell() == 0:
        lock.write(b"0"); lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    token = secrets.token_urlsafe(32)
    session = script = http = udp = installed_plugin = None
    ready, detached, faulted = threading.Event(), threading.Event(), threading.Event()
    output = Path(args.output).open("w", encoding="utf8")
    def emit(value):
        line = json.dumps({"time": datetime.datetime.now(datetime.timezone.utc).isoformat(), **value})
        print(line, flush=True)
        if not output.closed:
            output.write(line + "\n"); output.flush()
    def message(value, data):
        emit(value)
        if value.get("type") == "send":
            event = value.get("payload", {}).get("event")
            if event == "ready": ready.set()
            if event == "native-error": faulted.set()
        elif value.get("type") == "error": faulted.set()
    def on_detached(reason, *_):
        detached.set(); emit({"event": "detached", "reason": reason})
    try:
        emit({"event": "attach-start", "pid": args.pid})
        session = frida.attach(args.pid)
        session.on("detached", on_detached)
        script = session.create_script((ROOT / "background-core.js").read_text())
        script.on("message", message)
        script.load()
        if not ready.wait(10) or faulted.is_set():
            raise RuntimeError("Native core did not report ready")
        script.exports_sync.configure({'maxFps': args.max_fps})
        api = Api(script.exports_sync, token)
        http = HTTPServer(("127.0.0.1", args.http_port), handler_for(api))
        http.timeout = 0.005
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
        udp.bind(("127.0.0.1", args.udp_port)); udp.setblocking(False)
        Path(args.session_file).write_text(json.dumps({"token": token, "http_port": args.http_port,
            "udp_port": args.udp_port, "pid": args.pid}), encoding="utf8")
        emit({"event": "api-ready", "http_port": args.http_port, "udp_port": args.udp_port})
        if args.install_signalrgb:
            from install_signalrgb_background import install_from_session
            def publisher_health(settings):
                # This publisher already owns the listening sockets and session.
                # Verify the installer read that exact session and the live native
                # core, without making an HTTP request into our own single thread.
                if (not api.auth(settings.get("token")) or
                        settings.get("http_port") != args.http_port or
                        settings.get("udp_port") != args.udp_port):
                    raise ValueError("Installer session does not match this publisher")
                state = script.exports_sync.status()
                if state["errors"]:
                    raise RuntimeError("Native background core is not healthy")
                return {"ready": state["ready"]}
            installed_plugin = install_from_session(args.session_file,
                plugin_dir=args.signalrgb_plugin_dir, backup_dir=backup_directory, health_check=publisher_health)
            emit({"event": "signalrgb-client-installed", **installed_plugin})
        until = None if args.seconds == 0 else time.monotonic() + args.seconds
        while session_active(until, stop_file, detached, faulted):
            http.handle_request()
            # Coalesce a bounded batch of UDP updates to the newest valid frame.
            latest = None
            latest_jpeg = None
            for _ in range(128):
                try: raw, address = udp.recvfrom(MAX_DATAGRAM + 1)
                except BlockingIOError: break
                except OSError as error:
                    if getattr(error, 'winerror', None) == 10040:
                        api.canvas_rejected += 1
                        continue
                    raise
                if address[0] != "127.0.0.1" or len(raw) > MAX_DATAGRAM: continue
                try:
                    candidate = json.loads(raw)
                    if isinstance(candidate, dict) and api.auth(candidate.get("token")):
                        lease = validate_lease(candidate.get("lease_ms", 2000))
                        if candidate.get("kind") == "canvas-jpeg":
                            jpeg = api.canvas.feed(candidate, address)
                            if jpeg is not None:
                                latest_jpeg = (jpeg, lease)
                                latest = None
                        else:
                            validate_colors(candidate.get("colors"))
                            latest = candidate
                            latest_jpeg = None
                except (ValueError, TypeError): api.canvas_rejected += 1
            if latest is not None: api.colors(latest, udp=True)
            if latest_jpeg is not None:
                try: api.canvas_jpeg(*latest_jpeg)
                except (ValueError, OSError): api.canvas_rejected += 1
    except KeyboardInterrupt:
        emit({"event": "interrupted"})
    except Exception as error:
        emit({"event": "api-error", "message": str(error)})
    finally:
        if http: http.server_close()
        if udp: udp.close()
        if script and not detached.is_set():
            try:
                script.exports_sync.stop()
                until = time.monotonic() + 3
                while time.monotonic() < until:
                    status = script.exports_sync.status()
                    if status["errors"] or (status["pending"] is None and not status.get("restorationPending", False)):
                        # Allow the20ms dispatcher to enqueue the final restoration.
                        time.sleep(0.2)
                        if script.exports_sync.status()["pending"] is None: break
                    time.sleep(0.05)
                emit({"event": "final-status", "status": script.exports_sync.status()})
            except Exception as error: emit({"event": "cleanup-error", "message": str(error)})
            try: script.unload(); emit({"event": "script-unloaded"})
            except Exception as error: emit({"event": "unload-error", "message": str(error)})
        if session:
            try: session.detach()
            except Exception as error: emit({"event": "detach-error", "message": str(error)})
        if installed_plugin:
            try:
                from install_signalrgb_background import deactivate_installed
                emit({"event": "signalrgb-client-cleanup", **deactivate_installed(installed_plugin)})
            except Exception as error:
                emit({"event": "signalrgb-client-cleanup-error", "type": type(error).__name__})
        session_file = Path(args.session_file)
        try:
            if session_file.exists() and json.loads(session_file.read_text()).get("token") == token:
                session_file.unlink()
        except (OSError, ValueError): pass
        emit({"event": "api-finished"})
        output.close(); lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1); lock.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--seconds", type=int, default=600,
                        help="Session lifetime, 1..3600 seconds; 0 runs until a clean stop or fault")
    parser.add_argument("--http-port", type=int, default=47686)
    parser.add_argument("--udp-port", type=int, default=47685)
    parser.add_argument("--max-fps", type=int, choices=range(1, 31), default=30)
    parser.add_argument("--runtime-directory", type=absolute_runtime_directory,
                        help="Shared private runtime for tokens, logs, locks, and backups; does not override LOCALAPPDATA")
    parser.add_argument("--session-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stop-file")
    parser.add_argument("--install-signalrgb", action="store_true",
                        help="Install the session client locally; make it inert again on clean exit")
    parser.add_argument("--signalrgb-plugin-dir", type=Path,
                        help="Override discovery when Windows has multiple Documents folders")
    args = parser.parse_args(argv)
    if not 0 <= args.seconds <= 3600 or not all(1024 <= p <= 65535 for p in [args.http_port, args.udp_port]):
        parser.error("Use seconds 0 (until stopped) or 1..3600, and ports 1024..65535")
    if args.http_port == args.udp_port or args.pid <= 0:
        parser.error("Use distinct HTTP/UDP ports and a positive Stream Deck PID")
    defaults = args.runtime_directory or ROOT
    args.session_file = args.session_file or defaults / "api-session.json"
    args.output = args.output or defaults / "background-api.jsonl"
    if args.runtime_directory is not None and args.stop_file is None:
        args.stop_file = str(args.runtime_directory / "bridge.stop")
    return args


if __name__ == "__main__":
    run(parse_args())
