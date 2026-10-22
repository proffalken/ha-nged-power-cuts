"""Draw the brand icon: a lightning bolt struck through, on a dark circle."""

from pathlib import Path

from PIL import Image, ImageDraw

BRAND = Path(__file__).parent.parent / "custom_components/nged_power_cuts/brand"


def draw(size: int) -> Image.Image:
    scale = 4  # draw big, then shrink for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, s - 1, s - 1), fill=(30, 41, 59, 255))
    bolt = [
        (0.56, 0.12),
        (0.28, 0.54),
        (0.48, 0.54),
        (0.42, 0.88),
        (0.72, 0.42),
        (0.52, 0.42),
        (0.60, 0.12),
    ]
    d.polygon([(x * s, y * s) for x, y in bolt], fill=(250, 204, 21, 255))
    w = round(0.075 * s)
    d.line(
        (0.22 * s, 0.22 * s, 0.78 * s, 0.78 * s), fill=(30, 41, 59, 255), width=w * 2
    )
    d.line((0.22 * s, 0.22 * s, 0.78 * s, 0.78 * s), fill=(239, 68, 68, 255), width=w)
    return img.resize((size, size), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    BRAND.mkdir(parents=True, exist_ok=True)
    draw(256).save(BRAND / "icon.png")
    draw(512).save(BRAND / "icon@2x.png")
