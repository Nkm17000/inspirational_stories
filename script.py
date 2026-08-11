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
from PIL import Image, ImageDraw, ImageFont
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


# ============================================================
# MONGODB CONNECTION
# ============================================================

def get_mongodb_collection():

    if not MONGODB_URI:
        raise ValueError(
            "❌ MONGODB_URI environment variable is not set"
        )

    try:

        print(
            "🔌 Connecting to MongoDB Atlas...",
            flush=True
        )

        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=10000
        )

        # Test MongoDB connection
        client.admin.command("ping")

        print(
            "✅ MongoDB connection successful!",
            flush=True
        )

        db = client[DATABASE_NAME]

        collection = db[COLLECTION_NAME]

        print(
            f"📦 Database: {DATABASE_NAME}",
            flush=True
        )

        print(
            f"📚 Collection: {COLLECTION_NAME}",
            flush=True
        )

        return client, collection

    except ConnectionFailure as e:

        print(
            "❌ MongoDB connection failed:",
            e,
            flush=True
        )

        raise


# ============================================================
# MONGODB STATUS HELPERS
# ============================================================

def update_story_status(story, status, extra_fields=None, retries=3):
    """
    Reliably update and VERIFY the MongoDB status.

    The primary key is the document's _id. This avoids failures caused
    by a missing/different story_id field name. story_id/id/ID are also
    supported for compatibility with existing documents.
    """
    if not story:
        print("⚠️ Cannot update MongoDB status: story document is missing", flush=True)
        return False

    mongo_id = story.get("_id")
    story_id = (
        story.get("story_id")
        or story.get("id")
        or story.get("ID")
        or "unknown"
    )

    fields = {
        "status": status,
        "updated_at": datetime.now(timezone.utc)
    }

    if extra_fields:
        fields.update(extra_fields)

    if status == "COMPLETED":
        fields["story_id"] = story_id

    for attempt in range(1, retries + 1):
        client = None
        try:
            client, collection = get_mongodb_collection()

            if mongo_id is not None:
                query = {"_id": mongo_id}
            else:
                # Compatibility fallback for documents without _id in
                # an unusual test/mock collection.
                query = {
                    "$or": [
                        {"story_id": story_id},
                        {"id": story_id},
                        {"ID": story_id}
                    ]
                }

            result = collection.update_one(
                query,
                {"$set": fields}
            )

            current = collection.find_one(
                query,
                {"status": 1, "story_id": 1, "id": 1, "ID": 1}
            )

            actual_status = current.get("status") if current else None

            if actual_status == status:
                print(
                    f"✅ MongoDB status verified: {story_id} -> {status} "
                    f"(matched={result.matched_count}, "
                    f"modified={result.modified_count})",
                    flush=True
                )
                return True

            print(
                f"⚠️ MongoDB verification attempt "
                f"{attempt}/{retries}: expected={status}, "
                f"actual={actual_status}, story={story_id}",
                flush=True
            )

        except Exception as e:
            print(
                f"⚠️ MongoDB status update attempt "
                f"{attempt}/{retries} failed: {e}",
                flush=True
            )
        finally:
            if client:
                client.close()

        if attempt < retries:
            time.sleep(2 * attempt)

    return False


# ============================================================
# GET STORY FROM MONGODB
# ============================================================

