#!/usr/bin/env python3
"""
Generate application icons (PNG) in common sizes using Pillow.
"""
from pathlib import Path
from typing import Iterable
import subprocess
import sys

from PIL import Image, ImageDraw


SIZES: Iterable[int] = (64, 128, 256, 512, 1024)
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT_DIR = Path("assets/icons")


def lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw_gradient_bg(draw: ImageDraw.ImageDraw, size: int) -> None:
    top = (12, 18, 40)  # deep navy
    bottom = (35, 134, 173)  # teal-blue
    for y in range(size):
        t = y / max(size - 1, 1)
        color = lerp(top, bottom, t)
        draw.line([(0, y), (size, y)], fill=color)


def draw_cloud(draw: ImageDraw.ImageDraw, size: int) -> None:
    base_y = int(size * 0.62)
    width = int(size * 0.55)
    height = int(size * 0.22)
    left = int(size * 0.2)
    color = (236, 244, 255, 235)
    shadow = (8, 20, 34, 140)
    shadow_offset = int(size * 0.015)

    # shadow
    draw.rounded_rectangle(
        [left + shadow_offset, base_y + shadow_offset, left + width + shadow_offset, base_y + height + shadow_offset],
        radius=int(height * 0.35),
        fill=shadow,
    )
    draw.rounded_rectangle(
        [left, base_y, left + width, base_y + height],
        radius=int(height * 0.35),
        fill=color,
    )
    # bubbles
    r1 = int(size * 0.12)
    r2 = int(size * 0.10)
    r3 = int(size * 0.08)
    draw.ellipse([left + r1, base_y - r1, left + r1 * 3, base_y + r1], fill=color)
    draw.ellipse([left + r1 * 2, base_y - r2, left + r1 * 2 + r2 * 2, base_y + r2], fill=color)
    draw.ellipse([left + r1 * 3, base_y - r3, left + r1 * 3 + r3 * 2, base_y + r3], fill=color)


def draw_balloon(draw: ImageDraw.ImageDraw, size: int) -> None:
    cx = int(size * 0.7)
    cy = int(size * 0.38)
    r = int(size * 0.12)
    balloon_color = (255, 217, 102, 240)
    outline = (255, 255, 255, 220)
    string_color = (220, 235, 255, 220)

    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=balloon_color, outline=outline, width=max(1, size // 96))
    # string
    draw.line(
        [(cx, cy + r), (cx - int(size * 0.07), cy + int(size * 0.24)), (cx - int(size * 0.22), cy + int(size * 0.38))],
        fill=string_color,
        width=max(2, size // 128),
        joint="curve",
    )
    # small box
    box_w = int(size * 0.08)
    box_h = int(size * 0.05)
    draw.rounded_rectangle(
        [cx - box_w // 2, cy + int(size * 0.37), cx + box_w // 2, cy + int(size * 0.37) + box_h],
        radius=box_h // 2,
        fill=outline,
    )


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, size)
    draw_cloud(draw, size)
    draw_balloon(draw, size)
    return img


def build_ico(master: Image.Image, out_path: Path) -> None:
    master.save(out_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print(f"saved {out_path}")


def build_icns(out_dir: Path, out_path: Path) -> None:
    iconset = out_dir / "app.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for sz in sizes:
        base = make_icon(sz)
        base.save(iconset / f"icon_{sz}x{sz}.png", format="PNG")
        base.resize((sz * 2, sz * 2)).save(iconset / f"icon_{sz}x{sz}@2x.png", format="PNG")
    try:
        subprocess.run(
            ["iconutil", "-c", "icns", iconset, "-o", out_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print(f"saved {out_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"iconutil failed: {exc}. icns not generated.", file=sys.stderr)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    master = None
    for size in SIZES:
        icon = make_icon(size)
        out_path = OUT_DIR / f"icon-{size}.png"
        icon.save(out_path, format="PNG")
        print(f"saved {out_path}")
        if size == max(SIZES):
            master = icon

    if master:
        build_ico(master, OUT_DIR / "app.ico")
        build_icns(OUT_DIR, OUT_DIR / "app.icns")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
