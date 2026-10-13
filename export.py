"""CSVと、外部ライブラリ不要のSVG円グラフを生成する。"""

import csv
import math
from pathlib import Path
from xml.sax.saxutils import escape
import config


def export_files(csv_path, index, labels, colors=None):
    colors = config.COLORS if colors is None else colors
    if len(labels) != len(index.frames) or not labels or any(x is None or x not in colors for x in labels):
        raise ValueError("全フレームへのラベル付けが必要です。")
    csv_path = Path(csv_path)
    with csv_path.open("w", newline="", encoding=config.CSV_ENCODING) as handle:
        writer = csv.writer(handle)
        writer.writerow(["frame_index", "time_seconds", "duration_seconds", "label"])
        for i, (frame, label) in enumerate(zip(index.frames, labels)):
            writer.writerow([i, f"{float(frame.time):.{config.TIME_DECIMALS}f}",
                             f"{float(frame.duration):.{config.TIME_DECIMALS}f}", label])
    chart, legend = [], []
    angle = -math.pi / 2
    names = [name for name in colors if name is not None]
    for i, name in enumerate(names):
        count = labels.count(name)
        ratio = count / len(labels)
        color = colors[name]
        end = angle + ratio * math.tau
        if count == len(labels):
            chart.append(f'<circle cx="180" cy="185" r="125" fill="{color}"/>')
        elif count:
            x1, y1 = 180 + 125 * math.cos(angle), 185 + 125 * math.sin(angle)
            x2, y2 = 180 + 125 * math.cos(end), 185 + 125 * math.sin(end)
            chart.append(f'<path d="M 180 185 L {x1:.5f} {y1:.5f} A 125 125 0 {int(ratio > .5)} 1 {x2:.5f} {y2:.5f} Z" fill="{color}"/>')
        angle = end
        y = 65 + i * 28
        display = {"left": "Left", "right": "Right"}.get(name, name)
        legend.append(f'<rect x="340" y="{y-14}" width="18" height="18" fill="{color}"/>'
                      f'<text x="370" y="{y}" font-size="16">{escape(display)}: {count:,} ({ratio:.1%})</text>')
    height = max(380, 140 + len(names) * 28)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}" viewBox="0 0 900 {height}">
<rect width="900" height="{height}" fill="white"/>
<g font-family="sans-serif" fill="#111827">
<text x="24" y="30" font-size="18">Labels (frame count)</text>
{''.join(chart)}
{''.join(legend)}
<text x="340" y="{85 + len(names)*28}" font-size="16">Total: {len(labels):,} frames</text>
<text x="24" y="{height-25}" font-size="12">{escape(Path(index.path).name)}</text>
</g></svg>'''
    svg_path = csv_path.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    return csv_path, svg_path
