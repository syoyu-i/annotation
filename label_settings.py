"""ラベル名・ショートカットの検証と保存。"""
import json
from pathlib import Path
import config

SETTINGS_PATH = Path(__file__).with_name("label_settings.json")
DEFAULT_LABELS = [("left", "left"), ("right", "right")]
PALETTE = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6",
           "#06b6d4", "#ec4899", "#84cc16", "#a16207", "#64748b"]


def validate_labels(rows):
    if not 1 <= len(rows) <= 10:
        raise ValueError("ラベルは1〜10個にしてください（左右を含む）。")
    result = []
    for name, key in rows:
        name, key = name.strip(), key.strip().lower()
        if not name or len(name) > 40 or any(ord(c) < 32 for c in name):
            raise ValueError("ラベル名は1〜40文字で入力してください。")
        if key not in ("left", "right", "up", "down") and not (len(key) == 1 and key in "abcdefghijklmnopqrstuvwxyz0123456789"):
            raise ValueError("キーは英数字1文字、または Left / Right / Up / Down を指定してください。")
        if key in (config.EXTEND_KEY, config.SHRINK_KEY):
            raise ValueError("Q/Wなど、コマ送り用キーは割り当てられません。")
        if name in [n for n, _ in result] or key in [k for _, k in result]:
            raise ValueError("ラベル名とキーはそれぞれ重複しないようにしてください。")
        result.append((name, key))
    return result


def load_labels():
    if not SETTINGS_PATH.exists():
        return DEFAULT_LABELS.copy()
    return validate_labels(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))


def save_labels(rows):
    rows = validate_labels(rows)
    temporary = SETTINGS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SETTINGS_PATH)


def label_colors(rows):
    return {None: config.COLORS[None], **{name: PALETTE[i] for i, (name, _) in enumerate(rows)}}
