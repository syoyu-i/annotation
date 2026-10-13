import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from annotation_model import Annotation
from export import export_files
from label_settings import validate_labels, label_colors, save_labels, load_labels


class LabelTests(unittest.TestCase):
    def test_validation_limits_duplicates_and_reserved_keys(self):
        rows = [(f"label{i}", str(i)) for i in range(10)]
        self.assertEqual(validate_labels(rows), rows)
        for invalid in ([], rows + [("extra", "a")], [("a", "w")],
                        [("a", "q")], [("a", "F1")], [("", "a")],
                        [("a", "1"), ("a", "2")], [("a", "A"), ("b", "a")]):
            with self.assertRaises(ValueError):
                validate_labels(invalid)

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("label_settings.SETTINGS_PATH", Path(directory) / "settings.json"):
                save_labels([("左", "Left"), ("静止", "s")])
                self.assertEqual(load_labels(), [("左", "left"), ("静止", "s")])

    def test_custom_label_edit_undo_and_export(self):
        rows = [("left", "left"), ("right", "right"), ("静止<&", "s")]
        model = Annotation(3, [n for n, _ in rows])
        model.begin("静止<&")
        model.resize(2)
        model.resize(-1)
        self.assertEqual(model.labels, ["静止<&", "静止<&", None])
        model.resize(1)
        model.commit()
        self.assertTrue(model.complete)
        index = SimpleNamespace(path="test.mp4", frames=[SimpleNamespace(time=i, duration=1) for i in range(3)])
        with tempfile.TemporaryDirectory() as directory:
            csv_path, svg_path = export_files(Path(directory) / "labels.csv", index, model.labels, label_colors(rows))
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                self.assertEqual([r['label'] for r in csv.DictReader(handle)], model.labels)
            self.assertIn("静止<&: 3 (100.0%)", "".join(ET.parse(svg_path).getroot().itertext()))
            export_files(csv_path, index, ["left", "right", "静止<&"], label_colors(rows))
            self.assertEqual(len(ET.parse(svg_path).getroot().findall('.//{http://www.w3.org/2000/svg}path')), 3)
        model.undo()
        self.assertEqual(model.labels, [None] * 3)
