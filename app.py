"""起動: python app.py"""

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

import config
from annotation_model import Annotation
from label_settings import load_labels, save_labels, validate_labels, label_colors
from export import export_files
from video import VideoReader, scan


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("動画ラベルアノテーション")
        try:
            self.label_definitions = load_labels()
        except (ValueError, TypeError, OSError) as exc:
            messagebox.showwarning("ラベル設定", f"設定を読み込めないため左右の初期設定を使用します。\n{exc}")
            self.label_definitions = [("left", "left"), ("right", "right")]
        self.colors = label_colors(self.label_definitions)
        self.geometry(config.WINDOW_SIZE)
        self.minsize(800, 620)
        self.model = None
        self.index = None
        self.reader = None
        self.loading = False
        self.dirty = False
        self.held_arrow = None
        self.release_job = None
        self.preview_job = None
        self.messages = queue.Queue()
        self.photo = None
        self._build()
        self.bind("<KeyPress>", self.key_press)
        self.bind("<KeyRelease>", self.key_release)
        self.bind("<FocusOut>", self.focus_out)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(80, self.poll)

    def _build(self):
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        self.open_button = ttk.Button(top, text="動画を開く", command=self.open_video)
        self.open_button.pack(side="left")
        ttk.Button(top, text="ラベル設定", command=self.configure_labels).pack(side="left", padx=8)
        self.info = ttk.Label(top, text="動画を選択してください", padding=(12, 0))
        self.info.pack(side="left")
        self.video_canvas = tk.Canvas(self, bg=config.VIDEO_BACKGROUND, highlightthickness=0)
        self.video_canvas.pack(fill="both", expand=True, padx=12)
        self.video_canvas.bind("<Configure>", lambda event: self.schedule_preview())
        self.position = ttk.Label(self, text="", padding=(12, 8))
        self.position.pack(fill="x")
        controls = ttk.Frame(self, padding=(12, 4))
        controls.pack(fill="x")
        self.edit_buttons = []
        for title, action in [("1フレーム戻る", lambda: self.step(-1)),
                              ("1フレーム進む", lambda: self.step(1)),
                              ("元に戻す (Ctrl+Z)", self.undo)]:
            button = ttk.Button(controls, text=title, command=action, state="disabled")
            button.pack(side="left", padx=(0, 8))
            self.edit_buttons.append(button)
        self.finish_button = ttk.Button(controls, text="完了・CSVと円グラフを出力", command=self.finish, state="disabled")
        self.finish_button.pack(side="right")
        self.label_controls = ttk.Frame(self, padding=(12, 4))
        self.label_controls.pack(fill="x")
        self.rebuild_label_buttons()
        text = (f"ラベルキー：離すと確定して次へ。押したまま {config.EXTEND_KEY.upper()}：延長 / {config.SHRINK_KEY.upper()}：短縮\n"
                f"ラベルキーを押していないときは {config.SHRINK_KEY.upper()} / {config.EXTEND_KEY.upper()} でコマ送り。灰＝未入力。")
        ttk.Label(self, text=text, padding=(12, 8)).pack(fill="x")
        self.timeline = tk.Canvas(self, height=config.TIMELINE_HEIGHT, bg="white", highlightthickness=1,
                                  highlightbackground="#d1d5db")
        self.timeline.pack(fill="x", padx=12)
        self.scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.scroll_timeline)
        self.scrollbar.pack(fill="x", padx=12)
        self.timeline.configure(xscrollcommand=self.scrollbar.set)
        self.timeline.bind("<Configure>", lambda event: self.draw_timeline())
        self.timeline.bind("<Button-1>", self.timeline_click)
        self.status = ttk.Label(self, text="", padding=12)
        self.status.pack(fill="x")

    def rebuild_label_buttons(self):
        for child in self.label_controls.winfo_children():
            if child in self.edit_buttons:
                self.edit_buttons.remove(child)
            child.destroy()
        for i, (name, key) in enumerate(self.label_definitions):
            button = ttk.Button(self.label_controls, text=f"{key.upper()}：{name}",
                                command=lambda label=name: self.label_one(label),
                                state="normal" if self.ready() else "disabled")
            button.grid(row=i // 5, column=i % 5, padx=(0, 8), pady=3, sticky="w")
            self.edit_buttons.append(button)

    def configure_labels(self):
        if self.loading:
            return
        self.commit_gesture()
        dialog = tk.Toplevel(self)
        dialog.title("ラベル設定（最大10個・左右を含む）")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text="既存ラベルのキー変更と新規追加ができます。Q/Wは予約済み。", padding=12).grid(row=0, columnspan=2)
        ttk.Label(dialog, text="ラベル名").grid(row=1, column=0)
        ttk.Label(dialog, text="キー（英数字 / Left / Right / Up / Down）").grid(row=1, column=1)
        entries = []
        for i in range(10):
            name = tk.StringVar(value=self.label_definitions[i][0] if i < len(self.label_definitions) else "")
            key = tk.StringVar(value=self.label_definitions[i][1] if i < len(self.label_definitions) else "")
            ttk.Entry(dialog, textvariable=name, state="readonly" if i < len(self.label_definitions) else "normal").grid(row=i+2, column=0, padx=12, pady=3)
            ttk.Entry(dialog, textvariable=key).grid(row=i+2, column=1, padx=12, pady=3)
            entries.append((name, key))

        def apply():
            try:
                rows = validate_labels([(n.get(), k.get()) for n, k in entries if n.get().strip() or k.get().strip()])
                save_labels(rows)
            except (ValueError, OSError) as exc:
                messagebox.showerror("ラベル設定", str(exc), parent=dialog)
                return
            self.label_definitions = rows
            self.colors = label_colors(rows)
            if self.model:
                self.model.allowed_labels = tuple(n for n, _ in rows)
            self.rebuild_label_buttons()
            self.refresh()
            dialog.destroy()
            self.focus_set()

        ttk.Button(dialog, text="保存", command=apply).grid(row=12, column=0, pady=12)
        ttk.Button(dialog, text="キャンセル", command=dialog.destroy).grid(row=12, column=1, pady=12)

    def open_video(self):
        if self.loading:
            return
        self.commit_gesture()
        if self.dirty and not messagebox.askyesno("動画を変更", "出力していないラベルを破棄して別の動画を開きますか？"):
            return
        path = filedialog.askopenfilename(title="動画を選択", filetypes=[
            ("動画", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mpeg *.mpg"), ("すべて", "*.*")])
        if not path:
            return
        self.loading = True
        self.open_button.configure(state="disabled")
        for button in self.edit_buttons:
            button.configure(state="disabled")
        self.finish_button.configure(state="disabled")
        self.status.configure(text="全フレームの時刻を確認中… 動画の長さに応じて時間がかかります。")

        def worker():
            try:
                index = scan(path, lambda count: self.messages.put(("progress", count)))
                self.messages.put(("loaded", index))
            except Exception as exc:
                self.messages.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "progress":
                    self.status.configure(text=f"全フレームの時刻を確認中… {value:,} フレーム")
                    continue
                self.loading = False
                self.open_button.configure(state="normal")
                if kind == "loaded":
                    try:
                        reader = VideoReader(value)
                        reader.read(0)
                    except Exception as exc:
                        if "reader" in locals():
                            reader.close()
                        messagebox.showerror("読み込みエラー", str(exc))
                    else:
                        if self.reader:
                            self.reader.close()
                        self.reader, self.index = reader, value
                        self.model = Annotation(len(value.frames), [name for name, _ in self.label_definitions])
                        self.dirty = False
                        fps = f"{float(value.fps):.6g} fps ({value.fps})" if value.fps else "FPS情報なし"
                        mode = "可変間隔" if value.variable_rate else "固定間隔"
                        self.info.configure(text=f"{Path(value.path).name}  |  {fps}  |  {mode}  |  {len(value.frames):,} frames")
                        self.timeline.xview_moveto(0)
                else:
                    messagebox.showerror("読み込みエラー", value)
                for button in self.edit_buttons:
                    button.configure(state="normal" if self.model else "disabled")
                self.refresh()
        except queue.Empty:
            pass
        self.after(80, self.poll)

    def ready(self):
        return self.model is not None and not self.loading

    def key_press(self, event):
        if not self.ready() or event.widget.winfo_toplevel() != self:
            return
        key = event.keysym.lower()
        if event.state & 0x4 and key == "z":
            self.undo()
            return "break"
        if event.state & (0x4 | 0x8):
            return
        key_labels = {shortcut: name for name, shortcut in self.label_definitions}
        if key in key_labels:
            if key == self.held_arrow:
                if self.release_job:
                    self.after_cancel(self.release_job)
                    self.release_job = None
                return "break"
            if self.held_arrow is None:
                self.held_arrow = key
                self.model.begin(key_labels[key])
                self.dirty = True
                self.refresh()
            return "break"
        if key in (config.EXTEND_KEY, config.SHRINK_KEY):
            delta = 1 if key == config.EXTEND_KEY else -1
            if self.model.active:
                self.model.resize(delta)
                self.refresh()
            else:
                self.step(delta)
            return "break"

    def key_release(self, event):
        if event.keysym.lower() == self.held_arrow:
            if self.release_job:
                self.after_cancel(self.release_job)
            # X11の自動リピートが生成するRelease→Pressは確定しない。
            self.release_job = self.after_idle(self.commit_gesture)
            return "break"

    def focus_out(self, event):
        self.after_idle(self.check_focus)

    def check_focus(self):
        focus = self.focus_get()
        if focus is None or focus.winfo_toplevel() != self:
            self.commit_gesture()

    def commit_gesture(self):
        if self.release_job:
            self.after_cancel(self.release_job)
            self.release_job = None
        self.held_arrow = None
        if self.model and self.model.active:
            self.model.commit()
            self.refresh()

    def label_one(self, label):
        if not self.ready():
            return
        self.commit_gesture()
        self.model.begin(label)
        self.model.commit()
        self.dirty = True
        self.refresh()

    def undo(self):
        if not self.ready():
            return
        if self.release_job:
            self.after_cancel(self.release_job)
            self.release_job = None
        self.held_arrow = None
        self.model.undo()
        self.dirty = True
        self.refresh()

    def step(self, delta):
        if self.ready() and not self.model.active:
            self.model.seek(self.model.cursor + delta)
            self.refresh()

    def timeline_click(self, event):
        if self.ready() and not self.model.active:
            self.focus_set()
            self.model.seek(int(self.timeline.canvasx(event.x) // config.FRAME_WIDTH))
            self.refresh()

    def refresh(self):
        if not self.model:
            self.status.configure(text="動画を選択してください。")
            return
        model = self.model
        frame = self.index.frames[model.cursor]
        label = model.labels[model.cursor] or "未入力"
        active = f"  |  編集区間：{model.active['length']} フレーム" if model.active else ""
        self.position.configure(text=f"フレーム {model.cursor + 1:,} / {len(model.labels):,}  "
                                     f"（CSV index: {model.cursor}）  |  {float(frame.time):.6f} 秒  |  {label}{active}")
        done = model.labeled_count
        self.status.configure(text=f"ラベル付け済み {done:,} / {len(model.labels):,}  ({done / len(model.labels):.1%})"
                                   + (" — 全フレーム完了。出力できます。" if model.complete else ""))
        self.finish_button.configure(state="normal" if model.complete and not model.active and not self.loading else "disabled")
        total_width = max(len(model.labels) * config.FRAME_WIDTH, self.timeline.winfo_width())
        self.timeline.configure(scrollregion=(0, 0, total_width, config.TIMELINE_HEIGHT))
        x = model.cursor * config.FRAME_WIDTH
        start = self.timeline.canvasx(0)
        width = self.timeline.winfo_width()
        if x < start or x + config.FRAME_WIDTH > start + width:
            self.timeline.xview_moveto(max(0, x - width // 2) / total_width)
        self.draw_timeline()
        self.schedule_preview()

    def schedule_preview(self):
        if self.preview_job:
            self.after_cancel(self.preview_job)
        self.preview_job = self.after_idle(self.show_preview)

    def show_preview(self):
        self.preview_job = None
        if not self.reader or not self.model:
            return
        try:
            image = self.reader.read(self.model.cursor).copy()
            image.thumbnail((max(1, self.video_canvas.winfo_width()), max(1, self.video_canvas.winfo_height())), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(image)
            self.video_canvas.delete("all")
            self.video_canvas.create_image(self.video_canvas.winfo_width() / 2, self.video_canvas.winfo_height() / 2, image=self.photo)
        except Exception as exc:
            self.video_canvas.delete("all")
            self.video_canvas.create_text(20, 20, anchor="nw", fill="white", text=f"フレーム表示エラー：{exc}")

    def scroll_timeline(self, *args):
        self.timeline.xview(*args)
        self.draw_timeline()

    def draw_timeline(self):
        canvas = self.timeline
        canvas.delete("all")
        if not self.model:
            return
        width = config.FRAME_WIDTH
        first = max(0, int(canvas.canvasx(0) // width))
        last = min(len(self.model.labels), int(canvas.canvasx(canvas.winfo_width()) // width) + 2)
        tick = max(1, round(90 / width))
        for i in range(first, last):
            x = i * width
            canvas.create_rectangle(x, 30, x + width, 70, fill=self.colors[self.model.labels[i]], outline="white")
            if i % tick == 0:
                canvas.create_text(x + 2, 15, anchor="w", text=str(i + 1), fill="#374151")
                canvas.create_text(x + 2, 90, anchor="w", text=f"{float(self.index.frames[i].time):.2f}s", fill="#6b7280")
        if self.model.active:
            edit = self.model.active
            canvas.create_rectangle(edit["start"] * width, 28, (edit["start"] + edit["length"]) * width, 72,
                                    outline="#111827", width=2)
        x = (self.model.cursor + .5) * width
        canvas.create_line(x, 22, x, 78, fill="#111827", width=2)
        canvas.create_polygon(x - 5, 20, x + 5, 20, x, 27, fill="#111827")

    def finish(self):
        if not self.ready() or not self.model.complete or self.model.active:
            return
        path = filedialog.asksaveasfilename(title="CSVと円グラフの保存先", defaultextension=".csv",
                                          initialfile=Path(self.index.path).stem + "_labels.csv",
                                          filetypes=[("CSV", "*.csv")], confirmoverwrite=False)
        if not path:
            return
        path = Path(path).with_suffix(".csv")
        svg = path.with_suffix(".svg")
        existing = [str(p) for p in (path, svg) if p.exists()]
        if existing and not messagebox.askyesno("出力の上書き", "次のファイルを上書きしますか？\n" + "\n".join(existing)):
            return
        try:
            csv_path, svg_path = export_files(path, self.index, self.model.labels, self.colors)
        except Exception as exc:
            messagebox.showerror("出力エラー", f"出力を完了できませんでした。保存先をご確認ください。\n{exc}")
            return
        self.dirty = False
        messagebox.showinfo("出力完了", f"CSV：{csv_path}\n円グラフ：{svg_path}")

    def close(self):
        self.commit_gesture()
        if self.dirty and not messagebox.askyesno("終了", "出力していないラベルを破棄して終了しますか？"):
            return
        if self.reader:
            self.reader.close()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
