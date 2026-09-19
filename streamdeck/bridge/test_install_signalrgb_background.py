import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import install_signalrgb_background as installer


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.session = self.root / "api-session.json"
        self.plugins = self.root / "Plugins"
        self.backups = self.root / "private-backups"
        self.token = "synthetic-session-A-0123456789012345678901"
        self.write_session()

    def tearDown(self):
        self.temp.cleanup()

    def write_session(self, **overrides):
        data = {"token": self.token, "http_port": 47686, "udp_port": 47685, "pid": 123}
        data.update(overrides)
        self.session.write_text(json.dumps(data), encoding="utf-8")

    def install(self):
        return installer.install_from_session(self.session, self.plugins, self.backups,
                                              health_check=lambda _: {"ready": False})

    def test_injection_is_local_and_template_stays_inert(self):
        result = self.install()
        content = Path(result["path"]).read_text()
        self.assertIn('const BRIDGE_TOKEN = "' + self.token + '";', content)
        self.assertEqual(content.count('__LOCAL_SESSION_TOKEN__'), 1)  # guard remains
        self.assertIn(installer.TOKEN_DECLARATION, installer.read_template())
        self.assertNotIn(self.token, json.dumps(result))
        self.assertFalse(result["api_ready"])
        self.assertEqual(Path(result["interface_path"]).read_bytes(), (installer.ROOT / installer.INTERFACE_NAME).read_bytes())

    def test_interface_is_published_before_javascript_and_backed_up(self):
        self.plugins.mkdir()
        interface = self.plugins / installer.INTERFACE_NAME
        interface.write_bytes(b"// previous user interface")
        real_replace = installer.atomic_replace
        observed = []
        def traced(target, content, expected):
            observed.append(target.name)
            return real_replace(target, content, expected)
        with patch.object(installer, "atomic_replace", side_effect=traced):
            self.install()
        self.assertEqual(observed, [installer.INTERFACE_NAME, installer.PLUGIN_NAME])
        backups = list(self.backups.glob(installer.INTERFACE_NAME + ".*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"// previous user interface")

    def test_new_session_rotates_token_and_preserves_previous_copy(self):
        first = self.install()
        previous = Path(first["path"]).read_bytes()
        self.write_session(token="synthetic-session-B-0123456789012345678901", udp_port=47800)
        second = self.install()
        self.assertNotEqual(first["sha256"], second["sha256"])
        self.assertEqual(Path(second["backup"]).read_bytes(), previous)
        self.assertIn("const BRIDGE_PORT = 47800;", Path(second["path"]).read_text())
        self.assertNotIn(self.token, Path(second["path"]).read_text())

    def test_idempotence_avoids_reload_and_duplicate_backup(self):
        first = self.install()
        second = self.install()
        self.assertFalse(second["changed"])
        self.assertIsNone(second["backup"])
        self.assertEqual(first["sha256"], second["sha256"])

    def test_existing_unrelated_same_name_copy_is_backed_up_exactly(self):
        self.plugins.mkdir()
        target = self.plugins / installer.PLUGIN_NAME
        target.write_bytes(b"// preexisting user file\r\n")
        result = self.install()
        self.assertEqual(Path(result["backup"]).read_bytes(), b"// preexisting user file\r\n")

    def test_invalid_session_never_creates_target(self):
        for value in ["short", "x"*129, 'x";bad()', None]:
            self.write_session(token=value)
            with self.assertRaises(ValueError): self.install()
        for value in [True, 0, 65536, "47685"]:
            self.write_session(udp_port=value)
            with self.assertRaises(ValueError): self.install()
        self.assertFalse(self.plugins.exists())

    def test_failed_authentication_never_creates_target(self):
        with self.assertRaises(ValueError):
            installer.install_from_session(self.session, self.plugins, self.backups,
                health_check=lambda _: (_ for _ in ()).throw(ValueError("no matching local API")))
        self.assertFalse(self.plugins.exists())

    def test_cleanup_deactivates_only_exact_installed_copy(self):
        result = self.install()
        self.assertTrue(installer.deactivate_installed(result)["deactivated"])
        self.assertIn(installer.TOKEN_DECLARATION, Path(result["path"]).read_text())
        result = self.install()
        Path(result["path"]).write_text("// user changed this")
        self.assertFalse(installer.deactivate_installed(result)["deactivated"])
        self.assertEqual(Path(result["path"]).read_text(), "// user changed this")

    def test_concurrent_user_change_is_preserved(self):
        result = self.install()
        target = Path(result["path"])
        self.write_session(token="synthetic-session-B-0123456789012345678901")
        with patch.object(installer.os, "fsync", side_effect=lambda _: target.write_text("// concurrent user change")):
            with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(target.read_text(), "// concurrent user change")
        self.assertEqual(list(self.plugins.glob("*.tmp")), [])

    def test_health_request_cannot_redirect_or_use_remote_host(self):
        class Response:
            status = 200
            def read(self, _): return b'{"ready":false,"status":{"errors":0}}'
        class Connection:
            def request(self, method, path, headers):
                self.args = method, path, headers
            def getresponse(self): return Response()
            def close(self): pass
        connection = Connection()
        with patch.object(installer.http.client, "HTTPConnection", return_value=connection) as constructor:
            self.assertEqual(installer.verify_local_api(installer.load_session(self.session)), {"ready": False})
            constructor.assert_called_once_with("127.0.0.1", 47686, timeout=2)
            self.assertEqual(connection.args[:2], ("GET", "/health"))
            self.assertEqual(connection.args[2]["Authorization"], "Bearer " + self.token)
            Response.status = 302
            with self.assertRaises(ValueError): installer.verify_local_api(installer.load_session(self.session))

    def test_onedrive_existing_plugins_win_over_empty_windows_documents(self):
        cloud = self.root / "OneDrive"
        expected = cloud / "Documents" / "WhirlwindFX" / "Plugins"
        expected.mkdir(parents=True)
        self.assertEqual(installer.select_plugin_directory(self.root / "Documents", [str(cloud),str(cloud)]), expected)

    def test_ambiguous_existing_documents_require_explicit_path(self):
        documents = self.root / "Documents"
        (documents / "WhirlwindFX" / "Plugins").mkdir(parents=True)
        cloud = self.root / "OneDrive"
        (cloud / "Documents" / "WhirlwindFX" / "Plugins").mkdir(parents=True)
        with self.assertRaises(ValueError): installer.select_plugin_directory(documents, [str(cloud)])


if __name__ == "__main__": unittest.main()
