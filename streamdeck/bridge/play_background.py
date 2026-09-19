"""Play a local image/GIF/video through the separate Stream Deck background API."""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from media_frames import MediaDecoder


class BackgroundClient:
    def __init__(self, session):
        settings = json.loads(Path(session).read_text(encoding="utf-8"))
        self.token = settings["token"]
        port = settings.get("http_port", 47686)
        if not isinstance(self.token, str) or len(self.token) < 16:
            raise ValueError("Invalid local session token")
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("Invalid local API port")
        self.base = f"http://127.0.0.1:{port}"
        # Never send the local token through an environment-configured proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path, data=None, content_type="application/json"):
        request = urllib.request.Request(self.base + path, data=data, headers={
            "Authorization": "Bearer " + self.token,
            "Content-Type": content_type,
        })
        with self.opener.open(request, timeout=3) as reply:
            return json.loads(reply.read(65536))

    def layout(self):
        result = self.request("/layout")
        return result.get("layout", result)

    def frame(self, tiles):
        data = b"".join(tiles)
        if len(tiles) != 15 or len(data) != 311040:
            raise ValueError("Expected exactly fifteen 72x72 BGRA tiles")
        return self.request("/frame", data, "application/octet-stream")

    def stop(self):
        return self.request("/stop", b"{}")


def play(client, path, *, seconds=30, fps=10, fit="contain", loop=False):
    if not 0 < seconds <= 3600 or not 1 <= fps <= 30:
        raise ValueError("Playback must be bounded to 1 hour and 1..30 fps")
    layout = client.layout()
    if (layout["tileWidth"], layout["tileHeight"]) != (72, 72) or len(layout["positions"]) != 15:
        raise ValueError("Unsupported native tile layout")
    decoder = MediaDecoder(path, width=layout["width"], height=layout["height"], fps=fps, fit=fit)
    deadline = time.monotonic() + seconds
    sent = 0
    started = False
    try:
        while time.monotonic() < deadline:
            count = 0
            frames = decoder.frames(max_frames=max(1, int(seconds * fps) + 1))
            try:
                for frame in frames:
                    if time.monotonic() >= deadline:
                        break
                    frame_start = time.monotonic()
                    # Treat an uncertain HTTP response as a possible accepted frame.
                    started = True
                    client.frame(frame.tiles(layout["positions"], (72, 72)))
                    sent += 1
                    count += 1
                    time.sleep(max(0, min(frame_start + 1 / fps, deadline) - time.monotonic()))
            finally:
                frames.close()
            if not loop or count == 0:
                break
    finally:
        if started:
            client.stop()
    return sent


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", type=Path)
    parser.add_argument("--session", type=Path, default=Path(__file__).with_name("api-session.json"))
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--fit", choices=("contain", "cover"), default="contain")
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    client = BackgroundClient(args.session)
    print("Playing local media through the background API.", flush=True)
    count = play(client, args.media, seconds=args.seconds, fps=args.fps, fit=args.fit, loop=args.loop)
    print(f"Sent {count} frames; requested restoration of the normal background.", flush=True)
