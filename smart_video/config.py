"""Application configuration loaded from environment variables."""

import os


# Video
VIDEO_SIZE = (720, 1280)
FPS = int(os.getenv("VIDEO_FPS", "24"))
MIN_DURATION = float(os.getenv("MIN_SCENE_DURATION", "5"))

# Pause between completed image generations.
# Default: 5 seconds. Override with IMAGE_GENERATION_SLEEP_SECONDS.
IMAGE_GENERATION_SLEEP_SECONDS = max(
    0.0,
    float(os.getenv("IMAGE_GENERATION_SLEEP_SECONDS", "5"))
)

# Pause after each external translation request. Translation is optional, so
# failures fall back to the original text without stopping video generation.
TRANSLATION_REQUEST_SLEEP_SECONDS = max(
    0.0,
    float(os.getenv("TRANSLATION_REQUEST_SLEEP_SECONDS", "2"))
)

# Branding
LOGO_PATH = os.getenv("LOGO_PATH", "logo.png")
LOGO_SIZE = int(os.getenv("LOGO_SIZE", "125"))
LOGO_MARGIN = int(os.getenv("LOGO_MARGIN", "18"))

CTA_URL = os.getenv(
    "CTA_URL",
    "https://www.facebook.com/thesmartlearninglab",
)
END_CARD_DURATION = float(os.getenv("END_CARD_DURATION", "5"))
TITLE_CARD_DURATION = float(os.getenv("TITLE_CARD_DURATION", "3"))
TITLE_TEMPLATE_PATH = os.getenv(
    "TITLE_TEMPLATE_PATH",
    "title_page_template.png",
)

TITLE_TEMPLATE_CROP = (
    0.0432,
    0.0262,
    0.8811,
    0.9692,
)

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
DATABASE_NAME = os.getenv("MONGODB_DATABASE", "storydb").strip()
COLLECTION_NAME = os.getenv("MONGODB_COLLECTION", "story_scenes").strip()
STORY_ID = os.getenv("STORY_ID", "").strip() or None
MONGODB_SERVER_TIMEOUT_MS = int(
    os.getenv("MONGODB_SERVER_TIMEOUT_MS", "10000")
)

# Generated assets
os.makedirs("images", exist_ok=True)
os.makedirs("audio", exist_ok=True)
