"""Font helpers for Hindi/Devanagari and Latin text."""

import os
import subprocess
from PIL import ImageFont

# ============================================================
# FONT HELPERS
# ============================================================

def get_unicode_font(size, bold=True):
    """
    Find a font that supports both Latin and Devanagari/Hindi.
    Works on common Linux/GitHub Actions and Windows setups.
    """
    candidates = []

    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "NotoSansDevanagari-Bold.ttf",
            "NotoSansDevanagari.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            "NotoSansDevanagari-Regular.ttf",
            "NotoSansDevanagari.ttf",
        ])

    # Generic fallback fonts.
    candidates.extend([
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ])

    for font_path in candidates:
        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        except Exception:
            pass

    try:
        return ImageFont.truetype(
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            size
        )
    except Exception:
        return ImageFont.load_default()


def find_devanagari_font(size, bold=True):
    """Find a real Devanagari font for title rendering."""
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "NotoSansDevanagari-Bold.ttf",
            "Nirmala.ttf",
            "Mangal.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            "NotoSansDevanagari-Regular.ttf",
            "Nirmala.ttf",
            "Mangal.ttf",
        ]

    try:
        pattern = "Noto Sans Devanagari:style=Bold" if bold else "Noto Sans Devanagari"
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", pattern],
            capture_output=True,
            text=True,
            timeout=5,
        )
        font_path = result.stdout.strip()
        if font_path and os.path.exists(font_path):
            candidates.insert(0, font_path)
    except Exception:
        pass

    for font_path in candidates:
        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        except Exception:
            pass

    return get_unicode_font(size, bold=bold)


def get_cta_latin_font(size, bold=True):
    """Use a Latin font for the English CTA card."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/lato/Lato-Bold.ttf"
        if bold else "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for font_path in candidates:
        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    return get_unicode_font(size, bold=bold)
