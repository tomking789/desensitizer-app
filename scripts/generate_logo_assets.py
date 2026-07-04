from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


CANVAS = 1024


def _lerp(start: int, end: int, ratio: float) -> int:
    return round(start + (end - start) * ratio)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _gradient_square(size: int, top: str, bottom: str) -> Image.Image:
    top_rgb = _hex_to_rgb(top)
    bottom_rgb = _hex_to_rgb(bottom)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(size):
        ratio = y / max(size - 1, 1)
        color = tuple(_lerp(top_rgb[i], bottom_rgb[i], ratio) for i in range(3)) + (255,)
        for x in range(size):
            pixels[x, y] = color
    return image


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _draw_logo(size: int = CANVAS) -> Image.Image:
    scale = size / CANVAS

    def s(value: float) -> int:
        return round(value * scale)

    logo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    background = _gradient_square(size, "#172554", "#0f766e")
    logo.alpha_composite(background, (0, 0))
    logo.putalpha(_rounded_mask(size, s(210)))

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((s(180), s(135), s(850), s(790)), fill=(45, 212, 191, 58))
    glow_draw.ellipse((s(250), s(85), s(760), s(555)), fill=(96, 165, 250, 42))
    glow = glow.filter(ImageFilter.GaussianBlur(s(52)))
    logo.alpha_composite(glow)

    draw = ImageDraw.Draw(logo, "RGBA")

    shield = [
        (s(512), s(190)),
        (s(735), s(300)),
        (s(688), s(712)),
        (s(512), s(825)),
        (s(336), s(712)),
        (s(289), s(300)),
    ]
    draw.polygon(shield, fill=(255, 255, 255, 28))
    draw.line(shield + [shield[0]], fill=(229, 246, 255, 205), width=s(28), joint="curve")

    network_lines = [
        ((s(418), s(352)), (s(515), s(285))),
        ((s(515), s(285)), (s(626), s(354))),
        ((s(626), s(354)), (s(665), s(471))),
        ((s(665), s(471)), (s(548), s(548))),
        ((s(548), s(548)), (s(395), s(480))),
        ((s(395), s(480)), (s(418), s(352))),
        ((s(418), s(352)), (s(548), s(548))),
        ((s(626), s(354)), (s(395), s(480))),
    ]
    for start, end in network_lines:
        draw.line((start, end), fill=(178, 246, 241, 160), width=s(18))

    nodes = [
        (418, 352, 38),
        (515, 285, 34),
        (626, 354, 38),
        (665, 471, 32),
        (548, 548, 36),
        (395, 480, 34),
    ]
    for x, y, radius in nodes:
        draw.ellipse((s(x - radius), s(y - radius), s(x + radius), s(y + radius)), fill=(236, 254, 255, 232))
        draw.ellipse((s(x - radius / 2), s(y - radius / 2), s(x + radius / 2), s(y + radius / 2)), fill=(20, 184, 166, 255))

    bar_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(bar_shadow, "RGBA")
    shadow_draw.rounded_rectangle((s(282), s(542), s(742), s(680)), radius=s(62), fill=(0, 0, 0, 120))
    bar_shadow = bar_shadow.filter(ImageFilter.GaussianBlur(s(16)))
    logo.alpha_composite(bar_shadow)

    draw = ImageDraw.Draw(logo, "RGBA")
    draw.rounded_rectangle((s(272), s(520), s(752), s(655)), radius=s(58), fill=(12, 18, 30, 245))
    draw.rounded_rectangle((s(272), s(520), s(752), s(655)), radius=s(58), outline=(94, 234, 212, 230), width=s(16))
    draw.rounded_rectangle((s(336), s(568), s(508), s(608)), radius=s(18), fill=(148, 163, 184, 125))
    draw.rounded_rectangle((s(548), s(568), s(690), s(608)), radius=s(18), fill=(148, 163, 184, 125))
    draw.ellipse((s(488), s(566), s(530), s(608)), fill=(45, 212, 191, 255))

    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    highlight_draw = ImageDraw.Draw(highlight, "RGBA")
    highlight_draw.arc((s(250), s(175), s(775), s(700)), start=214, end=318, fill=(255, 255, 255, 90), width=s(20))
    logo.alpha_composite(highlight)
    return logo


def _write_svg(path: Path) -> None:
    path.write_text(
        """<svg width="1024" height="1024" viewBox="0 0 1024 1024" fill="none" xmlns="http://www.w3.org/2000/svg">
<rect width="1024" height="1024" rx="210" fill="url(#bg)"/>
<path d="M512 190L735 300L688 712L512 825L336 712L289 300L512 190Z" fill="white" fill-opacity=".11" stroke="#E5F6FF" stroke-width="28" stroke-linejoin="round"/>
<path d="M418 352L515 285L626 354L665 471L548 548L395 480L418 352ZM418 352L548 548M626 354L395 480" stroke="#B2F6F1" stroke-width="18" stroke-linecap="round"/>
<g fill="#ECFEFF">
<circle cx="418" cy="352" r="38"/><circle cx="515" cy="285" r="34"/><circle cx="626" cy="354" r="38"/><circle cx="665" cy="471" r="32"/><circle cx="548" cy="548" r="36"/><circle cx="395" cy="480" r="34"/>
</g>
<g fill="#14B8A6">
<circle cx="418" cy="352" r="19"/><circle cx="515" cy="285" r="17"/><circle cx="626" cy="354" r="19"/><circle cx="665" cy="471" r="16"/><circle cx="548" cy="548" r="18"/><circle cx="395" cy="480" r="17"/>
</g>
<rect x="272" y="520" width="480" height="135" rx="58" fill="#0C121E" stroke="#5EEAD4" stroke-width="16"/>
<rect x="336" y="568" width="172" height="40" rx="18" fill="#94A3B8" fill-opacity=".5"/>
<rect x="548" y="568" width="142" height="40" rx="18" fill="#94A3B8" fill-opacity=".5"/>
<circle cx="509" cy="587" r="21" fill="#2DD4BF"/>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1024" y2="1024" gradientUnits="userSpaceOnUse"><stop stop-color="#172554"/><stop offset="1" stop-color="#0F766E"/></linearGradient></defs>
</svg>
""",
        encoding="utf-8",
    )


def main() -> None:
    assets_dir = Path(__file__).resolve().parents[1] / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    logo = _draw_logo()
    logo.save(assets_dir / "app_logo_1024.png")
    logo.resize((256, 256), Image.Resampling.LANCZOS).save(assets_dir / "app_logo_256.png")
    logo.resize((64, 64), Image.Resampling.LANCZOS).save(assets_dir / "app_logo_64.png")
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    logo.save(assets_dir / "app_icon.ico", sizes=icon_sizes)
    _write_svg(assets_dir / "app_logo.svg")
    print(f"generated logo assets in {assets_dir}")


if __name__ == "__main__":
    main()
