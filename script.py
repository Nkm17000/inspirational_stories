import os
import requests
import time
import random
import numpy as np

from moviepy.editor import *
from PIL import Image

# ✅ FIX for Pillow 10+
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# =========================
# CONFIG
# =========================
VIDEO_SIZE = (720, 1280)
FPS = 24
SCENE_DURATION = 3
MAX_RETRY = 3
IMAGE_TIMEOUT = 10

# =========================
# SAMPLE SCENES
# =========================
scenes = [
    {"text": "A peaceful village at sunrise", "image_prompt": "village sunrise nature"},
    {"text": "A farmer working in the field", "image_prompt": "farmer खेत working"},
    {"text": "A happy child playing", "image_prompt": "happy child playing outdoor"},
]

# =========================
# IMAGE FETCH WITH TIMEOUT
# =========================
def fetch_image(prompt, index):
    for attempt in range(MAX_RETRY):
        try:
            print(f"🖼️ Scene {index} - Image attempt {attempt+1}", flush=True)

            url = f"https://image.pollinations.ai/prompt/{prompt}"
            response = requests.get(url, timeout=IMAGE_TIMEOUT)

            if response.status_code == 200:
                file_path = f"image_{index}.jpg"
                with open(file_path, "wb") as f:
                    f.write(response.content)

                print(f"✅ Image saved: {file_path}", flush=True)
                return file_path

        except Exception as e:
            print(f"❌ Image error: {e}", flush=True)

        time.sleep(2)

    print("⚠️ Using fallback image", flush=True)
    return None


# =========================
# CREATE VIDEO CLIP
# =========================
def create_clip(image_path, duration, index):
    try:
        if image_path and os.path.exists(image_path):
            clip = ImageClip(image_path)
        else:
            print("⚠️ Creating fallback blank clip", flush=True)
            clip = ColorClip(size=VIDEO_SIZE, color=(0, 0, 0))

        clip = clip.set_duration(duration)

        # Resize safely
        clip = clip.resize(height=VIDEO_SIZE[1])

        return clip

    except Exception as e:
        print(f"❌ Clip error: {e}", flush=True)
        return ColorClip(size=VIDEO_SIZE, color=(0, 0, 0)).set_duration(duration)


# =========================
# CREATE SCENE
# =========================
def create_scene(scene, index):
    print(f"🎬 Creating Scene {index}", flush=True)

    img_path = fetch_image(scene["image_prompt"], index)

    clip = create_clip(img_path, SCENE_DURATION, index)

    print(f"✅ Scene {index} ready", flush=True)
    return clip


# =========================
# BUILD VIDEO
# =========================
def build_video(scenes):
    print("🚀 Starting video build...", flush=True)

    clips = []

    for i, s in enumerate(scenes):
        try:
            clip = create_scene(s, i)
            clips.append(clip)
        except Exception as e:
            print(f"❌ Scene {i} failed: {e}", flush=True)

    if not clips:
        raise Exception("No clips created!")

    final = concatenate_videoclips(clips, method="compose")

    print("🎬 Rendering video...", flush=True)

    final.write_videofile(
        "final_video.mp4",
        fps=FPS,
        codec="libx264",
        audio=False
    )

    print("✅ Video created: final_video.mp4", flush=True)


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    start_time = time.time()

    try:
        print("🔥 Script started", flush=True)

        build_video(scenes)

        print(f"⏱️ Total time: {round(time.time() - start_time, 2)} sec", flush=True)

    except Exception as e:
        print(f"💥 Script failed: {e}", flush=True)
        exit(1)