def get_story_from_mongodb():
    """Atomically claim exactly one PENDING story."""
    client, collection = get_mongodb_collection()

    try:
        if STORY_ID:
            print(f"🔎 Requested STORY_ID: {STORY_ID}", flush=True)
            query = {"story_id": STORY_ID, "status": "PENDING"}
        else:
            print("🔎 STORY_ID not provided.", flush=True)
            print("📖 Searching for next PENDING story...", flush=True)
            query = {"status": "PENDING"}

        story = collection.find_one_and_update(
            query,
            {"$set": {"status": "PROCESSING"}},
            sort=[("created_at", 1), ("story_id", 1)],
            return_document=ReturnDocument.AFTER
        )

        if not story:
            print("ℹ️ No PENDING story available.", flush=True)
            return None, []

        title = story.get("title", "Untitled Story")
        story_id = (story.get("story_id") or story.get("id") or story.get("ID") or "unknown")

        print("✅ Story claimed successfully", flush=True)
        print(f"🆔 Story ID: {story_id}", flush=True)
        print(f"📖 Title: {title}", flush=True)
        print("🔄 Status: PROCESSING", flush=True)

        scenes = story.get("scenes", [])

        if not scenes:
            collection.update_one(
                {"_id": story["_id"], "status": "PROCESSING"},
                {"$set": {"status": "FAILED", "last_error": "Story contains no scenes"}}
            )
            raise ValueError("❌ Story contains no scenes")

        print(f"🎬 Total scenes: {len(scenes)}", flush=True)

        valid_scenes = []

        for scene in scenes:
            text = scene.get("text")
            sub_image_prompts = scene.get("sub_image_prompts")

            if not text:
                print("⚠️ Scene skipped: missing text", flush=True)
                continue

            if not isinstance(sub_image_prompts, list) or not sub_image_prompts:
                print("⚠️ Scene skipped: missing sub_image_prompts array", flush=True)
                continue

            valid_sub_prompts = []

            for sub_index, item in enumerate(sub_image_prompts, start=1):
                if not isinstance(item, dict):
                    print(
                        f"⚠️ Scene {scene.get('scene_number', '?')}: "
                        f"sub_image_prompts item {sub_index} is not an object",
                        flush=True
                    )
                    continue

                sub_text = item.get("text")
                image_prompt = item.get("image_prompt")

                if not image_prompt or not isinstance(image_prompt, str):
                    print(
                        f"⚠️ Scene {scene.get('scene_number', '?')}: "
                        f"sub-image {sub_index} missing image_prompt",
                        flush=True
                    )
                    continue

                valid_sub_prompts.append({
                    "text": sub_text.strip() if isinstance(sub_text, str) else "",
                    "image_prompt": image_prompt.strip()
                })

            if not valid_sub_prompts:
                print(
                    f"⚠️ Scene {scene.get('scene_number', '?')}: "
                    "no valid sub-image prompts",
                    flush=True
                )
                continue

            valid_scenes.append({
                "scene_number": scene.get(
                    "scene_number",
                    len(valid_scenes) + 1
                ),
                "text": text,
                "sub_image_prompts": valid_sub_prompts
            })

        if not valid_scenes:
            collection.update_one(
                {"_id": story["_id"], "status": "PROCESSING"},
                {"$set": {"status": "FAILED", "last_error": "No valid scenes found"}}
            )
            raise ValueError("❌ No valid scenes found")

        print(f"✅ Valid scenes: {len(valid_scenes)}", flush=True)
        return story, valid_scenes

    finally:
        client.close()



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


# ============================================================
# IMAGE GENERATION
# ============================================================

def generate_image(
    prompt,
    path,
    fallback_text=None
):

    # --------------------------------------------------------
    # 1. Pollinations
    # --------------------------------------------------------

    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(prompt)
    )

    for i in range(3):

        try:

            print(
                f"🖼️ Pollinations attempt {i + 1}",
                flush=True
            )

            time.sleep(5)

            response = requests.get(
                url,
                timeout=20
            )

            if response.status_code == 200:

                with open(path, "wb") as f:

                    f.write(
                        response.content
                    )

                print(
                    f"✅ Image saved: {path}",
                    flush=True
                )

                return path

        except Exception as e:

            print(
                "⚠️ Pollinations retry:",
                e,
                flush=True
            )


    # --------------------------------------------------------
    # 2. Picsum fallback
    # --------------------------------------------------------

    try:

        print(
            "🖼️ Picsum fallback",
            flush=True
        )

        picsum_url = (
            "https://picsum.photos/720/1280"
            f"?random={int(time.time())}"
        )

        response = requests.get(
            picsum_url,
            timeout=15
        )

        if response.status_code == 200:

            with open(path, "wb") as f:

                f.write(
                    response.content
                )

            return path

    except Exception as e:

        print(
            "⚠️ Picsum failed:",
            e,
            flush=True
        )


    # --------------------------------------------------------
    # 3. Dummy image fallback
    # --------------------------------------------------------

    try:

        print(
            "🖼️ Dummy fallback",
            flush=True
        )

        text = fallback_text or "Scene"

        dummy_url = (
            "https://dummyimage.com/720x1280/000/fff"
            f"&text={urllib.parse.quote(text[:80])}"
        )

        response = requests.get(
            dummy_url,
            timeout=10
        )

        if response.status_code == 200:

            with open(path, "wb") as f:

                f.write(
                    response.content
                )

            return path

    except Exception as e:

        print(
            "⚠️ Dummy failed:",
            e,
            flush=True
        )


    # --------------------------------------------------------
    # 4. Local fallback
    # --------------------------------------------------------

    print(
        "🖼️ Local fallback",
        flush=True
    )

    try:

        img = Image.new(
            "RGB",
            VIDEO_SIZE,
            (20, 20, 20)
        )

        draw = ImageDraw.Draw(img)

        font = get_unicode_font(45, bold=True)

        text = fallback_text or "Scene"

        words = text.split()

        lines = []

        line = ""

        for word in words:

            if len(line + word) < 20:

                line += word + " "

            else:

                lines.append(
                    line.strip()
                )

                line = word + " "

        lines.append(
            line.strip()
        )

        lines = lines[:4]

        y = (
            VIDEO_SIZE[1] // 2
            - 100
        )

        for i, line_text in enumerate(lines):

            bbox = draw.textbbox(
                (0, 0),
                line_text,
                font=font
            )

            width = (
                bbox[2]
                - bbox[0]
            )

            draw.text(
                (
                    (VIDEO_SIZE[0] - width) // 2,
                    y + i * 60
                ),
                line_text,
                font=font,
                fill=(255, 255, 255)
            )

        img.save(path)

        return path

    except Exception as e:

        print(
            "❌ Final fallback failed:",
            e,
            flush=True
        )

        return None


