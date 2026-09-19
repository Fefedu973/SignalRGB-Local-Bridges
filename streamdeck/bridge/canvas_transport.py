"""Bounded latest-frame assembly and native tile extraction for SignalRGB JPEGs."""
from io import BytesIO
import time
from PIL import Image

CHUNK_BYTES = 1024
MAX_PARTS = 256
MAX_JPEG_BYTES = CHUNK_BYTES * MAX_PARTS
MAX_DATAGRAM = 65535


class CanvasAssembler:
    def __init__(self):
        self.sender = None
        self.frame = -1
        self.parts = {}
        self.total = 0
        self.started = 0.0
        self.completed = 0
        self.discarded = 0
        self.closed_frame = False

    def feed(self, message, sender, now=None):
        now = time.monotonic() if now is None else now
        frame, part, total, data = (message.get(k) for k in ('frame', 'part', 'total', 'data'))
        if message.get('kind') != 'canvas-jpeg' or any(type(v) is not int for v in (frame, part, total)):
            raise ValueError('Invalid canvas frame header')
        if not 0 <= frame <= 2**53 - 1 or not 1 <= total <= MAX_PARTS or not 0 <= part < total:
            raise ValueError('Canvas frame bounds exceeded')
        if not isinstance(data, list) or not 1 <= len(data) <= CHUNK_BYTES or any(type(v) is not int or not 0 <= v <= 255 for v in data):
            raise ValueError('Invalid image chunk')
        if part < total - 1 and len(data) != CHUNK_BYTES:
            raise ValueError('Incomplete middle chunk')
        if sender != self.sender:
            self.sender = sender
            self.frame = -1
            self.parts = {}
        if frame < self.frame or (frame == self.frame and self.closed_frame):
            return None
        if frame > self.frame:
            if self.parts: self.discarded += 1
            self.frame, self.total, self.started = frame, total, now
            self.parts, self.closed_frame = {}, False
        if now - self.started > 0.25:
            self.parts, self.closed_frame = {}, True
            self.discarded += 1
            return None
        if total != self.total:
            raise ValueError('Chunk count changed within one frame')
        chunk = bytes(data)
        if part in self.parts and self.parts[part] != chunk:
            raise ValueError('Conflicting image chunk')
        self.parts[part] = chunk
        if len(self.parts) != total:
            return None
        jpeg = b''.join(self.parts[i] for i in range(total))
        self.parts, self.closed_frame = {}, True
        self.completed += 1
        return jpeg


def decode_canvas(jpeg, layout):
    if not 4 <= len(jpeg) <= MAX_JPEG_BYTES or not jpeg.startswith(b'\xff\xd8'):
        raise ValueError('Expected a bounded JPEG image')
    if layout is None:
        return None
    if (layout['width'], layout['height'], layout['tileWidth'], layout['tileHeight']) != (480, 272, 72, 72) or len(layout['positions']) != 15:
        raise ValueError('Unsupported MK.2 layout')
    with Image.open(BytesIO(jpeg)) as encoded:
        if encoded.format != 'JPEG' or encoded.size != (480, 272):
            raise ValueError('Canvas JPEG must be exactly 480 by 272')
        canvas = encoded.convert('RGB')
        result = []
        for x, y in layout['positions']:
            if type(x) is not int or type(y) is not int or not 0 <= x <= 408 or not 0 <= y <= 200:
                raise ValueError('Invalid native crop position')
            tile = canvas.crop((x, y, x + 72, y + 72)).convert('RGBA')
            result.append(tile.tobytes('raw', 'BGRA'))
    return b''.join(result)
