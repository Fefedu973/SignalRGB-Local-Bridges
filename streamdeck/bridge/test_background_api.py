import http.client
import json
import contextlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import HTTPServer
from background_api import Api, handler_for, validate_colors, validate_frame, validate_lease, parse_args, session_active, runtime_locations, ROOT


class Sink:
    def __init__(self): self.calls = []
    def setcolors(self, value, lease): self.calls.append(("colors", value, lease)); return {"accepted": True}
    def setframe(self, lease, data): self.calls.append(("frame", lease, data)); return {"accepted": True}
    def stop(self): self.calls.append(("stop",)); return {"stopped": True}
    def status(self): return {"ready": True, "errors": 0}
    def layout(self): return {"positions": []}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.sink = Sink()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(Api(self.sink, "secret-test-token")))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close()

    def request(self, path, body, extra=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer secret-test-token", "Content-Type": "application/json"}
        headers.update(extra or {})
        connection.request("POST", path, body, headers)
        reply = connection.getresponse(); result = reply.status, json.loads(reply.read())
        connection.close(); return result

    def test_auth_and_origin_reject_before_bridge(self):
        self.assertEqual(self.request("/stop", b"{}", {"Authorization": "Bearer wrong"})[0], 401)
        self.assertEqual(self.request("/stop", b"{}", {"Origin": "https://example.com"})[0], 403)
        self.assertEqual(self.sink.calls, [])

    def test_color_extremes_preserved_and_lease_default(self):
        colors = [[0, 255, 17]] * 15
        self.assertEqual(self.request("/colors", json.dumps({"colors": colors}))[0], 200)
        self.assertEqual(self.sink.calls, [("colors", colors, 2000)])

    def test_boolean_overflow_missing_and_oversize_rejected(self):
        for bad in [None, [], [[True, 0, 0]] * 15, [[256, 0, 0]] * 15, [[0.1, 0, 0]] * 15]:
            self.assertEqual(self.request("/colors", json.dumps({"colors": bad}))[0], 400)
        self.assertEqual(self.request("/colors", b" " * 2049)[0], 400)
        self.assertEqual(self.sink.calls, [])

    def test_binary_frame_preserved_without_json_encoding(self):
        frame = bytes([7, 19, 201, 255]) * (15 * 72 * 72)
        self.assertEqual(self.request("/frame", frame, {"Content-Type": "application/octet-stream"})[0], 200)
        self.assertEqual(self.sink.calls, [("frame", 2000, frame)])

    def test_frame_size_alpha_and_lease_limits(self):
        for data in [b"", b"\0" * 311040, bytes([0, 0, 0, 255]) * (15 * 72 * 72 - 1)]:
            with self.assertRaises(ValueError): validate_frame(data)
        for value in [True, 499, 10001, 2000.0, None]:
            with self.assertRaises(ValueError): validate_lease(value)

    def test_media_lease_prevents_signal_canvas_overwriting_video(self):
        api = Api(self.sink, "test")
        frame = bytes([7, 19, 201, 255]) * (15 * 72 * 72)
        api.frame(frame, 2000)
        colors = {"colors": [[0, 255, 0]] * 15}
        self.assertFalse(api.colors(colors, udp=True)["accepted"])
        self.assertEqual(len(self.sink.calls), 1)
        api.stop()
        self.assertTrue(api.colors(colors, udp=True)["accepted"])
        self.assertEqual([call[0] for call in self.sink.calls], ["frame", "stop", "colors"])

    def test_expired_http_lease_allows_udp_without_explicit_stop(self):
        api = Api(self.sink, "test")
        colors = {"colors": [[0, 255, 0]] * 15}
        with patch("background_api.time.monotonic", return_value=100):
            api.colors(colors)
        with patch("background_api.time.monotonic", return_value=103):
            self.assertTrue(api.colors(colors, udp=True)["accepted"])


class SessionTests(unittest.TestCase):
    def test_explicit_runtime_moves_all_private_defaults_without_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory).resolve() / "private shared runtime"
            with patch.dict("os.environ", {"LOCALAPPDATA": str(Path(directory) / "unrelated")}):
                args = parse_args(["--pid", "123", "--runtime-directory", str(runtime)])
                self.assertEqual(args.session_file, runtime / "api-session.json")
                self.assertEqual(args.output, runtime / "background-api.jsonl")
                self.assertEqual(Path(args.stop_file), runtime / "bridge.stop")
                self.assertEqual(runtime_locations(args.runtime_directory), (runtime / "locks", runtime / "signalrgb-backups"))
            self.assertFalse(runtime.exists())  # Parsing does not create state.

    def test_legacy_runtime_defaults_remain_compatible(self):
        args = parse_args(["--pid", "123"])
        self.assertIsNone(args.runtime_directory)
        self.assertEqual(args.session_file, ROOT / "api-session.json")
        self.assertEqual(args.output, ROOT / "background-api.jsonl")
        self.assertIsNone(args.stop_file)
        with patch.dict("os.environ", {"LOCALAPPDATA": "C:\\private-fixture"}):
            self.assertEqual(runtime_locations(None), (Path("C:/private-fixture/CodexLocalBridges/StreamDeck/locks"), None))

    def test_runtime_rejects_ambiguous_paths_and_preserves_explicit_outputs(self):
        for path in ["relative", "C:relative", "\\drive-relative", 'C:\\bad"quote', "C:\\bad\nline"]:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(["--pid", "123", "--runtime-directory", path])
        args = parse_args(["--pid", "123", "--runtime-directory", "C:\\private-fixture",
                           "--session-file", "C:\\custom\\session.json", "--output", "C:\\custom\\events.jsonl", "--stop-file", "C:\\custom\\stop"])
        self.assertEqual(args.session_file, Path("C:/custom/session.json"))
        self.assertEqual(args.output, Path("C:/custom/events.jsonl"))
        self.assertEqual(args.stop_file, "C:\\custom\\stop")

    def test_default_bounded_and_explicit_unlimited_parser(self):
        self.assertEqual(parse_args(["--pid", "123"]).seconds, 600)
        self.assertEqual(parse_args(["--pid", "123", "--seconds", "0"]).seconds, 0)
        for argv in [["--pid", "0"], ["--pid", "123", "--seconds", "-1"],
                     ["--pid", "123", "--seconds", "3601"],
                     ["--pid", "123", "--http-port", "47685"]]:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(argv)

    def test_unlimited_session_still_stops_on_file_detach_or_fault(self):
        with tempfile.TemporaryDirectory() as directory:
            stop = Path(directory) / "stop"
            detached, faulted = threading.Event(), threading.Event()
            self.assertTrue(session_active(None, stop, detached, faulted))
            stop.touch()
            self.assertFalse(session_active(None, stop, detached, faulted))
            stop.unlink()
            detached.set()
            self.assertFalse(session_active(None, stop, detached, faulted))
            detached.clear(); faulted.set()
            self.assertFalse(session_active(None, stop, detached, faulted))

    def test_bounded_session_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            stop = Path(directory) / "stop"
            with patch("background_api.time.monotonic", return_value=100):
                self.assertFalse(session_active(99, stop, threading.Event(), threading.Event()))
                self.assertTrue(session_active(101, stop, threading.Event(), threading.Event()))


if __name__ == "__main__": unittest.main()
