import os
import requests
import urllib.parse
import time
import numpy as np
import asyncio
import edge_tts
import nest_asyncio
import json
import re

from groq import Groq
from prompt import build_prompt
from moviepy.editor import *
from moviepy.video.fx.all import fadein, fadeout
from PIL import Image, ImageDraw, ImageFont
from moviepy.audio.AudioClip import AudioArrayClip

# =========================
# FIX ASYNC
# =========================
nest_asyncio.apply()

# =========================
# CONFIG
# =========================
VIDEO_SIZE = (720, 1280)
FPS = 24
MIN_DURATION = 5

DATA_FILE = "indian_story_titles_1000.json"
COUNTER_FILE = "counter.json"

os.makedirs("images", exist_ok=True)
os.makedirs("audio", exist_ok=True)

# =========================
# API KEY
# =========================
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("❌ GROQ_API_KEY not set")

client = Groq(api_key=api_key)

# =========================
# COUNTER
# =========================
def load_counter():
    if not os.path.exists(COUNTER_FILE):
        return 0
    with open(COUNTER_FILE) as f:
        return json.load(f).get("counter", 0)

def save_counter(value):
    with open(COUNTER_FILE, "w") as f:
        json.dump({"counter": value}, f)

def get_topic():
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    counter = load_counter()
    topic_data = data[counter % len(data)]

    title = topic_data.get("title", "")
    story_id = topic_data.get("id", counter)

    print(f"🎯 Topic: {title} (ID: {story_id})", flush=True)

    save_counter(counter + 1)
    return title

# =========================
# STORY (FIXED + RETRY)
# =========================
def get_story():
    topic = get_topic()

    full_prompt = f"""
Use this topic: "{topic}"
{build_prompt}
"""

    for attempt in range(3):
        try:
            print(f"🧠 Generating story (attempt {attempt+1})...", flush=True)

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a viral short video storyteller."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.8
            )

            output = response.choices[0].message.content
            print("📦 RAW OUTPUT:\n", output[:500], flush=True)

            if not output or len(output.strip()) == 0:
                raise ValueError("Empty response")

            match = re.search(r'\{.*\}', output, re.DOTALL)
            if not match:
                raise ValueError("No JSON found")

            clean = match.group(0)
            data = json.loads(clean)

            if "scenes" not in data:
                raise ValueError("Missing scenes key")

            return data["scenes"]

        except Exception as e:
            print("⚠️ Retry LLM:", e, flush=True)
            time.sleep(2)

    print("❌ LLM failed → fallback story", flush=True)

    return [
        {"text": "A hidden story begins...", "image_prompt": "dark village mystery cinematic"},
        {"text": "Something unexpected happens...", "image_prompt": "shock dramatic scene"},
        {"text": "Truth slowly reveals...", "image_prompt": "reveal suspense cinematic"},
        {"text": "Everything changes forever...", "image_prompt": "emotional ending cinematic"}
    ]

