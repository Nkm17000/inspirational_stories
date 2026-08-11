"""Logo preparation and fullscreen image clips."""

import os
from PIL import Image, ImageDraw
from moviepy.editor import ImageClip, ColorClip, CompositeVideoClip

from .config import VIDEO_SIZE, LOGO_PATH, LOGO_SIZE, LOGO_MARGIN

# ============================================================
# FULLSCREEN IMAGE CLIP
# ============================================================

def prepare_round_logo():
    """Create a transparent circular version of logo.png."""
    if not os.path.exists(LOGO_PATH):
        print(
            f"⚠️ Logo not found at '{LOGO_PATH}'. "
            "Video will continue without branding.",
            flush=True
        )
        return None

    output_path = os.path.join("images", "_round_logo.png")

    try:
        if os.path.exists(output_path):
            if os.path.getmtime(output_path) >= os.path.getmtime(LOGO_PATH):
                return output_path

        with Image.open(LOGO_PATH).convert("RGBA") as source:
            source.thumbnail(
                (LOGO_SIZE, LOGO_SIZE),
                Image.Resampling.LANCZOS
            )

            canvas = Image.new(
                "RGBA",
                (LOGO_SIZE, LOGO_SIZE),
                (0, 0, 0, 0)
            )

            x = (LOGO_SIZE - source.width) // 2
            y = (LOGO_SIZE - source.height) // 2
            canvas.alpha_composite(source, (x, y))

            # Make the logo genuinely round.
            mask = Image.new(
                "L",
                (LOGO_SIZE, LOGO_SIZE),
                0
            )
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse(
                (0, 0, LOGO_SIZE - 1, LOGO_SIZE - 1),
                fill=255
            )
            canvas.putalpha(mask)

            canvas.save(output_path, "PNG")

        print(
            f"✅ Circular logo prepared: {output_path}",
            flush=True
        )
        return output_path

    except Exception as e:
        print(f"⚠️ Could not prepare logo: {e}", flush=True)
        return None


ROUND_LOGO_PATH = None


def create_fullscreen_clip(
    image_path,
    duration,
    index
):
    """
    Create the image clip and put the circular logo at the top-left.

    The logo is part of every individual image clip, therefore it stays
    visible for the full duration of every image.
    """
    global ROUND_LOGO_PATH

    if image_path is None:
        base_clip = ColorClip(
            VIDEO_SIZE,
            color=(0, 0, 0)
        ).set_duration(duration)
    else:
        clip = ImageClip(image_path)

        clip = clip.resize(
            height=VIDEO_SIZE[1]
        )

        if clip.w < VIDEO_SIZE[0]:
            clip = clip.resize(
                width=VIDEO_SIZE[0]
            )

        clip = clip.crop(
            x_center=clip.w / 2,
            y_center=clip.h / 2,
            width=VIDEO_SIZE[0],
            height=VIDEO_SIZE[1]
        )

        base_clip = clip.set_duration(duration)

    if ROUND_LOGO_PATH is None:
        ROUND_LOGO_PATH = prepare_round_logo()

    if not ROUND_LOGO_PATH or not os.path.exists(ROUND_LOGO_PATH):
        return base_clip

    try:
        logo_clip = (
            ImageClip(ROUND_LOGO_PATH)
            .resize(width=LOGO_SIZE)
            .set_position((LOGO_MARGIN, LOGO_MARGIN))
            .set_duration(duration)
        )

        result = CompositeVideoClip(
            [base_clip, logo_clip],
            size=VIDEO_SIZE
        ).set_duration(duration)

        print(
            f"   🏷️ Logo added to image {index} "
            f"at top-left ({LOGO_MARGIN}, {LOGO_MARGIN})",
            flush=True
        )

        return result

    except Exception as e:
        print(f"⚠️ Logo overlay failed: {e}", flush=True)
        return base_clip
