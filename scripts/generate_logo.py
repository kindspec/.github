"""Render the kindspec mark to profile/assets/kindspec-logo.png."""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
BG = "#16181D"
FG = "#F2F0E8"
ACCENT = "#E8B04B"
OUTPUT = Path(__file__).resolve().parent.parent / "profile" / "assets" / "kindspec-logo.png"


def polygon(draw, pts, fill):
    draw.polygon([(int(x), int(y)) for x, y in pts], fill=fill)


def render_logo(size=SIZE, bg=BG, fg=FG, accent=ACCENT):
    img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)

    s = size / 1024.0

    def P(points):
        return [(x * s, y * s) for x, y in points]

    # Four bracket pieces around a central negative-space square.
    pieces = [
        [(232, 224), (456, 224), (456, 328), (336, 328), (336, 456), (232, 456)],
        [(568, 224), (792, 224), (792, 456), (688, 456), (688, 328), (568, 328)],
        [(232, 568), (336, 568), (336, 696), (456, 696), (456, 800), (232, 800)],
        [(688, 568), (792, 568), (792, 800), (568, 800), (568, 696), (688, 696)],
    ]
    for piece in pieces:
        polygon(draw, P(piece), fg)

    # Central diamond: the shared spec kernel.
    c, h = 512, 130
    polygon(draw, P([(c, c - h), (c + h, c), (c, c + h), (c - h, c)]), accent)

    return img


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    render_logo().save(OUTPUT, optimize=True)
    print(f"Wrote {OUTPUT}")
