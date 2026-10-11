"""小さな実動画を生成し、Bフレーム・可変間隔・逆方向シークを検証。"""

from fractions import Fraction
from pathlib import Path
import tempfile
import unittest

import av
from PIL import Image

from video import VideoReader, scan


class VideoTests(unittest.TestCase):
    def make_video(self, path, timestamps, rate):
        with av.open(str(path), "w") as container:
            stream = container.add_stream("libx264", rate=rate)
            stream.width = 64
            stream.height = 48
            stream.pix_fmt = "yuv420p"
            stream.time_base = Fraction(1, 90000)
            stream.codec_context.time_base = Fraction(1, 90000)
            for i, timestamp in enumerate(timestamps):
                frame = av.VideoFrame.from_image(Image.new("RGB", (64, 48), (i * 17, 60, 200 - i * 11)))
                frame.pts = timestamp
                frame.time_base = Fraction(1, 90000)
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)

    def test_frame_index_times_and_random_seeks(self):
        with tempfile.TemporaryDirectory() as directory:
            for variable in (False, True):
                path = Path(directory) / f"sample-{variable}.mp4"
                ticks = [i * 3003 for i in range(12)]
                if variable:
                    ticks = [value + (6006 if i >= 5 else 0) for i, value in enumerate(ticks)]
                self.make_video(path, ticks, Fraction(30000, 1001))
                index = scan(str(path))
                self.assertEqual(len(index.frames), len(ticks))
                self.assertEqual(index.variable_rate, variable)
                for frame, tick in zip(index.frames, ticks):
                    self.assertEqual(frame.time, Fraction(tick, 90000))
                with av.open(str(path)) as container:
                    expected = [frame.to_image().tobytes() for frame in container.decode(video=0)]
                reader = VideoReader(index)
                try:
                    for number in [0, 1, 2, 10, 3, 2, 11, 0, 0, 8, 9]:
                        self.assertEqual(reader.read(number).tobytes(), expected[number])
                finally:
                    reader.close()


if __name__ == "__main__":
    unittest.main()
