from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


OUT_DIR = Path(__file__).resolve().parent
PNG_PATH = OUT_DIR / "梁雪柏_商务名片.png"
PDF_PATH = OUT_DIR / "梁雪柏_商务名片.pdf"

WIDTH = 1200
HEIGHT = 720

FONT_REGULAR = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_LIGHT = r"C:\Windows\Fonts\msyhl.ttc"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def vertical_gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), top)
    pixels = image.load()
    for y in range(HEIGHT):
        ratio = y / max(HEIGHT - 1, 1)
        color = tuple(round(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        for x in range(WIDTH):
            pixels[x, y] = color
    return image


def rounded_line(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    width: int,
) -> None:
    draw.line(xy, fill=fill, width=width)
    radius = width // 2
    x1, y1, x2, y2 = xy
    draw.ellipse((x1 - radius, y1 - radius, x1 + radius, y1 + radius), fill=fill)
    draw.ellipse((x2 - radius, y2 - radius, x2 + radius, y2 + radius), fill=fill)


def draw_logo(draw: ImageDraw.ImageDraw) -> None:
    x, y, size = 72, 64, 86
    draw.rounded_rectangle(
        (x, y, x + size, y + size),
        radius=24,
        fill=(35, 151, 203),
        outline=(110, 220, 236),
        width=2,
    )
    # 抽象“云”图形：三段圆弧与水平基线。
    cloud = (239, 251, 255)
    draw.arc((x + 18, y + 29, x + 50, y + 61), 180, 330, fill=cloud, width=7)
    draw.arc((x + 34, y + 18, x + 68, y + 58), 205, 345, fill=cloud, width=7)
    draw.arc((x + 52, y + 32, x + 75, y + 59), 210, 345, fill=cloud, width=7)
    rounded_line(draw, (x + 25, y + 59, x + 69, y + 59), cloud, 7)


def create_png() -> None:
    image = vertical_gradient((5, 19, 36), (9, 47, 75))
    draw = ImageDraw.Draw(image)

    # 右侧柔和光晕与几何线条。
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((790, -240, 1370, 340), fill=(24, 183, 210, 34))
    glow_draw.ellipse((-240, 450, 260, 950), fill=(32, 129, 185, 28))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    draw = ImageDraw.Draw(image)

    draw.polygon(
        [(930, 0), (1200, 0), (1200, 720), (1070, 720)],
        fill=(255, 255, 255, 10),
    )
    draw.line((945, 0, 1090, 720), fill=(91, 211, 228, 60), width=2)

    draw_logo(draw)
    draw.text(
        (184, 70),
        "陕西依云信息技术有限公司",
        font=font(FONT_BOLD, 42),
        fill=(246, 250, 253),
    )
    draw.text(
        (186, 126),
        "SHAANXI YIYUN INFORMATION TECHNOLOGY",
        font=font(FONT_REGULAR, 17),
        fill=(126, 181, 204),
    )
    rounded_line(draw, (74, 187, 1126, 187), (48, 149, 190), 3)

    draw.text((76, 254), "梁雪柏", font=font(FONT_BOLD, 76), fill=(255, 255, 255))
    draw.rounded_rectangle(
        (78, 355, 275, 405),
        radius=25,
        fill=(28, 143, 190),
        outline=(86, 211, 229),
        width=2,
    )
    role = "客户经理"
    role_font = font(FONT_REGULAR, 28)
    role_box = draw.textbbox((0, 0), role, font=role_font)
    role_width = role_box[2] - role_box[0]
    draw.text((176 - role_width / 2, 362), role, font=role_font, fill=(247, 252, 255))

    # 中央分隔线。
    draw.line((488, 255, 488, 562), fill=(84, 145, 169), width=2)
    draw.ellipse((480, 249, 496, 265), fill=(76, 202, 221))

    label_font = font(FONT_REGULAR, 22)
    value_font = font(FONT_BOLD, 34)
    muted = (132, 183, 203)
    white = (247, 251, 253)

    draw.ellipse((558, 274, 608, 324), fill=(25, 139, 187))
    phone_icon = font(FONT_BOLD, 23)
    draw.text((574, 282), "T", font=phone_icon, fill=white)
    draw.text((632, 269), "电话 / MOBILE", font=label_font, fill=muted)
    draw.text((632, 305), "199 4636 0864", font=value_font, fill=white)

    draw.ellipse((558, 407, 608, 457), fill=(29, 171, 126))
    draw.text((570, 415), "W", font=phone_icon, fill=white)
    draw.text((632, 402), "微信 / WECHAT", font=label_font, fill=muted)
    draw.text((632, 438), "dbalxb", font=value_font, fill=white)

    # 底部视觉收口。
    rounded_line(draw, (76, 615, 250, 615), (70, 207, 225), 6)
    draw.text(
        (76, 637),
        "连接需求 · 提供专业的信息技术服务",
        font=font(FONT_LIGHT, 21),
        fill=(159, 196, 211),
    )

    image.convert("RGB").save(PNG_PATH, quality=98, dpi=(338, 338))


def create_pdf() -> None:
    page_size = landscape((54 * mm, 90 * mm))
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=page_size)
    pdf.setTitle("梁雪柏 - 商务名片")
    pdf.setAuthor("陕西依云信息技术有限公司")
    pdf.drawImage(
        str(PNG_PATH),
        0,
        0,
        width=90 * mm,
        height=54 * mm,
        preserveAspectRatio=True,
        mask="auto",
    )
    pdf.showPage()
    pdf.save()


if __name__ == "__main__":
    create_png()
    create_pdf()
    print(PNG_PATH)
    print(PDF_PATH)
