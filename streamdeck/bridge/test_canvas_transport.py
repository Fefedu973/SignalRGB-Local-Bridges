import io
import unittest
from unittest.mock import Mock
from PIL import Image, ImageDraw
from canvas_transport import CanvasAssembler, decode_canvas, CHUNK_BYTES

LAYOUT = dict(width=480, height=272, tileWidth=72, tileHeight=72,
              positions=[[11+(i%5)*97, 5+(i//5)*97] for i in range(15)])

def packets(data, frame=1):
    chunks = [list(data[i:i+CHUNK_BYTES]) for i in range(0, len(data), CHUNK_BYTES)]
    return [dict(kind='canvas-jpeg', frame=frame, part=i, total=len(chunks), data=chunk)
            for i, chunk in enumerate(chunks)]

def jpeg(size=(480, 272)):
    image = Image.new('RGB', size, (20, 40, 60))
    draw = ImageDraw.Draw(image)
    draw.rectangle((11, 5, 45, 76), fill=(240, 10, 10))
    draw.rectangle((46, 5, 82, 76), fill=(10, 10, 240))
    output = io.BytesIO(); image.save(output, format='JPEG', quality=95)
    return output.getvalue()

class CanvasTests(unittest.TestCase):
    def test_reordering_and_duplicate_chunks(self):
        data = bytes(range(256)) * 10
        parts = packets(data)
        assembler = CanvasAssembler()
        self.assertIsNone(assembler.feed(parts[1], 1, 0))
        self.assertIsNone(assembler.feed(parts[1], 1, .01))
        self.assertIsNone(assembler.feed(parts[0], 1, .02))
        self.assertEqual(assembler.feed(parts[2], 1, .03), data)
        self.assertIsNone(assembler.feed(parts[0], 1, .04))

    def test_newer_frame_discards_partial_and_late_data(self):
        assembler = CanvasAssembler()
        old = packets(b'a' * 5000)
        new = packets(b'b' * 80, 2)
        self.assertIsNone(assembler.feed(old[0], 1, 0))
        self.assertEqual(assembler.feed(new[0], 1, .1), b'b' * 80)
        self.assertIsNone(assembler.feed(old[1], 1, .11))
        self.assertEqual(assembler.discarded, 1)

    def test_timeout_and_renderer_restart(self):
        assembler = CanvasAssembler(); parts = packets(b'a' * 5000, 20)
        assembler.feed(parts[0], 1, 0)
        self.assertIsNone(assembler.feed(parts[1], 1, .3))
        self.assertEqual(assembler.feed(packets(b'b', 1)[0], 2, .4), b'b')

    def test_rejects_malformed_chunks(self):
        for changes in ({'total':257}, {'part':-1}, {'frame':True}, {'data':[True]}, {'data':[]}, {'data':[256]}):
            message = packets(b'a')[0]; message.update(changes)
            with self.assertRaises(ValueError): CanvasAssembler().feed(message, 1)

    def test_spatial_pixels_and_opaque_bgra(self):
        result = decode_canvas(jpeg(), LAYOUT)
        self.assertEqual(len(result), 311040)
        self.assertEqual(set(result[3::4]), {255})
        # Two contrasting pixels within the SAME key prove full-image content.
        left = result[(36*72+15)*4:(36*72+15)*4+4]
        right = result[(36*72+56)*4:(36*72+56)*4+4]
        self.assertGreater(left[2], left[0]+150)
        self.assertGreater(right[0], right[2]+150)
        # A different native crop retains the original low-color background.
        second = result[72*72*4+36*72*4:72*72*4+36*72*4+4]
        self.assertLess(abs(second[0]-60), 5)

    def test_only_expected_jpeg_geometry(self):
        for data in (b'bad', jpeg((48, 27))):
            with self.assertRaises(ValueError): decode_canvas(data, LAYOUT)

    def test_public_api_passes_lease_before_binary_and_respects_media(self):
        from background_api import Api
        exports = Mock()
        exports.layout.return_value = LAYOUT
        exports.setframe.return_value = {'accepted': True}
        api = Api(exports, 'test-token')
        self.assertTrue(api.canvas_jpeg(jpeg(), 2000)['accepted'])
        lease, raw = exports.setframe.call_args.args
        self.assertEqual(lease, 2000)
        self.assertEqual(len(raw), 311040)
        self.assertEqual(api.canvas_frames, 1)
        api.http_lease_until = float('inf')
        self.assertFalse(api.canvas_jpeg(jpeg(), 2000)['accepted'])
        self.assertEqual(exports.setframe.call_count, 1)

if __name__ == '__main__': unittest.main()
