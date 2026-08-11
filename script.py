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
            image_prompts = scene.get("image_prompts")

            if not text:

                print(
                    "⚠️ Scene skipped: missing text",
                    flush=True
                )

                continue

            # New MongoDB schema uses image_prompts: [...]
            if not isinstance(image_prompts, list) or not image_prompts:

                print(
                    "⚠️ Scene skipped: missing image_prompts array",
                    flush=True
                )

                continue

            # Remove empty/non-string prompts while preserving order.
            image_prompts = [
                prompt.strip()
                for prompt in image_prompts
                if isinstance(prompt, str) and prompt.strip()
            ]

            if not image_prompts:

                print(
                    "⚠️ Scene skipped: image_prompts array is empty",
                    flush=True
                )

                continue

            valid_scenes.append({

                "scene_number": scene.get(
                    "scene_number",
                    len(valid_scenes) + 1
                ),

                "text": text,

                "image_prompts": image_prompts
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
    Generate Edge-TTS audio and collect exact word-boundary timings.

    Returns:
        (audio_path, word_timings)

    word_timings:
        [
            {
                "word": "Raju",
                "start": 0.25,
                "end": 0.60
            },
            ...
        ]
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
                audio_bytes.extend(chunk["data"])

            elif chunk["type"] == "WordBoundary":
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
                "Edge-TTS returned no audio"
            )

        with open(path, "wb") as f:
            f.write(audio_bytes)

        return word_timings

    for attempt in range(3):
        try:
            print(
                f"🎤 Voice attempt {attempt + 1}",
                flush=True
            )

            timings = asyncio.run(tts())

            print(
                f"✅ Voice generated: "
                f"{len(timings)} word timings",
                flush=True
            )

            return path, timings

        except Exception as e:
            print(
                f"⚠️ Voice retry: {e}",
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

    try:
        font = ImageFont.truetype(
            "DejaVuSans-Bold.ttf",
            FONT_SIZE
        )
    except Exception:
        font = ImageFont.load_default()

    # ------------------------------------------------------------
    # Split sentence into words
    # ------------------------------------------------------------

    words = text.split()

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
            try:
                render_font = ImageFont.truetype(
                    "DejaVuSans-Bold.ttf",
                    34
                )
            except Exception:
                render_font = font

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

    # Do not fade each sub-image to black. The image should
    # remain visible for its complete allocated duration.
    return clip


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
    # Image prompts come directly from MongoDB
    # --------------------------------------------------------

    image_prompts = scene["image_prompts"]

    print(
        f"📝 Text: {text[:100]}...",
        flush=True
    )

    print(
        f"🎨 Image prompts: {len(image_prompts)}",
        flush=True
    )

    for prompt_index, prompt in enumerate(image_prompts, start=1):
        print(
            f"   🖼️ Image {prompt_index}/{len(image_prompts)}: "
            f"{prompt[:100]}...",
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

    if word_timings:
        first_word = word_timings[0]
        last_word = word_timings[-1]

        print(
            f"⏱️ Audio duration: {duration:.2f}s",
            flush=True
        )

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

        print(
            f"⏱️ Subtitle timing range: "
            f"{first_word['start']:.3f}s → "
            f"{min(last_word['end'], duration):.3f}s",
            flush=True
        )

    # --------------------------------------------------------
    # Generate ALL images for this text
    #
    # The voice duration belongs to the complete text.
    # If there are N image prompts, the duration is divided
    # equally between the N images.
    #
    # Example:
    #   Voice = 20 sec
    #   2 prompts = 10 sec each
    #
    #   Voice = 30 sec
    #   3 prompts = 10 sec each
    # --------------------------------------------------------

    image_clips = []
    image_count = len(image_prompts)

    print(
        f"🖼️ Total images for scene: {image_count}",
        flush=True
    )

    for prompt_index, image_prompt in enumerate(
        image_prompts,
        start=1
    ):

        img_path = (
            f"images/s_{scene_number}_{prompt_index}.png"
        )

        print(
            f"🖼️ Generating image {prompt_index}/{image_count}",
            flush=True
        )

        img = generate_image(
            image_prompt,
            img_path,
            text
        )

        # Divide the complete voice duration equally
        # across all images.
        start_time = (
            duration * (prompt_index - 1) / image_count
        )

        end_time = (
            duration * prompt_index / image_count
        )

        image_duration = end_time - start_time

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

        image_clips.append(image_clip)

    # Join image clips in the exact same order as image_prompts.
    # Their total duration is exactly the scene duration.
    base = concatenate_videoclips(
        image_clips,
        method="compose",
        padding=0
    )

    # --------------------------------------------------------
    # Create subtitle
    # --------------------------------------------------------

    # Subtitle timing is based on the actual generated voice duration.
    # If voice is shorter than MIN_DURATION, subtitles follow the voice
    # and the remaining video time stays without subtitle.
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

    # Keep scene audio/subtitle timelines aligned.
    # Do not overlap complete scenes because that can overlap
    # audio while subtitles remain on their own scene timeline.
    final = concatenate_videoclips(
        clips,
        method="compose",
        padding=0
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
