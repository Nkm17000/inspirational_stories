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
# 🎭 CONSISTENT CHARACTERS
# =========================
CHARACTER = "Raju, a 10-year-old Indian village boy, short hair, wearing dusty simple clothes, same face, consistent character"
FATHER = "Raju's father, poor Indian farmer, thin, wearing dhoti and turban, same face"

STYLE = "cinematic, realistic, 4k, emotional lighting, same character"

# =========================
# STORY
# =========================
# =========================
# STORY
# =========================
scenes = [
{
"text": "You won’t believe what this son did...",
"image_prompt": f"{CHARACTER}, {STYLE}"
},

{
"text": "Raju lived in a small village with his father...",
"image_prompt": f"{CHARACTER} with {FATHER} in village hut, {STYLE}"
},

{
"text": "His father worked day and night in the fields...",
"image_prompt": f"{FATHER} working in hot sun, खेत, sweating मेहनत, {STYLE}"
},

{
"text": "But Raju never cared about his father's struggles...",
"image_prompt": f"{CHARACTER} ignoring {FATHER}, sitting idle, {STYLE}"
},

{
"text": "He spent his time playing and wasting his days...",
"image_prompt": f"{CHARACTER} playing while {FATHER} working in background, {STYLE}"
},

{
"text": "One day... his father fell seriously ill...",
"image_prompt": f"{FATHER} sick lying on bed, {CHARACTER} shocked, emotional, {STYLE}"
},

{
"text": "For the first time... Raju felt fear and guilt...",
"image_prompt": f"{CHARACTER} crying near {FATHER}, emotional close scene, {STYLE}"
},

{
"text": "He realized how much his father had sacrificed...",
"image_prompt": f"{CHARACTER} remembering past मेहनत of {FATHER}, emotional flashback, {STYLE}"
},

{
"text": "The next morning... everything changed...",
"image_prompt": f"{CHARACTER} waking early with determination, sunrise, {STYLE}"
},

{
"text": "Raju went to the fields and started working hard...",
"image_prompt": f"{CHARACTER} working in farm like {FATHER}, मेहनत, {STYLE}"
},

{
"text": "Slowly... he took responsibility of the family...",
"image_prompt": f"{CHARACTER} taking care of sick {FATHER}, emotional, {STYLE}"
},

{
"text": "Days passed... his father finally recovered...",
"image_prompt": f"{FATHER} recovering and smiling at {CHARACTER}, {STYLE}"
},

{
"text": "Seeing his son change... his father felt proud...",
"image_prompt": f"{FATHER} proud emotional look at {CHARACTER}, {STYLE}"
},

{
"text": "Together... they worked and rebuilt their life...",
"image_prompt": f"{CHARACTER} and {FATHER} farming together happily, sunset, {STYLE}"
},

{
"text": "And Raju never ignored his father again...",
"image_prompt": f"{CHARACTER} respecting {FATHER}, emotional happy ending, {STYLE}"
}
]

# =========================
# IMAGE
# =========================
def generate_image(prompt, path):
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"

    for i in range(3):
        try:
            print(f"🖼️ Image attempt {i+1}")
            time.sleep(5)  # ✅ API GAP

            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
                return path
        except Exception as e:
            print("Retry:", e)
            time.sleep(3)

    raise Exception("Image failed")

# =========================
# 🎤 HUMAN VOICE (EDGE TTS)
# =========================
def generate_voice(text, path):

    async def tts():
        communicate = edge_tts.Communicate(
            text=text,
            voice="en-IN-NeerjaNeural",
            rate="-15%"  # 🔥 storytelling feel
        )
        await communicate.save(path)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(tts())

    return path

# =========================
# 🎬 CINEMATIC CAMERA
# =========================
def create_fullscreen_clip(image_path, duration, index):
    clip = ImageClip(image_path)

    clip = clip.resize(height=VIDEO_SIZE[1])
    if clip.w < VIDEO_SIZE[0]:
        clip = clip.resize(width=VIDEO_SIZE[0])

    clip = clip.crop(
        x_center=clip.w/2,
        y_center=clip.h/2,
        width=VIDEO_SIZE[0],
        height=VIDEO_SIZE[1]
    )

    # 🎥 Dynamic motion (NO slideshow feel)
    if index % 4 == 0:
        clip = clip.resize(lambda t: 1 + 0.1*(t/duration))
    elif index % 4 == 1:
        clip = clip.set_position(lambda t: (-30*t, 'center'))
    elif index % 4 == 2:
        clip = clip.resize(lambda t: 1.1 - 0.1*(t/duration))
    else:
        clip = clip.set_position(lambda t: ('center', -20*t))

    clip = clip.set_duration(duration)

    # 🎬 Smooth fade
    clip = fadein(clip, 0.8).fx(fadeout, 0.8)

    return clip

# =========================
# 🔥 SUBTITLE (BIG + BOTTOM)
# =========================
def create_subtitle(text, duration):
    img = Image.new("RGBA", VIDEO_SIZE, (0,0,0,0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 85)
    except:
        font = ImageFont.load_default()

    words = text.split()
    lines = []
    line = ""

    for w in words:
        if len(line + w) < 18:
            line += w + " "
        else:
            lines.append(line.strip())
            line = w + " "
    lines.append(line.strip())

    lines = lines[-2:]

    y = VIDEO_SIZE[1] - 180

    for i, l in enumerate(lines):
        bbox = draw.textbbox((0,0), l, font=font)
        w = bbox[2] - bbox[0]

        draw.text(
            ((VIDEO_SIZE[0]-w)//2, y + i*90),
            l,
            font=font,
            fill=(255,255,0),
            stroke_width=6,
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

    base = create_fullscreen_clip(img_path, duration, index)
    subtitle = create_subtitle(scene["text"], duration)

    final = CompositeVideoClip(
        [base, subtitle.set_position(("center", "bottom"))],
        size=VIDEO_SIZE
    )

    if audio.duration < duration:
        silence = AudioArrayClip(
            np.zeros((int(44100*(duration-audio.duration)),2)),
            fps=44100
        )
        audio = concatenate_audioclips([audio, silence])
    else:
        audio = audio.subclip(0, duration)

    return final.set_audio(audio)

# =========================
# BUILD VIDEO
# =========================
def build_video(scenes):
    clips = []

    for i, s in enumerate(scenes):
        clip = create_scene(s, i)

        # 🔥 cinematic transition
        if i > 0:
            clip = clip.crossfadein(1.0)

        clips.append(clip)

    final = concatenate_videoclips(
        clips,
        method="compose",
        padding=-1   # overlap
    )

    final.write_videofile(
        "final_video.mp4",
        fps=FPS,
        codec="libx264",
        audio_codec="aac"
    )

# =========================
# RUN
# =========================
build_video(scenes)