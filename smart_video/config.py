# Required packages:
# pip install -U edge-tts pymongo requests numpy nest-asyncio pillow moviepy qrcode
#
# For Hindi subtitles on Linux/GitHub Actions:
# sudo apt-get update
# sudo apt-get install -y fonts-noto-core
#
import os
import requests
import urllib.parse
import time
import numpy as np
import asyncio
import edge_tts
import nest_asyncio
import unicodedata
from datetime import datetime, timezone

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import ConnectionFailure

from moviepy.editor import *
from moviepy.video.fx.all import fadein, fadeout
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy.audio.AudioClip import AudioArrayClip


# ============================================================
# FIX ASYNC
# ============================================================

nest_asyncio.apply()


# ============================================================
# CONFIG
# ============================================================

VIDEO_SIZE = (720, 1280)
FPS = 24
MIN_DURATION = 5

# ============================================================
# BRANDING / FINAL CTA
# ============================================================

# Keep logo.png beside script.py.
LOGO_PATH = os.getenv("LOGO_PATH", "logo.png")
LOGO_SIZE = int(os.getenv("LOGO_SIZE", "125"))
LOGO_MARGIN = int(os.getenv("LOGO_MARGIN", "18"))

# Final Like / Subscribe / Learn More page.
# Change CTA_URL to your real Smart Learning Lab page.
CTA_URL = "https://www.facebook.com/thesmartlearninglab"
END_CARD_DURATION = float(os.getenv("END_CARD_DURATION", "5"))

# Opening title page.
# The title is read directly from the MongoDB story document.
TITLE_CARD_DURATION = float(os.getenv("TITLE_CARD_DURATION", "4"))

# Exact title-page design/template supplied by you.
# Put the supplied poster image in the repository with this name.
# You can also override it with TITLE_TEMPLATE_PATH environment variable.
TITLE_TEMPLATE_PATH = os.getenv(
    "TITLE_TEMPLATE_PATH",
    "title_page_template.png"
)

# The supplied screenshot contains a white/outer border around the
# actual 9:16 poster. These normalized values crop that border.
TITLE_TEMPLATE_CROP = (
    0.0432,   # left
    0.0262,   # top
    0.8811,   # right
    0.9692    # bottom
)

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")

DATABASE_NAME = "storydb"
COLLECTION_NAME = "story_scenes"

# MongoDB scene schema: sub_image_prompts[{text, image_prompt}]

# Optional:
# Set STORY_ID when you want to process a specific story.
#
# Example:
# STORY_ID=story_001
#
# If not provided, the first story from MongoDB will be used.
STORY_ID = os.getenv("STORY_ID")

os.makedirs("images", exist_ok=True)
os.makedirs("audio", exist_ok=True)
