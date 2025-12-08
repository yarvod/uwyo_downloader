#!/usr/bin/env python3
"""
Fetch and assemble a low-zoom OpenStreetMap base layer into a single PNG.
Zoom level 2 (4x4 tiles) -> 1024x1024 image.
"""
from pathlib import Path

import httpx
from io import BytesIO
from PIL import Image

OUT_PATH = Path("assets/maps/world-map.png")
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
Z = 2  # 4x4 tiles
TILE_SIZE = 256


def fetch_tile(client: httpx.Client, z: int, x: int, y: int) -> Image.Image:
    url = TILE_URL.format(z=z, x=x, y=y)
    resp = client.get(url, timeout=20.0)
    resp.raise_for_status()
    img = Image.open(BytesIO(resp.content)).convert("RGBA")
    return img


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    composite = Image.new("RGBA", (TILE_SIZE * 2**Z, TILE_SIZE * 2**Z))
    with httpx.Client(headers={"User-Agent": "uwyo-sounding-gui/tiles"}) as client:
        for x in range(2**Z):
            for y in range(2**Z):
                tile = fetch_tile(client, Z, x, y)
                composite.paste(tile, (x * TILE_SIZE, y * TILE_SIZE))
                print(f"fetched z{Z}/{x}/{y}")
    composite.save(OUT_PATH, format="PNG")
    print(f"saved {OUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
