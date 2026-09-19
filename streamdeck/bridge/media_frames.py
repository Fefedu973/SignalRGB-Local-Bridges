"""Bounded local media decoder for a Stream Deck background canvas.

This module has no Stream Deck, profile, USB, or network access. Tile positions
must come from the native composer; no model-specific spacing is assumed.
"""
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    bgra: bytes

    def __post_init__(self):
        if not (0 < self.width <= 4096 and 0 < self.height <= 4096):
            raise ValueError("Invalid canvas dimensions")
        if len(self.bgra) != self.width * self.height * 4:
            raise ValueError("Invalid BGRA frame length")

    def tiles(self, positions, size=(72, 72)):
        tw, th = size
        if tw <= 0 or th <= 0:
            raise ValueError("Invalid tile size")
        result = []
        for x, y in positions:
            if type(x) is not int or type(y) is not int:
                raise ValueError("Native tile coordinates must be integers")
            if x < 0 or y < 0 or x + tw > self.width or y + th > self.height:
                raise ValueError("Native tile rectangle exceeds canvas")
            result.append(b"".join(
                self.bgra[((y + row) * self.width + x) * 4:
                          ((y + row) * self.width + x + tw) * 4]
                for row in range(th)))
        return result


class MediaDecoder:
    def __init__(self, path, *, width=480, height=272, fps=15,
                 fit="contain", ffmpeg=None):
        self.path = Path(path).resolve(strict=True)
        if not self.path.is_file():
            raise ValueError("Expected a local media file")
        if not (0 < width <= 4096 and 0 < height <= 4096 and 1 <= fps <= 30):
            raise ValueError("Invalid canvas dimensions or frame rate")
        if fit not in ("contain", "cover"):
            raise ValueError("fit must be contain or cover")
        self.width, self.height, self.fps, self.fit = width, height, fps, fit
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg")
        if not self.ffmpeg:
            raise RuntimeError("FFmpeg is required for local media decoding")

    def frames(self, *, max_frames=1800):
        """Yield at most max_frames; generator.close() also stops FFmpeg."""
        if type(max_frames) is not int or not 1 <= max_frames <= 108000:
            raise ValueError("A bounded frame count is required")
        w, h = self.width, self.height
        if self.fit == "contain":
            geometry = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")
        else:
            geometry = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                        f"crop={w}:{h}")
        # Composite transparency onto black and emit explicit opaque BGRA.
        graph = (f"[0:v]fps={self.fps},{geometry},format=rgba[fg];"
                 f"color=black:s={w}x{h}:r={self.fps}[bg];"
                 "[bg][fg]overlay=shortest=1:format=auto,format=bgra[out]")
        command = [str(self.ffmpeg), "-hide_banner", "-loglevel", "error",
                   "-nostdin", "-protocol_whitelist", "file,pipe", "-i", str(self.path),
                   "-filter_complex", graph, "-map", "[out]", "-an", "-sn", "-dn",
                   "-frames:v", str(max_frames), "-f", "rawvideo", "-pix_fmt", "bgra", "pipe:1"]
        frame_size = w * h * 4
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=errors,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                for _ in range(max_frames):
                    chunks, remaining = [], frame_size
                    while remaining:
                        part = process.stdout.read(remaining)
                        if not part:
                            break
                        chunks.append(part)
                        remaining -= len(part)
                    if remaining:
                        if chunks:
                            raise RuntimeError("Truncated decoded video frame")
                        break
                    yield Frame(w, h, b"".join(chunks))
                code = process.wait(timeout=10)
                if code:
                    errors.seek(0)
                    detail = errors.read(4096).decode("utf-8", errors="replace")
                    raise RuntimeError(f"FFmpeg failed ({code}): {detail}")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                process.stdout.close()
