#!/usr/bin/env python3
"""Compile a paper-grounded cinematic scroll intro for The AI Engineer.

The video is deliberately content-only. Page chrome, chapter captions, and
scroll progress stay in HTML so the same master works across viewport sizes.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
FS = ROOT / "frontend_static"
OM = FS / "oil_motion_ai_engineer"
DOCS = ROOT / "docs" / "assets"

W, H = 1920, 1080
FPS = 24
HOLD = 66
XFADE = 20

NAVY = (5, 15, 28)
NAVY_2 = (8, 29, 45)
TEAL = (72, 221, 207)
CYAN = (78, 184, 255)
BLUE = (73, 125, 255)
GREEN = (89, 218, 147)
ORANGE = (246, 146, 55)
RED = (247, 94, 79)
WHITE = (232, 247, 246)
MUTED = (144, 182, 190)

STAGES = [
    {
        "id": "K0",
        "title": "Natural-language requirements",
        "caption": "业主意图 · 场址约束 · 规范条款",
        "kind": "requirements",
    },
    {
        "id": "K1",
        "title": "LLM orchestration",
        "caption": "把自然语言编排成可执行工程任务",
        "kind": "orchestration",
    },
    {
        "id": "K2",
        "title": "Reference → design domain",
        "caption": "OC4 参考几何 · 设计/非设计域 · 网格/载荷",
        "kind": "domain",
    },
    {
        "id": "K3",
        "title": "CalculiX–BESO",
        "caption": "柔度–体积迭代 · 拓扑逐步生长",
        "kind": "topology",
    },
    {
        "id": "K4",
        "title": "Scaling → Zwind",
        "caption": "参数升尺度 · PSO 尺寸优化 · FOWT 时域校核",
        "kind": "validation",
    },
    {
        "id": "K5",
        "title": "Autonomous replan",
        "caption": "失败分层诊断 · 回到设计域 · 恢复闭环",
        "kind": "replan",
    },
    {
        "id": "K6",
        "title": "Automated Reviewer",
        "caption": "承载力 · 钢耗 · 造价 · 可建造性 · 疲劳",
        "kind": "review",
    },
    {
        "id": "K7",
        "title": "Certifiable deliverable",
        "caption": "图纸与报告 · 内部门禁通过 · 进入工作台",
        "kind": "deliverable",
    },
]


def rgba(color, alpha=255):
    return (*color, alpha)


def load(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def contain(image: Image.Image, box: tuple[int, int], scale=1.0) -> Image.Image:
    bw, bh = box
    iw, ih = image.size
    ratio = min(bw / iw, bh / ih) * scale
    size = (max(1, int(iw * ratio)), max(1, int(ih * ratio)))
    return image.resize(size, Image.Resampling.LANCZOS)


def cover(image: Image.Image, box: tuple[int, int], scale=1.0) -> Image.Image:
    bw, bh = box
    iw, ih = image.size
    ratio = max(bw / iw, bh / ih) * scale
    size = (max(1, int(iw * ratio)), max(1, int(ih * ratio)))
    resized = image.resize(size, Image.Resampling.LANCZOS)
    left = max(0, (resized.width - bw) // 2)
    top = max(0, (resized.height - bh) // 2)
    return resized.crop((left, top, left + bw, top + bh))


def make_gradient(top=NAVY, bottom=(4, 11, 21)) -> Image.Image:
    image = Image.new("RGBA", (W, H))
    pixels = image.load()
    for y in range(H):
        t = y / max(1, H - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(W):
            pixels[x, y] = rgba(color)
    return image


def add_light(canvas: Image.Image, center: tuple[int, int], radius: int, color, alpha=90):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=rgba(color, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(max(8, radius // 3)))
    canvas.alpha_composite(layer)


def grid(canvas: Image.Image, alpha=34, step=72, offset=0):
    draw = ImageDraw.Draw(canvas)
    for x in range(-H, W + H, step):
        draw.line((x + offset, 0, x + H + offset, H), fill=rgba(CYAN, alpha), width=1)
        draw.line((x + offset, H, x + H + offset, 0), fill=rgba(CYAN, alpha), width=1)
    for y in range(0, H + step, step):
        draw.line((0, y, W, y), fill=rgba(TEAL, max(8, alpha // 2)), width=1)


def particles(canvas: Image.Image, seed: int, alpha=120, count=150, drift=0):
    draw = ImageDraw.Draw(canvas)
    for i in range(count):
        # Deterministic pseudo-random distribution keeps every render reproducible.
        x = (seed * 97 + i * 137) % (W + 260) - 130
        y = (seed * 53 + i * 83) % (H + 180) - 90
        r = 1 + ((seed + i * 11) % 4)
        color = TEAL if i % 3 else CYAN
        draw.ellipse((x + drift - r, y - r, x + drift + r, y + r), fill=rgba(color, alpha))


def soft_shadow(image: Image.Image, blur=24, opacity=110) -> Image.Image:
    alpha = image.getchannel("A")
    shadow = Image.new("RGBA", image.size, rgba((0, 0, 0), 0))
    shadow.putalpha(alpha.point(lambda value: int(value * opacity / 255)))
    return shadow.filter(ImageFilter.GaussianBlur(blur))


def cutout(path: Path, target_size: tuple[int, int], crop=(0.5, 0.54), scale=1.0) -> Image.Image:
    """Remove the near-white studio background from one of the paper renders."""
    source = load(path)
    rgb = source.convert("RGB")
    white = Image.new("RGB", rgb.size, (255, 255, 255))
    distance = ImageChops.difference(rgb, white).convert("L")
    # The source renders have a cool-gray studio sweep; keep the colored
    # structure but discard that sweep before compositing on dark scenes.
    alpha = distance.point(lambda value: 0 if value < 55 else min(255, (value - 42) * 12))
    source.putalpha(alpha)
    image = contain(source, target_size, scale=scale)
    canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
    x = int((target_size[0] - image.width) * crop[0])
    y = int((target_size[1] - image.height) * crop[1])
    canvas.alpha_composite(image, (x, y))
    return canvas


def ocean_background(dark=True) -> Image.Image:
    source = cover(load(DOCS / "ai_sea.png"), (W, H), scale=1.18)
    source = ImageEnhance.Color(source).enhance(0.72 if dark else 1.0)
    source = ImageEnhance.Contrast(source).enhance(1.08)
    source.alpha_composite(Image.new("RGBA", (W, H), rgba(NAVY, 135 if dark else 35)))
    return source


def composite_model(canvas: Image.Image, optimized=True, x=0, y=0, scale=1.0, tint=None):
    source = DOCS / ("ai.png" if optimized else "ai_2.png")
    image = cutout(source, (860, 960), crop=(0.5, 0.55), scale=scale)
    if tint:
        color_layer = Image.new("RGBA", image.size, rgba(tint, 60))
        color_layer.putalpha(image.getchannel("A").point(lambda value: int(value * 0.35)))
        image = Image.alpha_composite(image, color_layer)
    canvas.alpha_composite(soft_shadow(image, blur=30, opacity=130), (x + 18, y + 26))
    canvas.alpha_composite(image, (x, y))


def path_line(draw, points, color=TEAL, width=4, alpha=210):
    draw.line(points, fill=rgba(color, alpha), width=width, joint="curve")
    for x, y in points[:: max(1, len(points) // 4)]:
        draw.ellipse((x - width * 1.2, y - width * 1.2, x + width * 1.2, y + width * 1.2), fill=rgba(color, alpha))


def node(draw, x, y, radius=18, color=TEAL, fill_alpha=38):
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=rgba(color, 230), width=3)
    draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=rgba(color, 230))
    draw.ellipse((x - radius + 6, y - radius + 6, x + radius - 6, y + radius - 6), fill=rgba(color, fill_alpha))


def draw_paper(draw, box, color=CYAN, alpha=120):
    x, y, w, h = box
    points = [(x, y), (x + w - 22, y), (x + w, y + 22), (x + w, y + h), (x, y + h)]
    draw.polygon(points, outline=rgba(color, alpha), fill=rgba(NAVY_2, 125))
    draw.line((x + w - 22, y, x + w - 22, y + 22, x + w, y + 22), fill=rgba(color, alpha), width=2)
    for offset in (42, 68, 94, 120):
        draw.line((x + 26, y + offset, x + w - 28, y + offset), fill=rgba(color, max(35, alpha // 2)), width=2)


def stage_requirements() -> Image.Image:
    canvas = ocean_background()
    add_light(canvas, (420, 290), 300, BLUE, 90)
    add_light(canvas, (1440, 720), 360, TEAL, 75)
    particles(canvas, 2, count=115, drift=-30)
    draw = ImageDraw.Draw(canvas)
    grid(canvas, alpha=18, step=96, offset=20)
    for box, color in [
        ((150, 180, 330, 300), CYAN),
        ((1340, 150, 360, 260), TEAL),
        ((200, 710, 300, 220), BLUE),
        ((1430, 700, 300, 240), GREEN),
    ]:
        draw_paper(draw, box, color=color, alpha=105)
    for i, (x, y) in enumerate([(540, 250), (1180, 230), (480, 770), (1260, 770)]):
        color = (CYAN, TEAL, BLUE, GREEN)[i]
        node(draw, x, y, radius=18, color=color)
        path_line(draw, [(x, y), (960, 540)], color=color, width=2, alpha=80)
    composite_model(canvas, optimized=False, x=600, y=150, scale=0.86, tint=CYAN)
    canvas.alpha_composite(Image.new("RGBA", (W, H), rgba(NAVY, 35)))
    return canvas


def stage_orchestration() -> Image.Image:
    canvas = make_gradient((5, 22, 37), (4, 10, 22))
    add_light(canvas, (960, 500), 330, TEAL, 120)
    add_light(canvas, (350, 720), 240, BLUE, 65)
    add_light(canvas, (1580, 300), 240, GREEN, 55)
    particles(canvas, 5, count=190, alpha=130)
    draw = ImageDraw.Draw(canvas)
    center = (960, 500)
    draw.ellipse((770, 310, 1150, 690), fill=rgba((6, 34, 48), 220), outline=rgba(TEAL, 235), width=4)
    draw.ellipse((822, 362, 1098, 638), outline=rgba(CYAN, 120), width=2)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x = center[0] + int(math.cos(rad) * 82)
        y = center[1] + int(math.sin(rad) * 82)
        path_line(draw, [center, (x, y)], color=TEAL, width=3, alpha=190)
        node(draw, x, y, radius=13, color=CYAN)
    for x, y, color in [(320, 270, CYAN), (1600, 270, GREEN), (330, 800, BLUE), (1580, 790, ORANGE)]:
        path_line(draw, [(x, y), (960, 500)], color=color, width=3, alpha=145)
        node(draw, x, y, radius=34, color=color, fill_alpha=48)
    composite_model(canvas, optimized=False, x=650, y=170, scale=0.65, tint=TEAL)
    return canvas


def stage_domain() -> Image.Image:
    canvas = make_gradient((4, 26, 40), (3, 14, 25))
    add_light(canvas, (960, 560), 390, CYAN, 95)
    particles(canvas, 8, count=130, alpha=110)
    draw = ImageDraw.Draw(canvas)
    grid(canvas, alpha=30, step=68, offset=-10)
    front = [(660, 380), (1240, 380), (1240, 760), (660, 760)]
    back = [(820, 270), (1400, 270), (1400, 650), (820, 650)]
    for a, b in zip(front, back):
        draw.line((a, b), fill=rgba(CYAN, 175), width=3)
    draw.polygon(front, fill=rgba(CYAN, 16), outline=rgba(CYAN, 215), width=3)
    draw.polygon(back, fill=rgba(TEAL, 12), outline=rgba(TEAL, 160), width=3)
    for z in (0.25, 0.5, 0.75):
        y = int(380 + 380 * z)
        draw.line((660, y, 1240, y), fill=rgba(CYAN, 74), width=2)
        draw.line((820, y - 110, 1400, y - 110), fill=rgba(TEAL, 55), width=2)
    composite_model(canvas, optimized=False, x=575, y=160, scale=0.72, tint=CYAN)
    for x in (720, 960, 1200):
        draw.ellipse((x - 28, 740, x + 28, 770), fill=rgba((12, 38, 50), 230), outline=rgba(GREEN, 160), width=2)
    return canvas


def stage_topology() -> Image.Image:
    canvas = make_gradient((8, 21, 34), (4, 10, 21))
    add_light(canvas, (960, 520), 420, ORANGE, 75)
    add_light(canvas, (680, 700), 290, TEAL, 80)
    particles(canvas, 13, count=170, alpha=120)
    draw = ImageDraw.Draw(canvas)
    grid(canvas, alpha=22, step=82, offset=24)
    composite_model(canvas, optimized=True, x=620, y=110, scale=0.91, tint=ORANGE)
    for i, (x, y, w, color) in enumerate(
        [(310, 820, 270, TEAL), (540, 860, 370, CYAN), (1000, 858, 430, ORANGE), (1430, 820, 220, GREEN)]
    ):
        draw.rounded_rectangle((x, y, x + w, y + 8), radius=4, fill=rgba(color, 135 - i * 14))
        for dot in range(10 + i * 4):
            px = x + 15 + ((dot * 37 + i * 29) % max(1, w - 30))
            py = y - 12 - ((dot * 17 + i * 13) % 64)
            draw.ellipse((px, py, px + 4, py + 4), fill=rgba(color, 120))
    return canvas


def stage_validation() -> Image.Image:
    canvas = ocean_background()
    add_light(canvas, (470, 300), 260, BLUE, 70)
    add_light(canvas, (1460, 630), 370, GREEN, 90)
    particles(canvas, 21, count=125, alpha=115)
    draw = ImageDraw.Draw(canvas)
    composite_model(canvas, optimized=True, x=470, y=135, scale=0.75, tint=TEAL)
    for i, color in enumerate((CYAN, TEAL, ORANGE, GREEN)):
        y = 240 + i * 145
        path_line(draw, [(980, 520), (1180, y), (1590, y)], color=color, width=4, alpha=165)
        for j in range(5):
            x = 1200 + j * 76
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=rgba(color, 190))
        points = []
        for j in range(10):
            x = 1210 + j * 35
            yy = y + int(math.sin(j * 1.3 + i) * (22 + i * 5))
            points.append((x, yy))
        draw.line(points, fill=rgba(color, 215), width=3)
    return canvas


def stage_replan() -> Image.Image:
    canvas = make_gradient((20, 17, 31), (5, 10, 22))
    add_light(canvas, (960, 500), 400, RED, 80)
    add_light(canvas, (530, 700), 250, TEAL, 75)
    particles(canvas, 34, count=155, alpha=120)
    draw = ImageDraw.Draw(canvas)
    composite_model(canvas, optimized=True, x=635, y=140, scale=0.82, tint=RED)
    center = (960, 540)
    for radius, color, alpha in [(360, RED, 130), (285, ORANGE, 120), (210, TEAL, 150)]:
        draw.arc((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), 35, 315, fill=rgba(color, alpha), width=5)
    path_line(draw, [(300, 260), (620, 260), (760, 390)], color=RED, width=5, alpha=200)
    draw.line((760, 390, 805, 435), fill=rgba(RED, 220), width=6)
    draw.line((805, 390, 760, 435), fill=rgba(RED, 220), width=6)
    path_line(draw, [(1180, 670), (1420, 790), (1640, 790), (1640, 610)], color=TEAL, width=5, alpha=200)
    node(draw, 300, 260, radius=20, color=RED)
    node(draw, 1640, 610, radius=20, color=TEAL)
    return canvas


def stage_review() -> Image.Image:
    canvas = make_gradient((6, 25, 38), (3, 12, 23))
    add_light(canvas, (960, 540), 430, GREEN, 105)
    particles(canvas, 55, count=190, alpha=125)
    draw = ImageDraw.Draw(canvas)
    center = (960, 540)
    points = []
    for i in range(5):
        angle = -math.pi / 2 + i * 2 * math.pi / 5
        points.append((center[0] + math.cos(angle) * 250, center[1] + math.sin(angle) * 250))
    for level in (0.42, 0.68, 0.92):
        ring = []
        for i in range(5):
            angle = -math.pi / 2 + i * 2 * math.pi / 5
            ring.append((center[0] + math.cos(angle) * 250 * level, center[1] + math.sin(angle) * 250 * level))
        ring.append(ring[0])
        draw.line(ring, fill=rgba(GREEN, 90), width=2)
    for point in points:
        draw.line((center, point), fill=rgba(GREEN, 90), width=2)
        node(draw, *point, radius=20, color=GREEN, fill_alpha=55)
    score = []
    for i, level in enumerate((0.72, 0.84, 0.64, 0.9, 0.78)):
        angle = -math.pi / 2 + i * 2 * math.pi / 5
        score.append((center[0] + math.cos(angle) * 250 * level, center[1] + math.sin(angle) * 250 * level))
    score.append(score[0])
    draw.polygon(score, fill=rgba(GREEN, 45), outline=rgba(TEAL, 230))
    for radius in (310, 350):
        draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline=rgba(CYAN, 125), width=3)
    composite_model(canvas, optimized=True, x=650, y=140, scale=0.76, tint=GREEN)
    return canvas


def stage_deliverable() -> Image.Image:
    canvas = ocean_background(dark=False)
    canvas = ImageEnhance.Color(canvas).enhance(0.85)
    canvas = ImageEnhance.Contrast(canvas).enhance(1.06)
    add_light(canvas, (960, 310), 340, (250, 223, 150), 85)
    particles(canvas, 89, count=95, alpha=80)
    draw = ImageDraw.Draw(canvas)
    composite_model(canvas, optimized=True, x=630, y=110, scale=0.82, tint=(255, 211, 112))
    for width, alpha in ((60, 22), (34, 40), (12, 100)):
        draw.arc((560 - width, 650 - width, 1360 + width, 1460 + width), 205, 335, fill=rgba((255, 229, 160), alpha), width=max(2, width // 5))
    draw.line((960, 730, 960, 1060), fill=rgba((255, 236, 180), 105), width=4)
    return canvas


def build_stage(kind: str) -> Image.Image:
    return {
        "requirements": stage_requirements,
        "orchestration": stage_orchestration,
        "domain": stage_domain,
        "topology": stage_topology,
        "validation": stage_validation,
        "replan": stage_replan,
        "review": stage_review,
        "deliverable": stage_deliverable,
    }[kind]()


def animate(image: Image.Image, t: float, stage_index: int) -> Image.Image:
    """Add restrained camera drift so each scroll segment has internal life."""
    zoom = 1.0 + 0.018 * math.sin(t * math.pi)
    drift_x = int(math.sin(t * math.pi * 1.4 + stage_index) * 10)
    drift_y = int(math.cos(t * math.pi * 1.1 + stage_index) * 7)
    scaled = image.resize((int(W * zoom), int(H * zoom)), Image.Resampling.BICUBIC)
    left = max(0, (scaled.width - W) // 2 - drift_x)
    top = max(0, (scaled.height - H) // 2 - drift_y)
    return scaled.crop((left, top, left + W, top + H)).convert("RGB")


def encode(stages: list[Image.Image], output: Path):
    ff = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ff,
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "pipe:0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-g",
        "1",
        "-keyint_min",
        "1",
        "-sc_threshold",
        "0",
        "-bf",
        "0",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-an",
        str(output),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    frame_count = len(stages) * HOLD + (len(stages) - 1) * XFADE
    index = 0
    for stage_index, current in enumerate(stages):
        for hold_index in range(HOLD):
            frame = animate(current, hold_index / max(1, HOLD - 1), stage_index)
            proc.stdin.write(frame.tobytes())
            if index % 80 == 0:
                print(f"encoded {index}/{frame_count}", flush=True)
            index += 1
        if stage_index < len(stages) - 1:
            following = stages[stage_index + 1]
            for fade_index in range(XFADE):
                a = (fade_index + 1) / (XFADE + 1)
                frame = Image.blend(
                    animate(current, 1.0, stage_index),
                    animate(following, 0.0, stage_index + 1),
                    a,
                )
                proc.stdin.write(frame.tobytes())
                if index % 80 == 0:
                    print(f"encoded {index}/{frame_count}", flush=True)
                index += 1
    proc.stdin.close()
    stderr = proc.stderr.read().decode("utf-8", errors="replace")
    code = proc.wait()
    if code:
        raise RuntimeError(stderr[-3000:])


def main():
    source_keyframes = OM / "source" / "keyframes_scroll"
    final = OM / "final"
    final_keyframes = final / "keyframes_scroll"
    pilot = OM / "pilot"
    build = OM / "build"
    source_keyframes.mkdir(parents=True, exist_ok=True)
    final_keyframes.mkdir(parents=True, exist_ok=True)
    pilot.mkdir(parents=True, exist_ok=True)
    build.mkdir(parents=True, exist_ok=True)

    stages = [build_stage(stage["kind"]) for stage in STAGES]
    for stage, image in zip(STAGES, stages):
        path = source_keyframes / f"{stage['id']}.png"
        image.save(path, "PNG", optimize=True)
        image.save(final_keyframes / f"{stage['id']}.png", "PNG", optimize=True)
        print("composed", stage["id"], path)

    frame_count = len(stages) * HOLD + (len(stages) - 1) * XFADE

    master = pilot / "source_master_scroll.mp4"
    desktop = final / "desktop_scroll.mp4"
    mobile = final / "mobile_scroll.mp4"
    poster = final / "poster_scroll.png"
    poster.write_bytes(source_keyframes.joinpath("K0.png").read_bytes())
    encode(stages, master)
    desktop.write_bytes(master.read_bytes())

    ff = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run(
        [
            ff,
            "-y",
            "-i",
            str(master),
            "-vf",
            "scale=960:-2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "1",
            "-keyint_min",
            "1",
            "-sc_threshold",
            "0",
            "-bf",
            "0",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-an",
            str(mobile),
        ],
        check=True,
    )

    duration = frame_count / FPS
    states = []
    cursor = 0
    for index, stage in enumerate(STAGES):
        states.append(
            {
                "id": stage["id"],
                "start": cursor / FPS,
                "hold": (cursor + HOLD - 1) / FPS,
                "title": stage["title"],
                "caption": stage["caption"],
            }
        )
        cursor += HOLD + (XFADE if index < len(STAGES) - 1 else 0)

    segments = []
    cursor = 0
    for index in range(len(STAGES) - 1):
        hold_end = cursor + HOLD - 1
        segments.append(
            {
                "id": f"s{index + 1:02d}",
                "from": STAGES[index]["id"],
                "to": STAGES[index + 1]["id"],
                "start": cursor / FPS,
                "hold": hold_end / FPS,
                "endExclusive": (hold_end + 1) / FPS,
                "curve": {"type": "constant", "rate": 1},
            }
        )
        cursor += HOLD + XFADE

    timeline = {
        "schemaVersion": 1,
        "fps": FPS,
        "frameDuration": 1 / FPS,
        "frameCount": frame_count,
        "duration": duration,
        "initialState": "K0",
        "states": states,
        "segments": segments,
        "media": {
            "desktop": "./oil_motion_ai_engineer/final/desktop_scroll.mp4",
            "mobile": "./oil_motion_ai_engineer/final/mobile_scroll.mp4",
            "poster": "./oil_motion_ai_engineer/final/poster_scroll.png",
        },
        "style": "paper-grounded-cinematic-engineering-scroll",
        "sourceAssets": [
            "./docs/assets/ai_sea.png",
            "./docs/assets/ai.png",
            "./docs/assets/ai_2.png",
        ],
    }
    (build / "timeline.json").write_text(json.dumps(timeline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", desktop, desktop.stat().st_size)
    print("wrote", mobile, mobile.stat().st_size)
    print("timeline frames", frame_count, "duration", round(duration, 2))


if __name__ == "__main__":
    main()
