"""Install the local-only SignalRGB background client from a current API session.

No installation occurs on import. The launcher calls install_from_session after
api-ready. No token is accepted on the command line or included in the result.
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parent
PLUGIN_NAME = "SignalRGB_StreamDeck_Background.js"
INTERFACE_NAME = "SignalRGB_StreamDeck_Background.qml"
TOKEN_DECLARATION = 'const BRIDGE_TOKEN = "__LOCAL_SESSION_TOKEN__";'
PORT_DECLARATION = "const BRIDGE_PORT = 47685;"


def select_plugin_directory(documents, onedrive_roots):
    """Choose the single existing user Plugins tree; never guess between two."""
    default = Path(documents) / "WhirlwindFX" / "Plugins"
    candidates = [default]
    for root in onedrive_roots:
        if root:
            candidate = Path(root) / "Documents" / "WhirlwindFX" / "Plugins"
            if candidate not in candidates:
                candidates.append(candidate)
    existing = [candidate for candidate in candidates if candidate.is_dir()]
    if len(existing) > 1:
        raise ValueError("Multiple user Plugins directories exist; pass plugin_dir explicitly")
    return existing[0] if existing else default


def user_plugin_directory():
    """Resolve Documents and a retained OneDrive tree after folder redirection."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                       r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
        documents, _ = winreg.QueryValueEx(key, "Personal")
    folder = Path(os.path.expandvars(documents))
    if not folder.is_absolute():
        raise ValueError("Windows Documents is not an absolute directory")
    return select_plugin_directory(folder, [os.environ.get(name) for name in
        ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")])


def load_session(path):
    raw = Path(path).read_bytes()
    if len(raw) > 4096:
        raise ValueError("Unexpected local session file size")
    value = json.loads(raw)
    token = value.get("token") if isinstance(value, dict) else None
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
        raise ValueError("Invalid local session token")
    for name in ("http_port", "udp_port"):
        port = value.get(name)
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("Invalid local session port")
    return value


def verify_local_api(session):
    """HTTPConnection uses the fixed loopback host, no proxy or redirects."""
    connection = http.client.HTTPConnection("127.0.0.1", session["http_port"], timeout=2)
    try:
        connection.request("GET", "/health", headers={"Authorization": "Bearer " + session["token"]})
        reply = connection.getresponse()
        body = reply.read(65537)
        if reply.status != 200 or len(body) > 65536:
            raise ValueError("Local background API did not authenticate this session")
        result = json.loads(body)
        if not isinstance(result, dict) or not isinstance(result.get("status"), dict) or result["status"].get("errors") != 0:
            raise ValueError("Local background API is not healthy")
        # ready:false can mean that the first natural composition has not occurred.
        return {"ready": result.get("ready") is True}
    finally:
        connection.close()


def read_template():
    text = (ROOT / PLUGIN_NAME).read_text(encoding="utf-8")
    if text.count(TOKEN_DECLARATION) != 1 or text.count(PORT_DECLARATION) != 1:
        raise ValueError("Template must contain exactly one session token and port declaration")
    if 'export function Type() { return "network"; }' not in text:
        raise ValueError("Template is not a network plugin")
    if re.search(r"https?://|export function (VendorId|ProductId)|device\.(write|read|send_report|get_report|control_transfer|bulk_transfer)\s*\(", text):
        raise ValueError("Template unexpectedly contains remote or USB access")
    imports = re.findall(r'^import .*? from [\'"]([^\'"]+)[\'"];', text, flags=re.M)
    if imports != ["@SignalRGB/udp"]:
        raise ValueError("Unexpected plugin imports")
    return text


def atomic_replace(target, content, expected):
    """Avoid partial watched JavaScript and refuse a concurrently modified target."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        current = target.read_bytes() if target.exists() else None
        if current != expected:
            raise RuntimeError("Target plugin changed during installation; no replacement made")
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install_from_session(session_file, plugin_dir=None, backup_dir=None, *, health_check=verify_local_api):
    session = load_session(session_file)
    template = read_template()
    health = health_check(session)
    generated = template.replace(TOKEN_DECLARATION, "const BRIDGE_TOKEN = " + json.dumps(session["token"]) + ";", 1)
    generated = generated.replace(PORT_DECLARATION, f"const BRIDGE_PORT = {session['udp_port']};", 1).encode("utf-8")
    folder = Path(plugin_dir) if plugin_dir is not None else user_plugin_directory()
    if not folder.is_absolute():
        raise ValueError("Plugin directory must be absolute")
    # A network service loads its same-basename QML interface. Publish it before
    # the watched JS so the discovery page never references a missing file.
    interface = (ROOT / INTERFACE_NAME).read_bytes()
    interface_target = folder / INTERFACE_NAME
    old_interface = interface_target.read_bytes() if interface_target.exists() else None
    if old_interface != interface:
        if old_interface is not None:
            private_root = Path(backup_dir) if backup_dir else Path(os.environ["LOCALAPPDATA"]) / "CodexLocalBridges" / "StreamDeck" / "signalrgb-backups"
            if not private_root.is_absolute():
                raise ValueError("Backup directory must be absolute")
            private_root.mkdir(parents=True, exist_ok=True)
            interface_backup = private_root / (INTERFACE_NAME + "." + hashlib.sha256(old_interface).hexdigest()[:16] + ".bak")
            if interface_backup.exists():
                if interface_backup.read_bytes() != old_interface:
                    raise RuntimeError("Interface backup collision")
            else:
                with interface_backup.open("xb") as stream:
                    stream.write(old_interface)
        folder.mkdir(parents=True, exist_ok=True)
        atomic_replace(interface_target, interface, old_interface)
    target = folder / PLUGIN_NAME
    previous = target.read_bytes() if target.exists() else None
    digest = hashlib.sha256(generated).hexdigest()
    if previous == generated:
        return {"path": str(target), "sha256": digest, "changed": False, "backup": None, "api_ready": health["ready"], "interface_path": str(interface_target)}
    backup = None
    if previous is not None:
        if backup_dir is None:
            local = os.environ.get("LOCALAPPDATA")
            if not local:
                raise ValueError("LOCALAPPDATA is required for the private backup directory")
            backup_dir = Path(local) / "CodexLocalBridges" / "StreamDeck" / "signalrgb-backups"
        backup_folder = Path(backup_dir)
        if not backup_folder.is_absolute():
            raise ValueError("Backup directory must be absolute")
        backup_folder.mkdir(parents=True, exist_ok=True)
        backup = backup_folder / (PLUGIN_NAME + "." + hashlib.sha256(previous).hexdigest()[:16] + ".bak")
        if backup.exists():
            if backup.read_bytes() != previous:
                raise RuntimeError("Backup collision")
        else:
            with backup.open("xb") as stream:
                stream.write(previous)
    folder.mkdir(parents=True, exist_ok=True)
    atomic_replace(target, generated, previous)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    return {"path": str(target), "sha256": digest, "changed": True,
            "backup": str(backup) if backup else None, "api_ready": health["ready"], "interface_path": str(interface_target)}


def deactivate_installed(result):
    """Optional launcher cleanup: replace only its exact installed copy with the inert template."""
    target = Path(result["path"])
    if not target.exists():
        return {"deactivated": False, "reason": "absent"}
    previous = target.read_bytes()
    if hashlib.sha256(previous).hexdigest() != result["sha256"]:
        return {"deactivated": False, "reason": "changed_after_install"}
    atomic_replace(target, read_template().encode("utf-8"), previous)
    return {"deactivated": True, "path": str(target)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, default=ROOT / "api-session.json")
    parser.add_argument("--plugin-dir", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(install_from_session(args.session, args.plugin_dir, args.backup_dir)))
    except Exception as error:
        # Never print an untrusted session value or HTTP body in an error message.
        raise SystemExit("Local installation failed (" + type(error).__name__ + "). No token was logged.")
