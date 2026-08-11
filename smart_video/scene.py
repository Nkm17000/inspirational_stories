"""Scene construction: TTS + images + subtitles."""

import os
import numpy as np
from moviepy.editor import AudioFileClip, concatenate_videoclips, concatenate_audioclips, CompositeVideoClip
from moviepy.audio.AudioClip import AudioArrayClip

from .config import MIN_DURATION, VIDEO_SIZE
from .voice import clean_tts_text, generate_voice
from .image_generator import generate_image
from .branding import create_fullscreen_clip
from .subtitles import create_subtitle

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
