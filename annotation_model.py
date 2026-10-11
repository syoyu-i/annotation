"""UI・動画ライブラリに依存しない、フレーム単位の編集処理。"""

from dataclasses import dataclass


@dataclass
class Edit:
    start: int
    before: list
    cursor: int


class Annotation:
    def __init__(self, count):
        self.labels = [None] * count
        self.cursor = 0
        self.history = []
        self.active = None
        self.labeled_count = 0

    @property
    def complete(self):
        return bool(self.labels) and self.labeled_count == len(self.labels)

    def _set(self, index, value):
        old = self.labels[index]
        self.labeled_count += int(value is not None) - int(old is not None)
        self.labels[index] = value

    def begin(self, label):
        if label not in ("left", "right"):
            raise ValueError("Unknown label")
        if self.active or not self.labels:
            return
        self.active = {"start": self.cursor, "label": label, "before": [], "length": 0}
        self.resize(1)

    def resize(self, delta):
        if not self.active:
            return
        edit = self.active
        start, old = edit["start"], edit["length"]
        length = max(1, min(len(self.labels) - start, old + delta))
        if length > old:
            for offset in range(old, length):
                edit["before"].append(self.labels[start + offset])
                self._set(start + offset, edit["label"])
        else:
            for offset in range(old - 1, length - 1, -1):
                self._set(start + offset, edit["before"].pop())
        edit["length"] = length
        self.cursor = start + length - 1

    def commit(self):
        if not self.active:
            return
        edit = self.active
        start = edit["start"]
        if self.labels[start:start + edit["length"]] != edit["before"]:
            self.history.append(Edit(start, edit["before"].copy(), start))
        self.cursor = min(len(self.labels) - 1, start + edit["length"])
        self.active = None

    def undo(self):
        if self.active:
            edit = self.active
            for offset, value in enumerate(edit["before"]):
                self._set(edit["start"] + offset, value)
            self.cursor = edit["start"]
            self.active = None
        elif self.history:
            edit = self.history.pop()
            for offset, value in enumerate(edit.before):
                self._set(edit.start + offset, value)
            self.cursor = edit.cursor

    def seek(self, index):
        if self.labels and not self.active:
            self.cursor = max(0, min(len(self.labels) - 1, index))
