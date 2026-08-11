import os
import requests
import urllib.parse
import time
import numpy as np
import asyncio
import edge_tts
import nest_asyncio

from pymongo import MongoClient
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

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")

DATABASE_NAME = "storydb"
COLLECTION_NAME = "story_scenes"

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
# GET STORY FROM MONGODB
# ============================================================

def get_story_from_mongodb():

    client, collection = get_mongodb_collection()

    try:

        # ----------------------------------------------------
        # Get specific story
        # ----------------------------------------------------

        if STORY_ID:

            print(
                f"🔎 Searching story_id: {STORY_ID}",
                flush=True
            )

            story = collection.find_one({
                "story_id": STORY_ID
            })

        # ----------------------------------------------------
        # Otherwise get first story
        # ----------------------------------------------------

        else:

            print(
                "🔎 STORY_ID not provided.",
                flush=True
            )

            print(
                "📖 Getting first story from MongoDB...",
                flush=True
            )

            story = collection.find_one({})

        # ----------------------------------------------------
        # Story not found
        # ----------------------------------------------------

        if not story:

            raise ValueError(
                "❌ No story found in MongoDB"
            )

        # ----------------------------------------------------
        # Read title directly from MongoDB
        # ----------------------------------------------------

        title = story.get(
            "title",
            "Untitled Story"
        )

        story_id = story.get(
            "story_id",
            "unknown"
        )

        print(
            f"\n📖 Story ID: {story_id}",
            flush=True
        )

        print(
            f"📖 Title: {title}",
            flush=True
        )

        # ----------------------------------------------------
        # Get scenes
        # ----------------------------------------------------

        scenes = story.get(
            "scenes",
            []
        )

        if not scenes:

            raise ValueError(
                "❌ Story contains no scenes"
            )

        print(
            f"🎬 Total scenes: {len(scenes)}",
            flush=True
        )

        # ----------------------------------------------------
        # Validate scenes
        # ----------------------------------------------------

        valid_scenes = []

        for scene in scenes:

            text = scene.get("text")
            image_prompt = scene.get("image_prompt")

            if not text:

                print(
                    "⚠️ Scene skipped: missing text",
                    flush=True
                )

                continue

            if not image_prompt:

                print(
                    "⚠️ Scene skipped: missing image_prompt",
                    flush=True
                )

                continue

            valid_scenes.append({

                "scene_number": scene.get(
                    "scene_number",
                    len(valid_scenes) + 1
                ),

                "text": text,

                "image_prompt": image_prompt
            })

        if not valid_scenes:

            raise ValueError(
                "❌ No valid scenes found"
            )

        print(
            f"✅ Valid scenes: {len(valid_scenes)}",
            flush=True
        )

        return story, valid_scenes

    finally:

        client.close()


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

        try:

            font = ImageFont.truetype(
                "DejaVuSans-Bold.ttf",
                45
            )

        except:

            font = ImageFont.load_default()

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

def generate_voice(
    text,
    path
):
    """
    Generate voice and collect word-level timing from Edge-TTS.

    Returns:
        (audio_path, word_timings)

    word_timings example:
        {
            "word": "Raju",
            "start": 0.25,
            "end": 0.60
        }
    """

    async def tts():

        communicate = edge_tts.Communicate(
            text=text,
            voice="en-IN-NeerjaNeural",
            rate="-15%"
        )

        audio_bytes = bytearray()
        word_timings = []

        async for chunk in communicate.stream():

            if chunk["type"] == "audio":

                audio_bytes.extend(
                    chunk["data"]
                )

            elif chunk["type"] == "WordBoundary":

                offset = chunk.get("offset", 0)
                word_duration = chunk.get("duration", 0)
                word = chunk.get("text", "").strip()

                if not word:
                    continue

                # Edge-TTS uses 100-nanosecond units.
                start_seconds = offset / 10_000_000
                end_seconds = (
                    offset + word_duration
                ) / 10_000_000

                word_timings.append(
                    {
                        "word": word,
                        "start": start_seconds,
                        "end": end_seconds
                    }
                )

        if not audio_bytes:
            raise RuntimeError(
                "Edge-TTS returned no audio"
            )

        with open(path, "wb") as f:
            f.write(audio_bytes)

        return word_timings

    for i in range(3):

        try:

            print(
                f"🎤 Voice attempt {i + 1}",
                flush=True
            )

            timings = asyncio.run(tts())

            print(
                f"✅ Voice generated: {len(timings)} word timings",
                flush=True
            )

            return path, timings

        except Exception as e:

            print(
                "⚠️ Voice retry:",
                e,
                flush=True
            )

            time.sleep(2)

    print(
        "❌ Voice failed",
        flush=True
    )

    return None, []