# =========================
# IMAGE (MULTI FALLBACK)
# =========================
def generate_image(prompt, path, fallback_text=None):

    # 1️⃣ Pollinations
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"

    for i in range(3):
        try:
            print(f"🖼️ Pollinations attempt {i+1}", flush=True)
            time.sleep(5)

            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
                return path

        except Exception as e:
            print("⚠️ Pollinations retry:", e, flush=True)

    # 2️⃣ Picsum (no key)
    try:
        print("🖼️ Picsum fallback", flush=True)

        picsum_url = f"https://picsum.photos/720/1280?random={int(time.time())}"
        r = requests.get(picsum_url, timeout=15)

        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            return path

    except Exception as e:
        print("⚠️ Picsum failed:", e, flush=True)

    # 3️⃣ DummyImage
    try:
        print("🖼️ Dummy fallback", flush=True)

        text = fallback_text or "Scene"
        dummy_url = f"https://dummyimage.com/720x1280/000/fff&text={urllib.parse.quote(text[:80])}"

        r = requests.get(dummy_url, timeout=10)
        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            return path

    except Exception as e:
        print("⚠️ Dummy failed:", e, flush=True)

    # 4️⃣ Local fallback
    print("🖼️ Local fallback", flush=True)

    try:
        img = Image.new("RGB", VIDEO_SIZE, (20, 20, 20))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 45)
        except:
            font = ImageFont.load_default()

        text = fallback_text or "Scene"

        words = text.split()
        lines, line = [], ""

        for w in words:
            if len(line + w) < 20:
                line += w + " "
            else:
                lines.append(line.strip())
                line = w + " "
        lines.append(line.strip())

        lines = lines[:4]
        y = VIDEO_SIZE[1] // 2 - 100

        for i, l in enumerate(lines):
            bbox = draw.textbbox((0, 0), l, font=font)
            w = bbox[2] - bbox[0]

            draw.text(
                ((VIDEO_SIZE[0] - w) // 2, y + i * 60),
                l,
                font=font,
                fill=(255, 255, 255)
            )

        img.save(path)
        return path

    except Exception as e:
        print("❌ Final fallback failed:", e, flush=True)
        return None

# =========================
# VOICE
# =========================
def generate_voice(text, path):

    async def tts():
        communicate = edge_tts.Communicate(
            text=text,
            voice="en-IN-NeerjaNeural",
            rate="-15%"
        )
        await communicate.save(path)

    for i in range(3):
        try:
            print(f"🎤 Voice attempt {i+1}", flush=True)
            asyncio.run(tts())
            return path
        except Exception as e:
            print("⚠️ Voice retry:", e, flush=True)
            time.sleep(2)

    print("❌ Voice failed", flush=True)
    return None

# =========================
# SUBTITLE
# =========================
def create_subtitle(text, duration):
    img = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
    except:
        font = ImageFont.load_default()

    words = text.split()
    lines, line = [], ""

    for w in words:
        if len(line + w) < 22:
            line += w + " "
        else:
            lines.append(line.strip())
            line = w + " "
    lines.append(line.strip())

    lines = lines[-3:]
    y = VIDEO_SIZE[1] - 220

    for i, l in enumerate(lines):
        bbox = draw.textbbox((0, 0), l, font=font)
        w = bbox[2] - bbox[0]

        draw.text(
            ((VIDEO_SIZE[0] - w) // 2, y + i * 60),
            l,
            font=font,
            fill=(255, 255, 0),
            stroke_width=3,
            stroke_fill=(0, 0, 0)
        )

    return ImageClip(np.array(img)).set_duration(duration)

# =========================
# CLIP
# =========================
def create_fullscreen_clip(image_path, duration, index):
    if image_path is None:
        return ColorClip(VIDEO_SIZE, color=(0, 0, 0)).set_duration(duration)

    clip = ImageClip(image_path)
    clip = clip.resize(height=VIDEO_SIZE[1])

    if clip.w < VIDEO_SIZE[0]:
        clip = clip.resize(width=VIDEO_SIZE[0])

    clip = clip.crop(
        x_center=clip.w / 2,
        y_center=clip.h / 2,
        width=VIDEO_SIZE[0],
        height=VIDEO_SIZE[1]
    )

    clip = clip.set_duration(duration)
    return fadein(clip, 0.8).fx(fadeout, 0.8)

# =========================
# SCENE
# =========================
def create_scene(scene, index):
    print(f"\n🎬 Scene {index}", flush=True)

    audio_path = f"audio/a_{index}.mp3"
    voice = generate_voice(scene["text"], audio_path)

    audio = AudioFileClip(audio_path) if voice else None
    duration = max(audio.duration if audio else 0, MIN_DURATION)

    img_path = f"images/s_{index}.png"
    img = generate_image(scene["image_prompt"], img_path, scene["text"])

    base = create_fullscreen_clip(img, duration, index)
    subtitle = create_subtitle(scene["text"], duration)

    final = CompositeVideoClip(
        [base, subtitle.set_position(("center", "bottom"))],
        size=VIDEO_SIZE
    )

    if audio:
        if audio.duration < duration:
            silence = AudioArrayClip(
                np.zeros((int(44100 * (duration - audio.duration)), 2)),
                fps=44100
            )
            audio = concatenate_audioclips([audio, silence])
        else:
            audio = audio.subclip(0, duration)

        final = final.set_audio(audio)

    return final

# =========================
# BUILD VIDEO
# =========================
def build_video(scenes):
    clips = []

    for i, s in enumerate(scenes):
        clip = create_scene(s, i)

        if i > 0:
            clip = clip.crossfadein(1.0)

        clips.append(clip)

    final = concatenate_videoclips(clips, method="compose", padding=-1)

    final.write_videofile(
        "final_video.mp4",
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        threads=2
    )

# =========================
# RUN
# =========================
scenes = get_story()
print("✅ Scenes generated:", len(scenes), flush=True)

build_video(scenes)