"""Final Smart Learning Lab CTA card."""

import os
from PIL import Image, ImageDraw
from moviepy.editor import ImageClip

from .config import VIDEO_SIZE, CTA_URL, END_CARD_DURATION
from .fonts import get_cta_latin_font
from .branding import prepare_round_logo

# ============================================================
# CTA FONT HELPER
# ============================================================

def get_cta_latin_font(size, bold=True):
    """
    Use a guaranteed Latin font for the English CTA card.

    The normal subtitle font helper prefers Devanagari fonts. Some
    Linux font combinations can render Latin glyphs as square boxes.
    The CTA is English-only, so use a dedicated Latin font here.
    """
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
            "DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
            "DejaVuSans.ttf",
        ]

    for font_path in candidates:
        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        except Exception:
            pass

    return get_unicode_font(size, bold=bold)


# ============================================================
# FINAL SMART LEARNING LAB LIKE / SUBSCRIBE PAGE
# ============================================================

def create_end_card(duration=END_CARD_DURATION):
    """
    Render the Smart Learning Lab CTA page as the final video frame.

    The supplied HTML page is a web page, so it cannot itself be embedded
    as a live clickable HTML element inside an MP4. This function recreates
    the same CTA design as a video card and adds a scannable QR code.
    """

    width, height = VIDEO_SIZE

    # Background similar to the supplied Smart Learning Lab HTML page.
    img = Image.new("RGB", (width, height), (7, 26, 51))
    draw = ImageDraw.Draw(img)

    # Simple layered background gradients/glows.
    for y in range(height):
        ratio = y / max(1, height - 1)
        r = int(7 + 4 * ratio)
        g = int(26 + 18 * ratio)
        b = int(51 + 20 * ratio)
        draw.line((0, y, width, y), fill=(r, g, b))

    # Decorative glow circles.
    try:
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse(
            (-180, -180, 350, 350),
            fill=(0, 123, 255, 45)
        )
        glow_draw.ellipse(
            (width - 330, height - 330, width + 180, height + 180),
            fill=(255, 165, 0, 45)
        )
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
        draw = ImageDraw.Draw(img)
    except Exception:
        pass

    # Card.
    card_margin = 35
    card_top = 45
    card_bottom = height - 45
    draw.rounded_rectangle(
        (
            card_margin,
            card_top,
            width - card_margin,
            card_bottom
        ),
        radius=35,
        fill=(24, 47, 72),
        outline=(90, 120, 150),
        width=2
    )

    # Fonts.
    title_font = get_cta_latin_font(42, bold=True)
    tagline_font = get_cta_latin_font(24, bold=False)
    message_font = get_cta_latin_font(25, bold=True)
    button_font = get_cta_latin_font(24, bold=True)
    small_font = get_cta_latin_font(18, bold=False)
    footer_font = get_cta_latin_font(19, bold=True)

    # Logo.
    logo_path = prepare_round_logo()

    if logo_path and os.path.exists(logo_path):
        try:
            with Image.open(logo_path).convert("RGBA") as logo:
                logo_size = 190
                logo = logo.resize(
                    (logo_size, logo_size),
                    Image.Resampling.LANCZOS
                )

                logo_x = (width - logo_size) // 2
                logo_y = 95

                img.paste(
                    logo,
                    (logo_x, logo_y),
                    logo
                )
        except Exception as e:
            print(
                f"⚠️ CTA logo failed: {e}",
                flush=True
            )

    draw = ImageDraw.Draw(img)

    def centered(text_value, font, y, fill=(255, 255, 255)):
        bbox = draw.textbbox(
            (0, 0),
            text_value,
            font=font
        )
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2

        draw.text(
            (x, y),
            text_value,
            font=font,
            fill=fill,
            stroke_width=1,
            stroke_fill=(0, 0, 0)
        )

    # Branding.
    centered(
        "SMART LEARNING LAB",
        title_font,
        305
    )

    centered(
        "Learn Smarter. Grow Faster.",
        tagline_font,
        365,
        fill=(220, 235, 250)
    )

    centered(
        "LIKE OUR PAGE  •  FOLLOW US",
        message_font,
        425
    )

    # Facebook button.
    fb_x1 = 80
    fb_x2 = width - 80
    fb_y1 = 490
    fb_y2 = 555

    draw.rounded_rectangle(
        (fb_x1, fb_y1, fb_x2, fb_y2),
        radius=18,
        fill=(24, 119, 242)
    )

    centered(
        "LIKE & FOLLOW ON FACEBOOK",
        button_font,
        505
    )

    # QR code.
    qr_created = False

    try:
        import qrcode

        qr = qrcode.QRCode(
            version=4,
            box_size=7,
            border=2
        )
        qr.add_data(CTA_URL)
        qr.make(fit=True)

        qr_img = qr.make_image(
            fill_color="black",
            back_color="white"
        ).convert("RGB")

        qr_size = 230
        qr_img.thumbnail(
            (qr_size, qr_size),
            Image.Resampling.LANCZOS
        )

        qr_x = (width - qr_img.width) // 2
        qr_y = 610

        # White QR background/frame.
        padding = 12
        draw.rounded_rectangle(
            (
                qr_x - padding,
                qr_y - padding,
                qr_x + qr_img.width + padding,
                qr_y + qr_img.height + padding
            ),
            radius=10,
            fill=(255, 255, 255)
        )

        img.paste(
            qr_img,
            (qr_x, qr_y)
        )

        qr_created = True

        centered(
            "SCAN TO VISIT",
            small_font,
            qr_y + qr_img.height + 28
        )

    except Exception as e:
        print(
            f"ℹ️ QR code unavailable: {e}",
            flush=True
        )

    # URL.
    url_text = CTA_URL

    if len(url_text) > 48:
        url_text = url_text[:45] + "..."

    centered(
        url_text,
        small_font,
        905 if qr_created else 650,
        fill=(255, 205, 65)
    )

    # Secondary CTA.
    centered(
        "Follow for more inspiring stories",
        tagline_font,
        970,
        fill=(220, 235, 250)
    )

    # Orange visual button.
    learn_x1 = 80
    learn_x2 = width - 80
    learn_y1 = 1020
    learn_y2 = 1085

    draw.rounded_rectangle(
        (learn_x1, learn_y1, learn_x2, learn_y2),
        radius=18,
        fill=(255, 126, 0)
    )

    centered(
        "VISIT SMART LEARNING LAB",
        button_font,
        1035
    )

    centered(
        "BY NITIN MITTAL INNOVATIONS",
        footer_font,
        1115,
        fill=(205, 220, 235)
    )

    # Save the rendered end card.
    path = "images/_end_card.png"
    img.save(path)

    print(
        f"Final Smart Learning Lab CTA created: {path}",
        flush=True
    )
    print(
        f"CTA URL: {CTA_URL}",
        flush=True
    )

    return ImageClip(path).set_duration(duration)
