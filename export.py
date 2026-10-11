"""CSVと、外部ライブラリ不要のSVG円グラフを生成する。"""

import csv
import math
from pathlib import Path
from xml.sax.saxutils import escape
import config


def export_files(csv_path, index, labels):
    if len(labels) != len(index.frames) or not labels or any(x not in ("left", "right") for x in labels):
        raise ValueError("全フレームへのラベル付けが必要です。")
    csv_path = Path(csv_path)
    with csv_path.open("w", newline="", encoding=config.CSV_ENCODING) as handle:
        writer = csv.writer(handle)
        writer.writerow(["frame_index", "time_seconds", "duration_seconds", "label"])
        for i, (frame, label) in enumerate(zip(index.frames, labels)):
            writer.writerow([i, f"{float(frame.time):.{config.TIME_DECIMALS}f}",
                             f"{float(frame.duration):.{config.TIME_DECIMALS}f}", label])
    left = labels.count("left")
    right = len(labels) - left
    ratio = left / len(labels)
    if left == 0 or right == 0:
        chart = f'<circle cx="180" cy="185" r="125" fill="{config.COLORS["left" if left else "right"]}"/>'
    else:
        angle = ratio * math.tau - math.pi / 2
        x, y = 180 + 125 * math.cos(angle), 185 + 125 * math.sin(angle)
        chart = (f'<circle cx="180" cy="185" r="125" fill="{config.COLORS["right"]}"/>'
                 f'<path d="M 180 185 L 180 60 A 125 125 0 {int(ratio > .5)} 1 {x:.5f} {y:.5f} Z" '
                 f'fill="{config.COLORS["left"]}"/>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="660" height="380" viewBox="0 0 660 380">
<rect width="660" height="380" fill="white"/>
<g font-family="sans-serif" fill="#111827">
<text x="24" y="30" font-size="18">Direction labels (frame count)</text>
{chart}
<rect x="340" y="115" width="18" height="18" fill="{config.COLORS['left']}"/>
<text x="370" y="130" font-size="18">Left: {left:,} ({ratio:.1%})</text>
<rect x="340" y="165" width="18" height="18" fill="{config.COLORS['right']}"/>
<text x="370" y="180" font-size="18">Right: {right:,} ({1-ratio:.1%})</text>
<text x="340" y="235" font-size="16">Total: {len(labels):,} frames</text>
<text x="24" y="355" font-size="12">{escape(Path(index.path).name)}</text>
</g></svg>'''
    svg_path = csv_path.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    return csv_path, svg_path
