import os
import requests
import urllib.parse
import time
import numpy as np
import asyncio
import edge_tts
import nest_asyncio

from moviepy.editor import *
from moviepy.video.fx.all import fadein, fadeout
from PIL import Image, ImageDraw, ImageFont
from moviepy.audio.AudioClip import AudioArrayClip

# ✅ Fix async issue
nest_asyncio.apply()

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
CHARACTER = "Raju, a 10-year-old Indian village boy, short hair, wearing dusty simple clothes, same face, consistent character"
FATHER = "Raju's father, poor Indian farmer, thin, wearing dhoti and turban, same face"
STYLE = "cinematic, realistic, 4k, emotional lighting, same character"

# =========================
# STORY
# =========================
scenes = [
    {"text": "You won’t believe what this son did...", "image_prompt": f"{CHARACTER}, {STYLE}"},
    {"text": "Raju lived in a small village with his father...", "image_prompt": f"{CHARACTER} with {FATHER}, {STYLE}"},
    {"text": "His father worked day and night in the fields...", "image_prompt": f"{FATHER} working hard, {STYLE}"},
    {"text": "But Raju never cared about his father's struggles...", "image_prompt": f"{CHARACTER} ignoring {FATHER}, {STYLE}"},
    {"text": "He spent his time playing and wasting his days...", "image_prompt": f"{CHARACTER} playing, {STYLE}"},
    {"text": "One day... his father fell seriously ill...", "image_prompt": f"{FATHER} sick, {STYLE}"},
    {"text": "For the first time... Raju felt fear and guilt...", "image_prompt": f"{CHARACTER} crying, {STYLE}"},
    {"text": "He realized how much his father had sacrificed...", "image_prompt": f"{CHARACTER} emotional flashback, {STYLE}"},
    {"text": "The next morning... everything changed...", "image_prompt": f"{CHARACTER} determined, sunrise, {STYLE}"},
    {"text": "Raju went to the fields and started working hard...", "image_prompt": f"{CHARACTER} working, {STYLE}"},
]

# =========================
# IMAGE GENERATION
# =========================
def generate_image(prompt, path):
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"

    for i in range(3):
        try:
            print(f"🖼️ Image attempt {i+1}", flush=True)
            time.sleep(3)

            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
                return path

        except Exception as e:
            print("⚠️ Image retry:", e, flush=True)
            time.sleep(2)

    print("❌ Image failed, using fallback", flush=True)
    return None


# =========================
# VOICE (SAFE ASYNC)
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

    print("❌ Voice failed, skipping audio", flush=True)
    return None


# =========================
# VIDEO CLIP
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

    # 🎥 Motion
    if index % 4 == 0:
        clip = clip.resize(lambda t: 1 + 0.1 * (t / duration))
    elif index % 4 == 1:
        clip = clip.set_position(lambda t: (-30 * t, 'center'))
    elif index % 4 == 2:
        clip = clip.resize(lambda t: 1.1 - 0.1 * (t / duration))
    else:
        clip = clip.set_position(lambda t: ('center', -20 * t))

    clip = clip.set_duration(duration)
    clip = fadein(clip, 0.8).fx(fadeout, 0.8)

    return clip


# =========================
# SUBTITLE (FONT 60 ✅)
# =========================
def create_subtitle(text, duration):
    img = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 60)  # ✅ reduced
    except:
        font = ImageFont.load_default()

    words = text.split()
    lines, line = [], ""

    for w in words:
        if len(line + w) < 20:
            line += w + " "
        else:
            lines.append(line.strip())
            line = w + " "
    lines.append(line.strip())

    lines = lines[-2:]
    y = VIDEO_SIZE[1] - 180

    for i, l in enumerate(lines):
        bbox = draw.textbbox((0, 0), l, font=font)
        w = bbox[2] - bbox[0]

        draw.text(
            ((VIDEO_SIZE[0] - w) // 2, y + i * 70),
            l,
            font=font,
            fill=(255, 255, 0),
            stroke_width=4,
            stroke_fill=(0, 0, 0)
        )

    return ImageClip(np.array(img)).set_duration(duration)


# =========================
# SCENE
# =========================
def create_scene(scene, index):
    print(f"\n🎬 Scene {index}", flush=True)

    try:
        audio_path = f"audio/a_{index}.mp3"
        voice = generate_voice(scene["text"], audio_path)

        audio = AudioFileClip(audio_path) if voice else None
        duration = max(audio.duration if audio else 0, MIN_DURATION)

        img_path = f"images/s_{index}.png"
        img = generate_image(scene["image_prompt"], img_path)

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

    except Exception as e:
        print(f"❌ Scene {index} failed:", e, flush=True)
        return None


# =========================
# BUILD VIDEO
# =========================
def build_video(scenes):
    clips = []

    for i, s in enumerate(scenes):
        clip = create_scene(s, i)

        if clip:
            if i > 0:
                clip = clip.crossfadein(1.0)
            clips.append(clip)

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
        threads=2   # ⚡ faster
    )


# =========================
# RUN
# =========================
build_video(scenes)