#!/usr/bin/env python3
"""Compose project paper/brand assets into 16:9 storyboard frames and bake scrub MP4."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FS = ROOT / "frontend_static"
OM = FS / "oil_motion_ai_engineer"
DOCS = ROOT / "docs" / "assets"
OIL = FS / "assets" / "oil-intro"
BRAND = FS / "assets"

W, H = 1920, 1080
FPS = 30
HOLD = 36
XFADE = 14

# Product CSS tokens
BG0 = (247, 248, 251)
BG1 = (255, 255, 255)
SLATE = (15, 23, 42)
MUTED = (107, 114, 128)
ACCENT = (37, 99, 235)
ACCENT2 = (16, 185, 129)
CARD = (255, 255, 255)
BORDER = (226, 232, 240)

STAGES = [
    {
        "id": "K0",
        "title": "Human Engineer",
        "caption": "多工具碎片化 · 人工反复试错",
        "src": DOCS / "human engineer.png",
        "fallback": OIL / "k0-human.png",
    },
    {
        "id": "K1",
        "title": "Verification-closed",
        "caption": "LLM 编排确定性工程后端 · 验证闭环",
        "src": DOCS / "f1-2.png",
        "fallback": OIL / "k1-loop.png",
    },
    {
        "id": "K2",
        "title": "End-to-end pipeline",
        "caption": "需求 → 设计域 → BESO → 尺寸 → 评审交付",
        "src": DOCS / "all.png",
        "fallback": OIL / "k2-pipeline.png",
    },
    {
        "id": "K3",
        "title": "Design domain",
        "caption": "几何边界 · 可优化设计空间 · 网格/载荷",
        "src": OIL / "k3-cad.png",
        "fallback": DOCS / "file_flow.png",
    },
    {
        "id": "K4",
        "title": "The AI Engineer",
        "caption": "失败分层重规划 · 闭环可恢复",
        "src": DOCS / "ai engineer.png",
        "fallback": OIL / "k4-ai.png",
    },
    {
        "id": "K5",
        "title": "Certifiable gate",
        "caption": "Automated Reviewer · S≥85 · AIP 外校准",
        "src": OIL / "k5-aip.png",
        "fallback": DOCS / "file_flow.png",
    },
    {
        "id": "K6",
        "title": "Enter chat",
        "caption": "滚至底部，进入大模型工作台",
        "src": OIL / "k6-sea.png",
        "fallback": DOCS / "all.png",
    },
]


def font(size: int, bold: bool = False):
    # Prefer CJK-capable fonts so Chinese captions render (not tofu □).
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttf" if bold else "C:/Windows/Fonts/msyh.ttf",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for path in candidates:
        if not Path(path).exists():
            continue
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def open_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def cover(im: Image.Image, box: tuple[int, int]) -> Image.Image:
    tw, th = box
    w, h = im.size
    scale = max(tw / w, th / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return im.crop((left, top, left + tw, top + th))


def contain(im: Image.Image, box: tuple[int, int], pad: float = 0.92) -> Image.Image:
    tw, th = int(box[0] * pad), int(box[1] * pad)
    w, h = im.size
    scale = min(tw / w, th / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    return im.resize((nw, nh), Image.Resampling.LANCZOS)


def rounded_card(size: tuple[int, int], radius: int = 28) -> Image.Image:
    card = Image.new("RGBA", size, (0, 0, 0, 0))
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    body = Image.new("RGBA", size, (*CARD, 255))
    card.paste(body, (0, 0), mask)
    # soft border
    border = Image.new("RGBA", size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(border)
    bd.rounded_rectangle((1, 1, size[0] - 2, size[1] - 2), radius=radius, outline=(*BORDER, 255), width=2)
    return Image.alpha_composite(card, border)


def make_background() -> Image.Image:
    base = Image.new("RGB", (W, H), BG0)
    # Match landing radial washes (blue + emerald)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for r, color, alpha, cx, cy in [
        (900, ACCENT, 28, int(W * 0.15), int(H * 0.12)),
        (860, ACCENT2, 22, int(W * 0.88), int(H * 0.18)),
        (700, (14, 165, 233), 16, int(W * 0.55), int(H * 0.92)),
    ]:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*color, alpha))
        overlay = Image.alpha_composite(overlay, layer)
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGBA")


def paste_shadow(canvas: Image.Image, content: Image.Image, xy: tuple[int, int], blur: int = 24):
    shadow = Image.new("RGBA", (content.width + blur * 4, content.height + blur * 4), (0, 0, 0, 0))
    sh = Image.new("RGBA", content.size, (15, 23, 42, 55))
    shadow.paste(sh, (blur * 2, blur * 2), content.split()[-1] if content.mode == "RGBA" else None)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow, (xy[0] - blur * 2, xy[1] - blur * 2 + 8))
    canvas.alpha_composite(content, xy)


def compose_stage(stage: dict) -> Image.Image:
    canvas = make_background()
    src = stage["src"] if Path(stage["src"]).exists() else stage["fallback"]
    fig = open_rgba(src)

    # Brand mark top-left
    mark_path = BRAND / "beso-agent-mark.png"
    if mark_path.exists():
        mark = open_rgba(mark_path).resize((56, 56), Image.Resampling.LANCZOS)
        canvas.alpha_composite(mark, (48, 36))
    draw = ImageDraw.Draw(canvas)
    draw.text((118, 42), "The AI Engineer", font=font(28, True), fill=(*SLATE, 255))
    draw.text((118, 78), "Closed-loop · Certifiable FOWT design", font=font(18), fill=(*MUTED, 255))

    # Progress dots (product-like)
    n = len(STAGES)
    idx = next(i for i, s in enumerate(STAGES) if s["id"] == stage["id"])
    for i in range(n):
        x = W - 48 - (n - i) * 18
        color = ACCENT if i <= idx else (203, 213, 225)
        draw.ellipse((x, 52, x + 10, 62), fill=(*color, 255))

    # Main figure card
    card_w, card_h = 1680, 780
    card = rounded_card((card_w, card_h), radius=32)
    # Inner figure area
    inner = contain(fig, (card_w - 64, card_h - 64), pad=1.0)
    # Prefer contain for diagrams; cover for tall sea photo framed in card
    if fig.height > fig.width * 1.15:
        # portrait: cover center of a soft panel
        panel = Image.new("RGBA", (card_w - 48, card_h - 48), (241, 245, 249, 255))
        covered = cover(fig, (panel.width, panel.height))
        panel.alpha_composite(covered.convert("RGBA"))
        card.alpha_composite(panel, (24, 24))
    else:
        ix = (card_w - inner.width) // 2
        iy = (card_h - inner.height) // 2
        card.alpha_composite(inner, (ix, iy))

    paste_shadow(canvas, card, ((W - card_w) // 2, 120))

    # Caption dock (landing composer-like)
    dock_h = 118
    dock = rounded_card((1680, dock_h), radius=24)
    dd = ImageDraw.Draw(dock)
    dd.text((28, 22), stage["title"], font=font(30, True), fill=(*SLATE, 255))
    dd.text((28, 64), stage["caption"], font=font(22), fill=(*MUTED, 255))
    # accent chip
    dd.rounded_rectangle((dock.width - 150, 36, dock.width - 28, 78), radius=999, fill=(*ACCENT, 255))
    dd.text((dock.width - 128, 44), f"{idx + 1}/{n}", font=font(20, True), fill=(255, 255, 255, 255))
    paste_shadow(canvas, dock, ((W - 1680) // 2, H - dock_h - 36), blur=18)

    return canvas.convert("RGB")


def ken_burns(im: Image.Image, t: float, zoom_end: float = 1.06) -> Image.Image:
    """Subtle scale for motion between holds (t in 0..1)."""
    z = 1.0 + (zoom_end - 1.0) * t
    nw, nh = int(W * z), int(H * z)
    scaled = im.resize((nw, nh), Image.Resampling.BILINEAR)
    left = (nw - W) // 2
    top = (nh - H) // 2
    return scaled.crop((left, top, left + W, top + H))


def main() -> None:
    out_kf = OM / "source" / "keyframes_project"
    out_kf.mkdir(parents=True, exist_ok=True)
    final = OM / "final"
    final.mkdir(parents=True, exist_ok=True)
    pilot = OM / "pilot"
    pilot.mkdir(parents=True, exist_ok=True)

    stills = []
    for stage in STAGES:
        frame = compose_stage(stage)
        path = out_kf / f"{stage['id']}.png"
        frame.save(path, "PNG", optimize=True)
        (final / "keyframes").mkdir(exist_ok=True)
        frame.save(final / "keyframes" / f"{stage['id']}.png", "PNG", optimize=True)
        stills.append(frame)
        print("composed", stage["id"], path)

    # Build frame list with hold + crossfade + ken burns
    frames: list[Image.Image] = []
    for i, still in enumerate(stills):
        for h in range(HOLD):
            frames.append(ken_burns(still, h / max(1, HOLD - 1) * 0.35))
        if i < len(stills) - 1:
            nxt = stills[i + 1]
            for x in range(XFADE):
                a = (x + 1) / (XFADE + 1)
                blended = Image.blend(
                    ken_burns(still, 0.35 + 0.2 * a),
                    ken_burns(nxt, a * 0.2),
                    a,
                )
                frames.append(blended)

    print("total_frames", len(frames))

    # Stream to ffmpeg
    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    master = pilot / "source_master_project.mp4"
    desktop = final / "desktop.mp4"
    mobile = final / "mobile.mp4"
    poster = final / "poster.png"
    stills[0].save(poster, "PNG")

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
        str(master),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    for i, fr in enumerate(frames):
        proc.stdin.write(fr.tobytes())
        if i % 40 == 0:
            print(f"pushed {i}/{len(frames)}", flush=True)
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="replace")
    code = proc.wait()
    if code != 0:
        raise RuntimeError(err[-2000:])

    # copy desktop + scale mobile
    desktop.write_bytes(master.read_bytes())
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

    # timeline from bake structure
    duration = len(frames) / FPS
    states = []
    cursor = 0
    for i, stage in enumerate(STAGES):
        hold_end = cursor + HOLD - 1
        states.append(
            {
                "id": stage["id"],
                "hold": hold_end / FPS,
                "title": stage["title"],
                "caption": stage["caption"],
            }
        )
        if i < len(STAGES) - 1:
            cursor = cursor + HOLD + XFADE
        else:
            cursor = hold_end + 1

    segments = []
    cursor = 0
    for i in range(len(STAGES) - 1):
        start_f = cursor
        hold_f = cursor + HOLD - 1
        segments.append(
            {
                "id": f"s{i+1:02d}",
                "from": STAGES[i]["id"],
                "to": STAGES[i + 1]["id"],
                "start": start_f / FPS,
                "hold": hold_f / FPS,
                "endExclusive": (hold_f + 1) / FPS,
                "curve": {"type": "constant", "rate": 1},
            }
        )
        cursor = cursor + HOLD + XFADE

    timeline = {
        "schemaVersion": 1,
        "fps": FPS,
        "frameDuration": 1 / FPS,
        "frameCount": len(frames),
        "duration": duration,
        "initialState": "K0",
        "states": states,
        "segments": segments,
        "media": {
            "desktop": "./oil_motion_ai_engineer/final/desktop.mp4",
            "mobile": "./oil_motion_ai_engineer/final/mobile.mp4",
            "poster": "./oil_motion_ai_engineer/final/poster.png",
        },
        "style": "project-assets",
        "sources": [str(s["src"]) for s in STAGES],
    }
    (OM / "build" / "timeline.json").write_text(
        json.dumps(timeline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("wrote", desktop, desktop.stat().st_size)
    print("wrote", mobile, mobile.stat().st_size)
    print("timeline frames", len(frames), "duration", duration)


if __name__ == "__main__":
    main()
