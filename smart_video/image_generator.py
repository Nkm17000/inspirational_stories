"""AI image generation with Cloudflare Workers AI as primary and Pollinations as fallback."""

import base64
import os
import time
import urllib.parse
from io import BytesIO

import requests
from PIL import Image, ImageDraw

from .config import VIDEO_SIZE
from .fonts import get_unicode_font


# ============================================================
# CONFIGURATION
# ============================================================

CLOUDFLARE_ACCOUNT_ID = os.getenv(
    "CLOUDFLARE_ACCOUNT_ID", ""
).strip()

CLOUDFLARE_API_TOKEN = os.getenv(
    "CLOUDFLARE_API_TOKEN", ""
).strip()

CLOUDFLARE_MODEL = os.getenv(
    "CLOUDFLARE_IMAGE_MODEL",
    "@cf/black-forest-labs/flux-1-schnell",
).strip()

# 3 steps keeps usage lower while retaining reasonable scene quality.
# Increase to 4 if you prefer the model's default quality/steps.
CLOUDFLARE_STEPS = int(
    os.getenv("CLOUDFLARE_IMAGE_STEPS", "3")
)

CLOUDFLARE_RETRIES = int(
    os.getenv("CLOUDFLARE_IMAGE_RETRIES", "2")
)

CLOUDFLARE_TIMEOUT = int(
    os.getenv("CLOUDFLARE_IMAGE_TIMEOUT", "120")
)

POLLINATIONS_RETRIES = int(
    os.getenv("POLLINATIONS_IMAGE_RETRIES", "3")
)

POLLINATIONS_TIMEOUT = int(
    os.getenv("POLLINATIONS_IMAGE_TIMEOUT", "30")
)


# ============================================================
# HELPERS
# ============================================================

def _save_cloudflare_image(response, path):
    """
    Cloudflare FLUX.1 Schnell REST responses contain:
        {
            "result": {
                "image": "<base64>"
            }
        }

    Decode the Base64 image, validate it with Pillow, and save it.
    Returns True on success.
    """
    data = response.json()

    result = data.get("result")

    if not isinstance(result, dict):
        raise ValueError(
            f"Unexpected Cloudflare result format: {type(result).__name__}"
        )

    image_base64 = result.get("image")

    if not image_base64:
        raise ValueError(
            "Cloudflare response did not contain result.image"
        )

    # Be tolerant if a future response includes a data-URI prefix.
    if image_base64.startswith("data:") and "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]

    image_bytes = base64.b64decode(image_base64, validate=True)

    # Validate before declaring success.
    image = Image.open(BytesIO(image_bytes))
    image.verify()

    with open(path, "wb") as f:
        f.write(image_bytes)

    return True


