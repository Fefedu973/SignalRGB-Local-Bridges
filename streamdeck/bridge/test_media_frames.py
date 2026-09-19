import tempfile
import unittest
from pathlib import Path
from PIL import Image
from media_frames import Frame, MediaDecoder


class MediaTests(unittest.TestCase):
    def test_native_tile_coordinates(self):
        pixels = b"".join(bytes((x, y, 7, 255)) for y in range(4) for x in range(6))
        frame = Frame(6, 4, pixels)
        tile = frame.tiles([(2, 1)], (2, 2))[0]
        self.assertEqual(tile, bytes((2, 1, 7, 255, 3, 1, 7, 255,
                                     2, 2, 7, 255, 3, 2, 7, 255)))
        with self.assertRaises(ValueError):
            frame.tiles([(5, 3)], (2, 2))

    def test_gif_animation_survives_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two.gif"
            Image.new("RGB", (8, 8), "red").save(path, save_all=True,
                append_images=[Image.new("RGB", (8, 8), "blue")], duration=200, loop=0)
            frames = list(MediaDecoder(path, width=16, height=16, fps=10).frames(max_frames=4))
            self.assertEqual(len(frames), 4)
            self.assertEqual(frames[0].bgra[:4], bytes((0, 0, 255, 255)))
            self.assertEqual(frames[-1].bgra[:4], bytes((255, 0, 0, 255)))

    def test_alpha_and_padding_are_opaque_black(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transparent.png"
            Image.new("RGBA", (8, 4), (255, 0, 0, 0)).save(path)
            frame = next(MediaDecoder(path, width=16, height=16).frames(max_frames=1))
            self.assertEqual(set(frame.bgra[3::4]), {255})
            self.assertEqual(set(frame.bgra[0::4]), {0})
            self.assertEqual(set(frame.bgra[2::4]), {0})


if __name__ == "__main__":
    unittest.main()