# ============================================================
# SUBTITLE
# ============================================================

def create_subtitle(
    text,
    duration,
    word_timings
):
    """
    Create progressive subtitles synchronized with the voice.

    The complete sentence is displayed progressively instead of
    keeping only the last three lines.

    Each subtitle chunk contains a small number of words and is
    timed using the WordBoundary timestamps returned by Edge-TTS.
    """

    # --------------------------------------------------------
    # FALLBACK: if Edge-TTS did not provide timings
    # --------------------------------------------------------

    if not word_timings:

        print(
            "⚠️ Word timings unavailable - using static subtitle",
            flush=True
        )

        img = Image.new(
            "RGBA",
            VIDEO_SIZE,
            (0, 0, 0, 0)
        )

        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype(
                "DejaVuSans-Bold.ttf",
                40
            )
        except:
            font = ImageFont.load_default()

        words = text.split()
        lines = []
        line = ""

        for word in words:

            test_line = (
                f"{line} {word}".strip()
            )

            if len(test_line) <= 22:
                line = test_line

            else:

                if line:
                    lines.append(line)

                line = word

        if line:
            lines.append(line)

        lines = lines[-3:]

        y = VIDEO_SIZE[1] - 220

        for i, line_text in enumerate(lines):

            bbox = draw.textbbox(
                (0, 0),
                line_text,
                font=font
            )

            width = bbox[2] - bbox[0]

            draw.text(
                (
                    (VIDEO_SIZE[0] - width) // 2,
                    y + i * 60
                ),
                line_text,
                font=font,
                fill=(255, 255, 0),
                stroke_width=3,
                stroke_fill=(0, 0, 0)
            )

        return ImageClip(
            np.array(img)
        ).set_duration(duration)

    # --------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------

    FONT_SIZE = 40
    MAX_CHARS_PER_LINE = 22
    MAX_LINES = 3

    # Number of words shown at a time.
    # This gives a running-subtitle effect while remaining readable.
    WORDS_PER_CHUNK = 5

    subtitle_clips = []

    # --------------------------------------------------------
    # Create timed chunks
    # --------------------------------------------------------

    chunks = []
    current_chunk = []

    for timing in word_timings:

        current_chunk.append(timing)

        word = timing["word"].strip()

        # End a subtitle after a few words or punctuation.
        punctuation_break = word.endswith(
            (".", "!", "?", ";", ":")
        )

        if (
            len(current_chunk) >= WORDS_PER_CHUNK
            or punctuation_break
        ):
            chunks.append(current_chunk)
            current_chunk = []

    if current_chunk:
        chunks.append(current_chunk)

    # --------------------------------------------------------
    # Render each timed subtitle
    # --------------------------------------------------------

    for chunk_index, chunk in enumerate(chunks):

        if not chunk:
            continue

        start_time = chunk[0]["start"]

        # The next chunk starts exactly when the next group
        # begins speaking.
        if chunk_index + 1 < len(chunks):

            end_time = (
                chunks[chunk_index + 1][0]["start"]
            )

        else:

            end_time = duration

        # Clamp timing to actual video duration.
        start_time = max(
            0,
            min(start_time, duration)
        )

        end_time = max(
            start_time,
            min(end_time, duration)
        )

        if end_time <= start_time:
            continue

        # ----------------------------------------------------
        # Build subtitle text
        # ----------------------------------------------------

        chunk_text = " ".join(
            item["word"]
            for item in chunk
        ).strip()

        words = chunk_text.split()

        lines = []
        line = ""

        for word in words:

            test_line = (
                f"{line} {word}".strip()
            )

            if len(test_line) <= MAX_CHARS_PER_LINE:

                line = test_line

            else:

                if line:
                    lines.append(line)

                line = word

        if line:
            lines.append(line)

        # Maximum 3 lines.
        lines = lines[:MAX_LINES]

        # ----------------------------------------------------
        # Create transparent subtitle image
        # ----------------------------------------------------

        img = Image.new(
            "RGBA",
            VIDEO_SIZE,
            (0, 0, 0, 0)
        )

        draw = ImageDraw.Draw(img)

        try:

            font = ImageFont.truetype(
                "DejaVuSans-Bold.ttf",
                FONT_SIZE
            )

        except:

            font = ImageFont.load_default()

        y = VIDEO_SIZE[1] - 220

        for line_index, line_text in enumerate(lines):

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
                    y + line_index * 60
                ),
                line_text,
                font=font,
                fill=(255, 255, 0),
                stroke_width=3,
                stroke_fill=(0, 0, 0)
            )

        subtitle_clip = (
            ImageClip(np.array(img))
            .set_start(start_time)
            .set_duration(
                end_time - start_time
            )
            .set_position(
                ("center", "bottom")
            )
        )

        subtitle_clips.append(
            subtitle_clip
        )

    # --------------------------------------------------------
    # Final subtitle composition
    # --------------------------------------------------------

    if not subtitle_clips:

        return ImageClip(
            np.zeros(
                (
                    VIDEO_SIZE[1],
                    VIDEO_SIZE[0],
                    4
                ),
                dtype=np.uint8
            )
        ).set_duration(duration)

    return CompositeVideoClip(
        subtitle_clips,
        size=VIDEO_SIZE
    ).set_duration(duration)

