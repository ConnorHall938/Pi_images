#!/usr/bin/env python3
"""Convert a PNG into the TGA the rpi-splash-screen layer expects.

The layer needs: TGA, 24-bit, uncompressed, at most 1920x1080, at most
224 colours. The picture is flattened onto black, scaled down to fit
(never up), and centred on a 1920x1080 black canvas.

Usage: png2splash.py <input.png> <output.tga>
"""
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("error: Pillow is required (sudo apt install python3-pil)")

WIDTH, HEIGHT, MAX_COLOURS = 1920, 1080, 224


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dst = sys.argv[1], sys.argv[2]

    try:
        img = Image.open(src).convert("RGBA")
    except OSError as err:
        sys.exit(f"error: cannot read {src}: {err}")

    flat = Image.new("RGBA", img.size, (0, 0, 0, 255))
    flat.alpha_composite(img)
    logo = flat.convert("RGB")
    logo.thumbnail((WIDTH, HEIGHT))

    canvas = Image.new("RGB", (WIDTH, HEIGHT), "black")
    canvas.paste(logo, ((WIDTH - logo.width) // 2, (HEIGHT - logo.height) // 2))
    canvas.quantize(MAX_COLOURS).convert("RGB").save(dst)
    print(f"{src} -> {dst} ({WIDTH}x{HEIGHT}, <= {MAX_COLOURS} colours)")


if __name__ == "__main__":
    main()
