import os
import requests
import urllib.parse
import time
import numpy as np
import asyncio
import edge_tts
import nest_asyncio
import subprocess
import sys

from moviepy.editor import *
from moviepy.video.fx.all import fadein, fadeout
from PIL import Image, ImageDraw, ImageFont
from moviepy.audio.AudioClip import AudioArrayClip

# =========================
# ✅ FIX FOR CI
# =========================

nest_asyncio.apply()

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        print("❌ FFmpeg not found!")
        sys.exit(1)

check_ffmpeg()

# =========================
# CONFIG
# =========================

VIDEO_SIZE = (720, 1280)
FPS = 24
MIN_DURATION = 5

os.makedirs("images", exist_ok=True)
os.makedirs("audio", exist_ok=True)

# =========================
# CHARACTERS
# =========================

CHARACTER = "Raju, a 10-year-old Indian village boy, short hair, wearing dusty simple clothes, same face"
FATHER = "Raju's father, poor Indian farmer, thin, wearing dhoti and turban, same face"
STYLE = "cinematic, realistic, emotional lighting, 4k"

# =========================
# STORY
# =========================

scenes = [
    {"text": "You won’t believe what this son did...", "image_prompt": f"{CHARACTER}, {STYLE}"},
    {"text": "Raju lived in a small village with his father...", "image_prompt": f"{CHARACTER} with {FATHER} in village hut, {STYLE}"},
    {"text": "His father worked day and night in the fields...", "image_prompt": f"{FATHER} working in hot sun, खेत, मेहनत, {STYLE}"},
    {"text": "But Raju never cared about his father's struggles...", "image_prompt": f"{CHARACTER} ignoring {FATHER}, {STYLE}"},
    {"text": "One day... his father fell seriously ill...", "image_prompt": f"{FATHER} sick, {CHARACTER} emotional, {STYLE}"},
    {"text": "Raju realized his mistake and changed...", "image_prompt": f"{CHARACTER} working hard in fields, {STYLE}"},
    {"text": "His father recovered and felt proud...", "image_prompt": f"{FATHER} smiling at {CHARACTER}, {STYLE}"}
]

# =========================
# IMAGE
# =========================

def generate_image(prompt, path):
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"

    for i in range(3):
        try:
            print(f"🖼️ Image attempt {i+1}")
            time.sleep(2)

            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
                return path
        except Exception as e:
            print("Retry:", e)
            time.sleep(2)

    raise Exception("Image generation failed")

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

    asyncio.run(tts())
    return path

# =========================
# VIDEO CLIP
# =========================

def create_clip(image_path, duration, index):
    clip = ImageClip(image_path)

    clip = clip.resize(height=VIDEO_SIZE[1])
    clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2,
                     width=VIDEO_SIZE[0], height=VIDEO_SIZE[1])

    # Motion
    if index % 2 == 0:
        clip = clip.resize(lambda t: 1 + 0.05*(t/duration))
    else:
        clip = clip.set_position(lambda t: ('center', -20*t))

    clip = clip.set_duration(duration)
    clip = fadein(clip, 0.5).fx(fadeout, 0.5)

    return clip

# =========================
# SUBTITLE
# =========================

def create_subtitle(text, duration):
    img = Image.new("RGBA", VIDEO_SIZE, (0,0,0,0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 70)
    except:
        font = ImageFont.load_default()

    draw.text(
        (50, VIDEO_SIZE[1] - 200),
        text,
        font=font,
        fill=(255,255,0),
        stroke_width=4,
        stroke_fill=(0,0,0)
    )

    return ImageClip(np.array(img)).set_duration(duration)

# =========================
# SCENE
# =========================

def create_scene(scene, index):
    print(f"\n🎬 Scene {index}")

    audio_path = f"audio/a_{index}.mp3"
    generate_voice(scene["text"], audio_path)

    audio = AudioFileClip(audio_path)
    duration = max(audio.duration, MIN_DURATION)

    img_path = f"images/s_{index}.png"
    generate_image(scene["image_prompt"], img_path)

    base = create_clip(img_path, duration, index)
    subtitle = create_subtitle(scene["text"], duration)

    video = CompositeVideoClip(
        [base, subtitle.set_position(("center", "bottom"))],
        size=VIDEO_SIZE
    )

    return video.set_audio(audio)

# =========================
# BUILD VIDEO
# =========================

def build_video(scenes):
    clips = []

    for i, s in enumerate(scenes):
        clip = create_scene(s, i)

        if i > 0:
            clip = clip.crossfadein(0.5)

        clips.append(clip)

    final = concatenate_videoclips(clips, method="compose", padding=-0.5)

    final.write_videofile(
        "final_video.mp4",
        fps=FPS,
        codec="libx264",
        audio_codec="aac"
    )

# =========================
# RUN
# =========================

if __name__ == "__main__":
    build_video(scenes)