def _generate_cloudflare(prompt, path):
    """Generate an image using Cloudflare Workers AI."""
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        print(
            "ℹ️ Cloudflare credentials are not configured; "
            "skipping to Pollinations fallback.",
            flush=True,
        )
        return False

    api_url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{CLOUDFLARE_ACCOUNT_ID}/ai/run/"
        f"{CLOUDFLARE_MODEL}"
    )

    payload = {
        "prompt": prompt,
        "steps": CLOUDFLARE_STEPS,
    }

    for attempt in range(1, CLOUDFLARE_RETRIES + 1):
        try:
            print(
                f"☁️ Cloudflare image attempt "
                f"{attempt}/{CLOUDFLARE_RETRIES}",
                flush=True,
            )

            response = requests.post(
                api_url,
                headers={
                    "Authorization": (
                        f"Bearer {CLOUDFLARE_API_TOKEN}"
                    ),
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=CLOUDFLARE_TIMEOUT,
            )

            if response.status_code == 200:
                try:
                    _save_cloudflare_image(response, path)

                    print(
                        f"✅ Cloudflare image saved: {path}",
                        flush=True,
                    )

                    return True

                except Exception as e:
                    print(
                        "⚠️ Cloudflare returned an invalid image:",
                        e,
                        flush=True,
                    )

            else:
                # Do not print the Authorization header/token.
                try:
                    error_data = response.json()
                except Exception:
                    error_data = response.text[:1000]

                print(
                    f"⚠️ Cloudflare API error "
                    f"(HTTP {response.status_code}): "
                    f"{error_data}",
                    flush=True,
                )

        except requests.RequestException as e:
            print(
                "⚠️ Cloudflare request failed:",
                e,
                flush=True,
            )

        if attempt < CLOUDFLARE_RETRIES:
            time.sleep(2)

    return False


def _generate_pollinations(prompt, path):
    """Generate an image using Pollinations as the AI fallback."""
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(prompt)
    )

    for attempt in range(1, POLLINATIONS_RETRIES + 1):
        try:
            print(
                f"🔄 Pollinations fallback attempt "
                f"{attempt}/{POLLINATIONS_RETRIES}",
                flush=True,
            )

            response = requests.get(
                url,
                timeout=POLLINATIONS_TIMEOUT,
            )

            if response.status_code == 200 and response.content:
                # Validate that the response is actually an image.
                image = Image.open(
                    BytesIO(response.content)
                )
                image.verify()

                with open(path, "wb") as f:
                    f.write(response.content)

                print(
                    f"✅ Pollinations fallback image saved: {path}",
                    flush=True,
                )

                return True

            print(
                f"⚠️ Pollinations returned HTTP "
                f"{response.status_code}",
                flush=True,
            )

        except Exception as e:
            print(
                "⚠️ Pollinations fallback failed:",
                e,
                flush=True,
            )

        if attempt < POLLINATIONS_RETRIES:
            time.sleep(3)

    return False


# ============================================================
# PUBLIC IMAGE GENERATOR
# ============================================================

def generate_image(
    prompt,
    path,
    fallback_text=None,
):
    """
    Generate a scene image.

    Provider order:
        1. Cloudflare Workers AI
        2. Pollinations
        3. Local text fallback

    The rest of the application only needs to call this function.
    """

    # --------------------------------------------------------
    # 1. CLOUDFLARE PRIMARY
    # --------------------------------------------------------

    if _generate_cloudflare(prompt, path):
        return path

    # --------------------------------------------------------
    # 2. POLLINATIONS AI FALLBACK
    # --------------------------------------------------------

    print(
        "🔄 Switching to Pollinations fallback...",
        flush=True,
    )

    if _generate_pollinations(prompt, path):
        return path

    # --------------------------------------------------------
    # 3. LOCAL FALLBACK
    # --------------------------------------------------------

    print(
        "🖼️ Using local fallback image...",
        flush=True,
    )

    try:
        img = Image.new(
            "RGB",
            VIDEO_SIZE,
            (20, 20, 20),
        )

        draw = ImageDraw.Draw(img)

        font = get_unicode_font(
            45,
            bold=True,
        )

        text = fallback_text or "Scene"

        words = text.split()
        lines = []
        line = ""

        for word in words:
            if len(line + word) < 20:
                line += word + " "
            else:
                lines.append(line.strip())
                line = word + " "

        if line.strip():
            lines.append(line.strip())

        lines = lines[:4]

        y = VIDEO_SIZE[1] // 2 - 100

        for i, line_text in enumerate(lines):
            bbox = draw.textbbox(
                (0, 0),
                line_text,
                font=font,
            )

            width = bbox[2] - bbox[0]

            draw.text(
                (
                    (VIDEO_SIZE[0] - width) // 2,
                    y + i * 60,
                ),
                line_text,
                font=font,
                fill=(255, 255, 255),
            )

        img.save(path)

        print(
            f"⚠️ Local fallback saved: {path}",
            flush=True,
        )

        return path

    except Exception as e:
        print(
            "❌ Final fallback failed:",
            e,
            flush=True,
        )

        return None
