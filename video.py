"""PyAVで表示順にフレームを列挙し、実際のPTSを保持する。"""

from dataclasses import dataclass
from fractions import Fraction
import av


@dataclass(frozen=True)
class FrameInfo:
    pts: int
    time: Fraction
    duration: Fraction


@dataclass
class VideoIndex:
    path: str
    frames: list
    fps: object
    variable_rate: bool
    stream_index: int


def scan(path, progress=lambda count: None):
    frames = []
    with av.open(path) as container:
        if not container.streams.video:
            raise ValueError("動画ストリームがありません。")
        stream = container.streams.video[0]
        fps = stream.average_rate
        fallback = 1 / fps if fps else Fraction(0)
        for frame in container.decode(stream):
            if frame.is_corrupt:
                raise ValueError("破損したフレームがあります。動画を修復してから読み込んでください。")
            if frame.pts is None:
                raise ValueError("時刻情報のないフレームがあります。この動画には対応していません。")
            timestamp = frame.pts * frame.time_base
            if frames and timestamp <= frames[-1].time:
                raise ValueError("フレーム時刻が重複・逆転しています。動画を変換してから読み込んでください。")
            duration = getattr(frame, "duration", 0)
            frames.append(FrameInfo(frame.pts, timestamp, duration * frame.time_base if duration else fallback))
            if len(frames) % 100 == 0:
                progress(len(frames))
        if not frames:
            raise ValueError("読み取れるフレームがありません。")
        origin = frames[0].time
        intervals = [frames[i + 1].time - frames[i].time for i in range(len(frames) - 1)]
        last_duration = frames[-1].duration or (intervals[-1] if intervals else Fraction(0))
        normalized = [FrameInfo(f.pts, f.time - origin, intervals[i] if i < len(intervals) else last_duration)
                      for i, f in enumerate(frames)]
        # 時間基準の丸め誤差（1 tick程度）をVFRと誤判定しない。
        variable = bool(intervals) and max(intervals) - min(intervals) > stream.time_base * 2
        return VideoIndex(path, normalized, fps, variable, stream.index)


class VideoReader:
    def __init__(self, index):
        self.index = index
        self.container = av.open(index.path)
        self.stream = self.container.streams[index.stream_index]
        self.iterator = iter(self.container.decode(self.stream))
        self.last_index = -1
        self.last_image = None

    def read(self, number):
        if number == self.last_index:
            return self.last_image
        target = self.index.frames[number].pts
        if number != self.last_index + 1:
            try:
                self.container.seek(target, stream=self.stream, backward=True, any_frame=False)
            except av.FFmpegError:
                self.container.close()
                self.container = av.open(self.index.path)
                self.stream = self.container.streams[self.index.stream_index]
            self.iterator = iter(self.container.decode(self.stream))
        for frame in self.iterator:
            if frame.pts == target:
                self.last_index = number
                self.last_image = frame.to_image()
                return self.last_image
            if frame.pts is not None and frame.pts > target:
                break
        # シーク位置が不正確なコンテナも、先頭からの再読込で正確さを優先する。
        self.container.close()
        self.container = av.open(self.index.path)
        self.stream = self.container.streams[self.index.stream_index]
        self.iterator = iter(self.container.decode(self.stream))
        for i, frame in enumerate(self.iterator):
            if i == number:
                self.last_index = number
                self.last_image = frame.to_image()
                return self.last_image
        raise ValueError(f"フレーム {number} を読み込めませんでした。")

    def close(self):
        self.container.close()
