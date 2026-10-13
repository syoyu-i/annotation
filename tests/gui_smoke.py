"""GUI環境があるときだけ明示的に実行する画面・操作の結合テスト。"""

from fractions import Fraction
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from annotation_model import Annotation
from app import App
from label_settings import label_colors


class GuiSmokeTests(unittest.TestCase):
    def test_controls_keyboard_timeline_and_export(self):
        app = App()
        app.withdraw()
        app.index = SimpleNamespace(path="test.mp4", frames=[
            SimpleNamespace(time=Fraction(i, 30), duration=Fraction(1, 30)) for i in range(5)])
        app.model = Annotation(5)
        app.reader = SimpleNamespace(read=lambda number: Image.new("RGB", (80, 60)), close=lambda: None)

        def press(key, state=0):
            app.key_press(SimpleNamespace(keysym=key, state=state, widget=app))

        try:
            app.refresh()
            app.update()
            self.assertTrue(app.finish_button.instate(["disabled"]))
            press("Left")
            press("w")
            press("w")
            press("q")
            self.assertEqual(app.model.labels, ["left", "left", None, None, None])
            app.key_release(SimpleNamespace(keysym="Left"))
            app.update()
            self.assertEqual(app.model.cursor, 2)
            press("z", state=0x4)
            self.assertEqual(app.model.labels, [None] * 5)
            self.assertEqual(app.model.cursor, 0)
            press("Right")
            for _ in range(4):
                press("w")
            self.assertTrue(app.finish_button.instate(["disabled"]))
            app.key_release(SimpleNamespace(keysym="Right"))
            app.update()
            self.assertTrue(app.finish_button.instate(["!disabled"]))
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "labels.csv"
                with patch("app.filedialog.asksaveasfilename", return_value=str(path)), patch("app.messagebox.showinfo"):
                    app.finish_button.invoke()
                self.assertTrue(path.exists())
                self.assertTrue(path.with_suffix(".svg").exists())
                self.assertFalse(app.dirty)
            app.undo()
            self.assertTrue(app.finish_button.instate(["disabled"]))
            app.label_definitions = [("left", "a"), ("right", "d"), ("静止", "s")]
            app.colors = label_colors(app.label_definitions)
            app.model.allowed_labels = ("left", "right", "静止")
            app.rebuild_label_buttons()
            press("s")
            for _ in range(4):
                press("w")
            app.key_release(SimpleNamespace(keysym="s"))
            app.update()
            self.assertEqual(app.model.labels, ["静止"] * 5)
            app.undo()
            press("Left")
            self.assertIsNone(app.model.active)
            press("a")
            app.key_release(SimpleNamespace(keysym="a"))
            app.update()
            self.assertEqual(app.model.labels[0], "left")
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