# ============================================================
# FULLSCREEN IMAGE CLIP
# ============================================================

def create_fullscreen_clip(
    image_path,
    duration,
    index
):

    if image_path is None:

        return ColorClip(
            VIDEO_SIZE,
            color=(0, 0, 0)
        ).set_duration(duration)

    clip = ImageClip(
        image_path
    )

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

    clip = clip.set_duration(
        duration
    )

    return fadein(
        clip,
        0.8
    ).fx(
        fadeout,
        0.8
    )


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
    # Text comes directly from MongoDB
    # --------------------------------------------------------

    text = scene["text"]

    # --------------------------------------------------------
    # Image prompt comes directly from MongoDB
    # --------------------------------------------------------

    image_prompt = scene["image_prompt"]

    print(
        f"📝 Text: {text[:100]}...",
        flush=True
    )

    print(
        f"🎨 Image prompt: {image_prompt[:100]}...",
        flush=True
    )

    # --------------------------------------------------------
    # Generate voice
    # --------------------------------------------------------

    audio_path = (
        f"audio/a_{index + 1}.mp3"
    )

    voice, word_timings = generate_voice(
        text,
        audio_path
    )

    audio = (
        AudioFileClip(audio_path)
        if voice
        else None
    )

    duration = max(
        audio.duration
        if audio
        else 0,
        MIN_DURATION
    )

    # --------------------------------------------------------
    # Generate image
    # --------------------------------------------------------

    img_path = (
        f"images/s_{index + 1}.png"
    )

    img = generate_image(
        image_prompt,
        img_path,
        text
    )

    # --------------------------------------------------------
    # Create image clip
    # --------------------------------------------------------

    base = create_fullscreen_clip(
        img,
        duration,
        index
    )

    # --------------------------------------------------------
    # Create subtitle
    # --------------------------------------------------------

    subtitle = create_subtitle(
        text,
        duration,
        word_timings
    )

    final = CompositeVideoClip(
        [
            base,
            subtitle.set_position(
                ("center", "bottom")
            )
        ],
        size=VIDEO_SIZE
    )

    # --------------------------------------------------------
    # Add audio
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
# BUILD VIDEO
# ============================================================

def build_video(
    scenes
):

    clips = []

    for i, scene in enumerate(scenes):

        clip = create_scene(
            scene,
            i
        )

        if i > 0:

            clip = clip.crossfadein(
                1.0
            )

        clips.append(clip)

    if not clips:

        raise ValueError(
            "❌ No video clips generated"
        )

    final = concatenate_videoclips(
        clips,
        method="compose",
        padding=-1
    )

    final.write_videofile(
        "final_video.mp4",
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        threads=2
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "🚀 Starting SmartStudyLab video generator...",
        flush=True
    )

    # --------------------------------------------------------
    # Get everything from MongoDB
    # --------------------------------------------------------

    story, scenes = get_story_from_mongodb()

    # --------------------------------------------------------
    # Title also comes from MongoDB
    # --------------------------------------------------------

    title = story.get(
        "title",
        "Untitled Story"
    )

    print(
        f"\n📖 TITLE: {title}",
        flush=True
    )

    print(
        f"🎬 SCENES: {len(scenes)}",
        flush=True
    )

    # --------------------------------------------------------
    # Build video
    # --------------------------------------------------------

    build_video(
        scenes
    )

    print(
        "\n✅ Video generation completed!",
        flush=True
    )