# ============================================================
# VOICE
# ============================================================

# ============================================================
# LANGUAGE + VOICE HELPERS
# ============================================================

def detect_text_language(text):
    """
    Detect Hindi vs English from Unicode script.

    Hindi/Devanagari characters are in U+0900-U+097F.
    If enough Devanagari characters are present, use Hindi TTS.
    Otherwise use English TTS.
    """
    if not text:
        return "en"

    devanagari = sum(
        1 for ch in text
        if "\u0900" <= ch <= "\u097F"
    )

    latin = sum(
        1 for ch in text
        if ("A" <= ch <= "Z") or ("a" <= ch <= "z")
    )

    if devanagari > 0 and devanagari >= latin * 0.20:
        return "hi"

    return "en"


def get_voice_candidates(text):
    """
    Return voices in priority order.

    Hindi:
      1. hi-IN-SwaraNeural
      2. hi-IN-AnanyaNeural
      3. hi-IN-MadhurNeural
      4. en-IN-NeerjaNeural

    English:
      1. en-IN-NeerjaNeural
      2. en-IN-AnanyaNeural
      3. en-IN-PrabhatNeural
    """
    language = detect_text_language(text)

    if language == "hi":
        return [
            "hi-IN-SwaraNeural",
            "hi-IN-AnanyaNeural",
            "hi-IN-MadhurNeural",
            "en-IN-NeerjaNeural",
        ]

    return [
        "en-IN-NeerjaNeural",
        "en-IN-AnanyaNeural",
        "en-IN-PrabhatNeural",
    ]


def clean_tts_text(text):
    """
    Normalize text without destroying Hindi Unicode characters.
    """
    if not text:
        return ""

    text = str(text)

    # Remove accidental control characters but preserve Unicode.
    text = "".join(
        ch for ch in text
        if ch in "\n\r\t" or ord(ch) >= 32
    )

    # Normalize whitespace.
    text = " ".join(text.split())

    return text.strip()


