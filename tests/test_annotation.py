import csv
from fractions import Fraction
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET

from annotation_model import Annotation
from export import export_files


class AnnotationTests(unittest.TestCase):
    def test_shrink_restores_overwritten_labels_and_undo_is_one_gesture(self):
        model = Annotation(5)
        model.begin("left")
        model.resize(3)
        model.commit()
        model.seek(1)
        model.begin("right")
        model.resize(3)
        model.resize(-2)
        self.assertEqual(model.labels, ["left", "right", "right", "left", None])
        model.commit()
        self.assertEqual(model.cursor, 3)
        model.undo()
        self.assertEqual(model.labels, ["left"] * 4 + [None])
        self.assertEqual(model.cursor, 1)
        self.assertEqual(model.labeled_count, 4)

    def test_active_undo_cancels_only_current_gesture(self):
        model = Annotation(4)
        model.begin("left")
        model.commit()
        model.begin("right")
        model.resize(2)
        model.undo()
        self.assertEqual(model.labels, ["left", None, None, None])
        self.assertEqual(model.cursor, 1)
        model.undo()
        self.assertEqual(model.labels, [None] * 4)
        self.assertEqual(model.labeled_count, 0)

    def test_boundaries_completion_and_repeated_resize(self):
        model = Annotation(3)
        model.begin("right")
        model.resize(-100)
        self.assertEqual(model.active["length"], 1)
        model.resize(100)
        self.assertTrue(model.complete)
        model.resize(-1)
        self.assertFalse(model.complete)
        model.resize(1)
        model.commit()
        self.assertEqual(model.cursor, 2)
        self.assertTrue(model.complete)
        model.undo()
        self.assertEqual(model.labels, [None] * 3)

    def test_single_frame(self):
        model = Annotation(1)
        model.begin("left")
        model.commit()
        self.assertTrue(model.complete)
        self.assertEqual(model.cursor, 0)
        model.undo()
        self.assertFalse(model.complete)

    def test_exports_match_variable_timestamps_and_chart_counts(self):
        index = SimpleNamespace(path="sample&video.mp4", frames=[
            SimpleNamespace(time=Fraction(0), duration=Fraction(1, 30)),
            SimpleNamespace(time=Fraction(1, 30), duration=Fraction(1, 15)),
            SimpleNamespace(time=Fraction(1, 10), duration=Fraction(1, 30))])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.csv"
            with self.assertRaises(ValueError):
                export_files(path, index, ["left", None, "right"])
            self.assertFalse(path.exists())
            for labels in (["left", "right", "right"], ["left"] * 3, ["right"] * 3):
                csv_path, svg_path = export_files(path, index, labels)
                with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual([row["label"] for row in rows], labels)
                self.assertEqual(rows[2]["time_seconds"], "0.100000000")
                self.assertEqual(rows[1]["duration_seconds"], "0.066666667")
                root = ET.parse(svg_path).getroot()
                text = " ".join(root.itertext())
                self.assertIn(f"Left: {labels.count('left')}", text)
                self.assertIn("sample&video.mp4", text)


if __name__ == "__main__":
    unittest.main()