def run_async(coro):
    """
    Safely run an async coroutine even when an event loop is already active.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        result = {}

        def runner():
            try:
                result["value"] = asyncio.run(coro)
            except Exception as e:
                result["error"] = e

        import threading
        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()

        if "error" in result:
            raise result["error"]

        return result.get("value")

    return asyncio.run(coro)


# ============================================================
# VOICE
# ============================================================

def generate_voice(
    text,
    path
):
    """
    Generate Edge-TTS audio for both Hindi and English.

    Hindi text is automatically routed to a Hindi voice.
    English text is routed to an Indian-English voice.

    WordBoundary timings are collected when Edge-TTS provides them.
    The video does NOT depend on WordBoundary timings; subtitles use
    the actual generated audio duration.

    Returns:
        (audio_path, word_timings)
    """

    text = clean_tts_text(text)

    if not text:
        print("⚠️ Empty narration text; skipping TTS", flush=True)
        return None, []

    language = detect_text_language(text)
    voices = get_voice_candidates(text)

    print(
        f"🌐 Detected language: "
        f"{'Hindi' if language == 'hi' else 'English'}",
        flush=True
    )

    print(
        f"🎤 Voice candidates: {', '.join(voices)}",
        flush=True
    )

    async def tts(voice_name):
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_name,
            rate="-15%",
            # Explicitly request word boundaries where supported.
            boundary="WordBoundary"
        )

        audio_bytes = bytearray()
        word_timings = []

        async for chunk in communicate.stream():

            chunk_type = chunk.get("type")

            if chunk_type == "audio":
                data = chunk.get("data", b"")

                if data:
                    audio_bytes.extend(data)

            elif chunk_type == "WordBoundary":
                word = chunk.get("text", "").strip()

                if not word:
                    continue

                offset = chunk.get("offset", 0)
                word_duration = chunk.get("duration", 0)

                # Edge-TTS timing units are 100 nanoseconds.
                start_seconds = offset / 10_000_000
                end_seconds = (
                    offset + word_duration
                ) / 10_000_000

                word_timings.append({
                    "word": word,
                    "start": start_seconds,
                    "end": end_seconds
                })

        if not audio_bytes:
            raise RuntimeError(
                f"Edge-TTS returned no audio for voice '{voice_name}'"
            )

        # Write atomically so a failed request never leaves a bad MP3.
        temp_path = path + ".tmp"

        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        if not os.path.exists(temp_path) or os.path.getsize(temp_path) < 1000:
            try:
                os.remove(temp_path)
            except OSError:
                pass

            raise RuntimeError(
                f"TTS produced an invalid/empty audio file for '{voice_name}'"
            )

        os.replace(temp_path, path)

        return word_timings

    # Try each suitable voice. This is much better than retrying
    # the same voice three times when the selected voice is unavailable.
    for voice_index, voice_name in enumerate(voices, start=1):

        for attempt in range(1, 3):

            try:
                print(
                    f"🎤 Voice {voice_index}/{len(voices)} "
                    f"({voice_name}) attempt {attempt}",
                    flush=True
                )

                timings = run_async(tts(voice_name))

                print(
                    f"✅ Voice generated using {voice_name}: "
                    f"{len(timings)} word timings",
                    flush=True
                )

                return path, timings

            except Exception as e:

                print(
                    f"⚠️ {voice_name} failed: {e}",
                    flush=True
                )

                time.sleep(2)

    print(
        "❌ All Edge-TTS voices failed",
        flush=True
    )

    return None, []


# ============================================================
# WORD COUNT / SUBTITLE HELPERS
# ============================================================

def split_words_unicode(text):
    """
    Unicode-safe word splitting.

    Python's split() already handles Hindi words separated by spaces,
    but this helper also removes empty tokens and avoids accidental
    punctuation-only tokens.
    """
    if not text:
        return []

    return [
        word.strip()
        for word in str(text).split()
        if word.strip()
    ]

# ============================================================
# SUBTITLE
# ============================================================

def create_subtitle(text, duration, word_timings=None):
    """
    Subtitle timing based on the ACTUAL VOICE DURATION.

    The sentence is divided into 3 word groups.

    Example for 21 words:
        Group 1 = words 1-7
        Group 2 = words 8-14
        Group 3 = words 15-21

    The duration of each group is proportional to its number of words.

    Example:
        Voice = 21 seconds
        21 words / 3 groups = 7 words per group

        Group 1 -> 0-7 sec
        Group 2 -> 7-14 sec
        Group 3 -> 14-21 sec

    IMPORTANT:
    We intentionally do NOT use Edge-TTS WordBoundary timestamps here.
    The subtitle timing is calculated from the total generated voice
    duration, exactly according to the requested 7-word grouping logic.
    """

    FONT_SIZE = 40
    MAX_CHARS_PER_LINE = 22
    MAX_LINES = 3
    LINE_HEIGHT = 60

    font = get_unicode_font(FONT_SIZE, bold=True)

    # ------------------------------------------------------------
    # Split sentence into words
    # ------------------------------------------------------------

    words = split_words_unicode(text)

    if not words:
        return ImageClip(
            np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 4), dtype=np.uint8)
        ).set_duration(duration)

    total_words = len(words)

    # ------------------------------------------------------------
    # Divide words into 3 approximately equal groups.
    #
    # Examples:
    # 21 words -> 7 / 7 / 7
    # 20 words -> 7 / 7 / 6
    # 10 words -> 4 / 3 / 3
    #  5 words -> 2 / 2 / 1
    # ------------------------------------------------------------

    group_count = min(3, total_words)

    base_size = total_words // group_count
    remainder = total_words % group_count

    groups = []
    start_index = 0

    for group_index in range(group_count):
        group_size = base_size + (
            1 if group_index < remainder else 0
        )

        group_words = words[
            start_index:start_index + group_size
        ]

        groups.append(group_words)
        start_index += group_size

    # ------------------------------------------------------------
    # Create one subtitle clip for each word group.
    #
    # Timing is based on the TOTAL VOICE DURATION.
    # ------------------------------------------------------------

    subtitle_clips = []
    elapsed = 0.0

    for group_index, group_words in enumerate(groups):

        word_count = len(group_words)

        # Each word gets an equal share of the voice duration.
        group_duration = (
            duration * word_count / total_words
        )

        start_time = elapsed

        # Make the last group end exactly at duration.
        if group_index == len(groups) - 1:
            end_time = duration
        else:
            end_time = min(
                duration,
                start_time + group_duration
            )

        elapsed = end_time

        group_text = " ".join(group_words)

        # --------------------------------------------------------
        # Wrap this group into maximum 3 lines.
        # IMPORTANT:
        # We display the ENTIRE group, not only the last words.
        # --------------------------------------------------------

        lines = []
        line = ""

        for word in group_words:

            candidate = (
                f"{line} {word}".strip()
            )

            if len(candidate) <= MAX_CHARS_PER_LINE:
                line = candidate
            else:
                if line:
                    lines.append(line)

                line = word

        if line:
            lines.append(line)

        # If a group somehow needs more than 3 lines,
        # preserve the whole group by reducing the font slightly.
        render_font = font

        if len(lines) > MAX_LINES:
            render_font = get_unicode_font(34, bold=True)

        # --------------------------------------------------------
        # Debug log
        # --------------------------------------------------------

        print(
            f"📝 Subtitle group {group_index + 1}/{len(groups)}: "
            f"{start_time:.2f}s -> {end_time:.2f}s | "
            f"{word_count} words | {group_text}",
            flush=True
        )

        # --------------------------------------------------------
        # Render subtitle image
        # --------------------------------------------------------

        img = Image.new(
            "RGBA",
            VIDEO_SIZE,
            (0, 0, 0, 0)
        )

        draw = ImageDraw.Draw(img)

        visible_lines = lines[:MAX_LINES]

        block_height = (
            len(visible_lines) * LINE_HEIGHT
        )

        y = (
            VIDEO_SIZE[1]
            - 180
            - block_height
        )

        for line_index, line_text in enumerate(
            visible_lines
        ):

            bbox = draw.textbbox(
                (0, 0),
                line_text,
                font=render_font
            )

            width = (
                bbox[2] - bbox[0]
            )

            draw.text(
                (
                    (
                        VIDEO_SIZE[0]
                        - width
                    ) // 2,
                    y + line_index * LINE_HEIGHT
                ),
                line_text,
                font=render_font,
                fill=(255, 255, 0),
                stroke_width=3,
                stroke_fill=(0, 0, 0)
            )

        subtitle_clip = (
            ImageClip(np.array(img))
            .set_start(start_time)
            .set_duration(
                max(0.001, end_time - start_time)
            )
        )

        subtitle_clips.append(
            subtitle_clip
        )

    return CompositeVideoClip(
        subtitle_clips,
        size=VIDEO_SIZE
    ).set_duration(duration)


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


# ============================================================
# CREATE SCENE
# ============================================================

def create_scene(
    scene,
    index
):

    scene_number = scene.get(
        "scene_number",
        index + 1
    )

    print(
        f"\n🎬 Scene {scene_number}",
        flush=True
    )

    # --------------------------------------------------------
    # Main scene text comes directly from MongoDB.
    #
    # IMPORTANT:
    # The main text is used for ONE voice track.
    # sub_image_prompts only controls which images are shown.
    # --------------------------------------------------------

    text = clean_tts_text(scene["text"])

    if not text:
        raise ValueError(
            f"❌ Scene {scene_number} contains empty narration text"
        )

    # --------------------------------------------------------
    # New MongoDB structure:
    #
    # "sub_image_prompts": [
    #   {
    #       "text": "...",
    #       "image_prompt": "..."
    #   },
    #   ...
    # ]
    #
    # We use image_prompt from every object.
    # The sub-text is kept in MongoDB but the complete scene
    # text remains the narration/voice for the scene.
    # --------------------------------------------------------

    sub_image_prompts = scene["sub_image_prompts"]

    print(
        f"📝 Text: {text[:150]}...",
        flush=True
    )

    print(
        f"🎨 Sub-image prompts: {len(sub_image_prompts)}",
        flush=True
    )

    for prompt_index, item in enumerate(
        sub_image_prompts,
        start=1
    ):
        sub_text = item.get("text", "")
        image_prompt = item["image_prompt"]

        print(
            f"   🖼️ Image {prompt_index}/{len(sub_image_prompts)}",
            flush=True
        )

        if sub_text:
            print(
                f"      📝 Sub-text: {sub_text[:100]}...",
                flush=True
            )

        print(
            f"      🎨 Prompt: {image_prompt[:120]}...",
            flush=True
        )

    # --------------------------------------------------------
    # Generate ONE voice for the complete scene text
    # --------------------------------------------------------

    audio_path = (
        f"audio/a_{index + 1}.mp3"
    )

    voice, word_timings = generate_voice(
        text,
        audio_path
    )

    audio = None

    if voice and os.path.exists(audio_path):
        try:
            audio = AudioFileClip(audio_path)
        except Exception as e:
            print(
                f"⚠️ Generated audio could not be opened: {e}",
                flush=True
            )
            audio = None

    duration = max(
        audio.duration
        if audio
        else 0,
        MIN_DURATION
    )

    print(
        f"⏱️ Scene voice/video duration: {duration:.2f}s",
        flush=True
    )

    if word_timings:
        first_word = word_timings[0]
        last_word = word_timings[-1]

        print(
            f"⏱️ First word: "
            f"{first_word['word']} "
            f"@ {first_word['start']:.3f}s",
            flush=True
        )

        print(
            f"⏱️ Last word: "
            f"{last_word['word']} "
            f"@ {last_word['start']:.3f}s",
            flush=True
        )

    # --------------------------------------------------------
    # Generate all images
    # --------------------------------------------------------

    image_clips = []
    image_count = len(sub_image_prompts)

    print(
        f"🖼️ Total images for scene: {image_count}",
        flush=True
    )

    for prompt_index, item in enumerate(
        sub_image_prompts,
        start=1
    ):

        image_prompt = item["image_prompt"]

        img_path = (
            f"images/s_{scene_number}_{prompt_index}.png"
        )

        print(
            f"🖼️ Generating image "
            f"{prompt_index}/{image_count}",
            flush=True
        )

        img = generate_image(
            image_prompt,
            img_path,
            text
        )

        # ----------------------------------------------------
        # Equal timing distribution
        #
        # Example:
        # Scene voice = 20 sec
        # 2 images
        #
        # Image 1 = 0 -> 10 sec
        # Image 2 = 10 -> 20 sec
        #
        # Example:
        # Scene voice = 30 sec
        # 3 images
        #
        # Image 1 = 0 -> 10 sec
        # Image 2 = 10 -> 20 sec
        # Image 3 = 20 -> 30 sec
        # ----------------------------------------------------

        start_time = (
            duration * (prompt_index - 1) / image_count
        )

        end_time = (
            duration * prompt_index / image_count
        )

        image_duration = (
            end_time - start_time
        )

        print(
            f"   ⏱️ Image {prompt_index}: "
            f"{start_time:.2f}s -> {end_time:.2f}s "
            f"({image_duration:.2f}s)",
            flush=True
        )

        image_clip = create_fullscreen_clip(
            img,
            image_duration,
            prompt_index
        )

        image_clips.append(
            image_clip
        )

    # --------------------------------------------------------
    # Join all images sequentially.
    #
    # No overlap.
    # No black frame between images.
    # Total image duration = complete voice duration.
    # --------------------------------------------------------

    base = concatenate_videoclips(
        image_clips,
        method="compose",
        padding=0
    )

    # --------------------------------------------------------
    # Create subtitle for the complete scene text
    # --------------------------------------------------------

    subtitle_duration = (
        audio.duration
        if audio
        else duration
    )

    subtitle = create_subtitle(
        text,
        subtitle_duration
    )

    final = CompositeVideoClip(
        [
            base,
            subtitle
        ],
        size=VIDEO_SIZE
    )

    # --------------------------------------------------------
    # Add scene voice
    # --------------------------------------------------------

    if audio:

        if audio.duration < duration:

            silence = AudioArrayClip(
                np.zeros(
                    (
                        int(
                            44100
                            * (
                                duration
                                - audio.duration
                            )
                        ),
                        2
                    )
                ),
                fps=44100
            )

            audio = concatenate_audioclips(
                [
                    audio,
                    silence
                ]
            )

        else:

            audio = audio.subclip(
                0,
                duration
            )

        final = final.set_audio(
            audio
        )

    return final


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


# ============================================================
# OPENING TITLE PAGE
# ============================================================

def wrap_title_text(text, font, max_width, draw):
    """
    Wrap the MongoDB story title so it fits cleanly on the 720x1280
    vertical title card.
    """
    words = str(text or "Untitled Story").split()

    if not words:
        return ["Untitled Story"]

    lines = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def create_title_card(title, duration=TITLE_CARD_DURATION):
    """
    Create the opening title page using the story title stored in MongoDB.

    The title page:
      - appears before the first story scene
      - uses the same 720x1280 video size
      - supports Hindi/Devanagari and English titles
      - uses the existing logo when available
      - has no narration/audio
    """

    width, height = VIDEO_SIZE
    title = clean_tts_text(title) or "Untitled Story"

    print(
        f"📖 Creating opening title page: {title}",
        flush=True
    )

    img = Image.new(
        "RGB",
        (width, height),
        (7, 26, 51)
    )

    draw = ImageDraw.Draw(img)

    # Vertical background gradient.
    for y in range(height):
        ratio = y / max(1, height - 1)

        r = int(7 + 4 * ratio)
        g = int(26 + 18 * ratio)
        b = int(51 + 20 * ratio)

        draw.line(
            (0, y, width, y),
            fill=(r, g, b)
        )

    # Decorative glows.
    try:
        glow = Image.new(
            "RGBA",
            (width, height),
            (0, 0, 0, 0)
        )

        glow_draw = ImageDraw.Draw(glow)

        glow_draw.ellipse(
            (-180, -180, 350, 350),
            fill=(0, 123, 255, 55)
        )

        glow_draw.ellipse(
            (
                width - 330,
                height - 330,
                width + 180,
                height + 180
            ),
            fill=(255, 165, 0, 45)
        )

        img = Image.alpha_composite(
            img.convert("RGBA"),
            glow
        ).convert("RGB")

        draw = ImageDraw.Draw(img)

    except Exception:
        pass

    # Main card.
    card_margin = 35
    card_top = 55
    card_bottom = height - 55

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
    small_font = get_unicode_font(24, bold=False)
    title_font = get_unicode_font(54, bold=True)
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
                logo_y = 115

                img.paste(
                    logo,
                    (logo_x, logo_y),
                    logo
                )

        except Exception as e:
            print(
                f"⚠️ Title-card logo failed: {e}",
                flush=True
            )

    draw = ImageDraw.Draw(img)

    # "STORY" label.
    label = "STORY"

    bbox = draw.textbbox(
        (0, 0),
        label,
        font=small_font
    )

    label_width = bbox[2] - bbox[0]

    draw.text(
        (
            (width - label_width) // 2,
            350
        ),
        label,
        font=small_font,
        fill=(220, 235, 250),
        stroke_width=1,
        stroke_fill=(0, 0, 0)
    )

    # MongoDB story title.
    title_lines = wrap_title_text(
        title,
        title_font,
        width - 110,
        draw
    )

    # If the title is very long, reduce font size once.
    if len(title_lines) > 5:
        title_font = get_unicode_font(42, bold=True)

        title_lines = wrap_title_text(
            title,
            title_font,
            width - 100,
            draw
        )

    line_height = 75
    total_title_height = len(title_lines) * line_height

    start_y = (
        455
        - total_title_height // 2
    )

    for index, line_text in enumerate(title_lines):
        bbox = draw.textbbox(
            (0, 0),
            line_text,
            font=title_font
        )

        text_width = bbox[2] - bbox[0]

        x = (width - text_width) // 2
        y = start_y + index * line_height

        draw.text(
            (x, y),
            line_text,
            font=title_font,
            fill=(255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0)
        )

    # Decorative separator.
    separator_y = min(
        690,
        start_y + total_title_height + 70
    )

    draw.rounded_rectangle(
        (
            130,
            separator_y,
            width - 130,
            separator_y + 5
        ),
        radius=3,
        fill=(255, 126, 0)
    )

    # Bottom branding.
    branding = "SMART LEARNING LAB"

    bbox = draw.textbbox(
        (0, 0),
        branding,
        font=footer_font
    )

    branding_width = bbox[2] - bbox[0]

    draw.text(
        (
            (width - branding_width) // 2,
            height - 150
        ),
        branding,
        font=footer_font,
        fill=(205, 220, 235),
        stroke_width=1,
        stroke_fill=(0, 0, 0)
    )

    path = "images/_title_card.png"

    img.save(path)

    print(
        f"✅ Opening title page created: {path}",
        flush=True
    )

    return ImageClip(path).set_duration(duration)


# ============================================================
# BUILD VIDEO
# ============================================================

def build_video(
    scenes,
    title
):
    clips = []

    # Add MongoDB story title page FIRST.
    print(
        f"\\n📖 Adding opening title page: {title}",
        flush=True
    )

    clips.append(
        create_title_card(
            title,
            TITLE_CARD_DURATION
        )
    )

    # Add story scenes after the title page.
    for i, scene in enumerate(scenes):
        clip = create_scene(
            scene,
            i
        )
        clips.append(clip)

    if not clips:
        raise ValueError(
            "❌ No video clips generated"
        )

    # Add final Like / Subscribe / CTA page.
    print(
        f"\n📣 Adding final Like/Subscribe page: {CTA_URL}",
        flush=True
    )

    clips.append(
        create_end_card(END_CARD_DURATION)
    )

    final = concatenate_videoclips(
        clips,
        method="compose",
        padding=0
    )

    print(
        f"🎬 Final video duration: {final.duration:.2f}s",
        flush=True
    )

    final.write_videofile(
        "final_video.mp4",
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        threads=2
    )

    try:
        final.close()
    except Exception:
        pass

    for clip in clips:
        try:
            clip.close()
        except Exception:
            pass


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "🚀 Starting SmartStudyLab video generator...",
        flush=True
    )

    story = None

    try:

        # Atomically claim exactly ONE PENDING story.
        story, scenes = get_story_from_mongodb()

        if not story:
            print(
                "ℹ️ Nothing to process. All stories may already be completed.",
                flush=True
            )
            raise SystemExit(0)

        story_id = story.get("story_id", "unknown")
        title = story.get("title", "Untitled Story")

        print(f"\n📖 TITLE: {title}", flush=True)
        print(f"🆔 STORY ID: {story_id}", flush=True)
        print(f"🎬 SCENES: {len(scenes)}", flush=True)

        # Build video.
        # The title comes directly from the MongoDB story document.
        build_video(
            scenes,
            title
        )

        # Only mark COMPLETED after the final MP4 is successfully written.
        if not os.path.exists("final_video.mp4"):
            raise RuntimeError(
                "❌ Video generation finished but final_video.mp4 was not created"
            )

        video_size = os.path.getsize("final_video.mp4")

        if video_size == 0:
            raise RuntimeError(
                "❌ final_video.mp4 is empty"
            )

        print(
            f"✅ final_video.mp4 created successfully "
            f"({video_size / (1024 * 1024):.2f} MB)",
            flush=True
        )

        # IMPORTANT:
        # Update MongoDB status only.
        # The generated video is NOT stored in MongoDB.
        # Only processing metadata/status is saved.
        status_updated = update_story_status(
            story,
            "COMPLETED",
            {
                "completed_at": datetime.now(timezone.utc),
                "last_error": None
            }
        )

        if not status_updated:
            raise RuntimeError(
                f"❌ Video was created, but MongoDB status could not be "
                f"verified as COMPLETED for story {story_id}"
            )

        print(
            f"\n✅ Story {story_id} marked COMPLETED and verified in MongoDB",
            flush=True
        )

        print(
            "\n✅ Video generation completed!",
            flush=True
        )

    except SystemExit:
        raise

    except Exception as e:

        print(
            f"\n❌ Video generation failed: {e}",
            flush=True
        )

        # Explicitly mark the story FAILED and save the error.
        # This prevents a story from being left indefinitely in PROCESSING.
        if story:
            failed_story_id = (
                story.get("story_id")
                or story.get("id")
                or story.get("ID")
                or "unknown"
            )

            status_updated = update_story_status(
                story,
                "FAILED",
                {
                    "last_error": str(e),
                    "failed_at": datetime.now(timezone.utc)
                }
            )

            if status_updated:
                print(
                    f"🔴 Story {failed_story_id} marked FAILED in MongoDB",
                    flush=True
                )
            else:
                print(
                    f"❌ Could not mark story {failed_story_id} as FAILED",
                    flush=True
                )

        raise

