"""Scene construction: TTS + images + subtitles."""

import os
import numpy as np

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    concatenate_audioclips,
)
from moviepy.audio.AudioClip import AudioArrayClip

from .config import MIN_DURATION, VIDEO_SIZE
from .voice import clean_tts_text, generate_voice
from .image_generator import generate_image
from .branding import create_fullscreen_clip
from .subtitles import create_subtitle


# ============================================================
# CINEMATIC IMAGE MOTION
# ============================================================

def _apply_ken_burns(
    clip,
    duration,
    motion_index,
):
    """
    Add subtle cinematic camera movement to a still image.

    The source clip is first slightly enlarged and then slowly
    moves/zooms during the scene.

    Motion patterns alternate between scenes/images so the whole
    video does not feel repetitive:

        0 -> slow zoom in + slight left-to-right movement
        1 -> slow zoom out + slight right-to-left movement
        2 -> slow zoom in + slight right-to-left movement
        3 -> slow zoom out + slight left-to-right movement

    The clip is cropped back to VIDEO_SIZE, so no black bars appear.
    """

    width, height = VIDEO_SIZE

    # Keep the movement subtle. Large movement makes AI-generated
    # still images look unnatural.
    zoom_start = 1.02
    zoom_end = 1.08

    pattern = motion_index % 4

    if pattern == 0:
        # Zoom in, move from left to right.
        direction = 1
        zoom_from = zoom_start
        zoom_to = zoom_end

    elif pattern == 1:
        # Zoom out, move from right to left.
        direction = -1
        zoom_from = zoom_end
        zoom_to = zoom_start

    elif pattern == 2:
        # Zoom in, move from right to left.
        direction = -1
        zoom_from = zoom_start
        zoom_to = zoom_end

    else:
        # Zoom out, move from left to right.
        direction = 1
        zoom_from = zoom_end
        zoom_to = zoom_start

    # Resize dynamically over time.
    animated = clip.resize(
        lambda t: (
            zoom_from
            + (zoom_to - zoom_from)
            * min(1.0, max(0.0, t / max(duration, 0.001)))
        )
    )

    # After resizing, crop a VIDEO_SIZE window that moves slowly
    # horizontally. This gives a real camera-pan feeling.
    def crop_frame(get_frame, t):

        frame = get_frame(t)

        frame_h, frame_w = frame.shape[:2]

        max_x = max(
            0,
            frame_w - width
        )

        max_y = max(
            0,
            frame_h - height
        )

        progress = min(
            1.0,
            max(
                0.0,
                t / max(duration, 0.001)
            )
        )

        # Keep vertical movement very small.
        vertical_progress = (
            0.5
            + 0.08 * np.sin(progress * np.pi)
        )

        if direction > 0:
            horizontal_progress = progress
        else:
            horizontal_progress = 1.0 - progress

        x = int(
            max_x * horizontal_progress
        )

        y = int(
            max_y * vertical_progress
        )

        x = max(
            0,
            min(x, max_x)
        )

        y = max(
            0,
            min(y, max_y)
        )

        cropped = frame[
            y:y + height,
            x:x + width
        ]

        # Safety fallback in case MoviePy/PIL rounding produces
        # a frame that is one pixel smaller than VIDEO_SIZE.
        if (
            cropped.shape[0] != height
            or cropped.shape[1] != width
        ):
            from PIL import Image

            cropped = np.array(
                Image.fromarray(
                    cropped
                ).resize(
                    (width, height),
                    Image.Resampling.LANCZOS
                )
            )

        return cropped

    animated = animated.fl(
        crop_frame,
        apply_to=["mask"] if animated.mask else []
    )

    return animated.set_duration(
        duration
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
    # Main scene text comes directly from MongoDB.
    #
    # IMPORTANT:
    # The main text is used for ONE voice track.
    # sub_image_prompts only controls which images are shown.
    # --------------------------------------------------------

    text = clean_tts_text(
        scene["text"]
    )

    if not text:
        raise ValueError(
            f"❌ Scene {scene_number} contains empty narration text"
        )

    # --------------------------------------------------------
    # MongoDB structure:
    #
    # "sub_image_prompts": [
    #   {
    #       "text": "...",
    #       "image_prompt": "..."
    #   },
    #   ...
    # ]
    # --------------------------------------------------------

    sub_image_prompts = scene[
        "sub_image_prompts"
    ]

    if not sub_image_prompts:
        raise ValueError(
            f"❌ Scene {scene_number} contains no image prompts"
        )

    print(
        f"📝 Text: {text[:150]}...",
        flush=True
    )

    print(
        f"🎨 Sub-image prompts: "
        f"{len(sub_image_prompts)}",
        flush=True
    )

    for prompt_index, item in enumerate(
        sub_image_prompts,
        start=1
    ):

        sub_text = item.get(
            "text",
            ""
        )

        image_prompt = item[
            "image_prompt"
        ]

        print(
            f"   🖼️ Image "
            f"{prompt_index}/{len(sub_image_prompts)}",
            flush=True
        )

        if sub_text:

            print(
                f"      📝 Sub-text: "
                f"{sub_text[:100]}...",
                flush=True
            )

        print(
            f"      🎨 Prompt: "
            f"{image_prompt[:120]}...",
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

    if (
        voice
        and os.path.exists(audio_path)
    ):

        try:

            audio = AudioFileClip(
                audio_path
            )

        except Exception as e:

            print(
                f"⚠️ Generated audio could "
                f"not be opened: {e}",
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
        f"⏱️ Scene voice/video duration: "
        f"{duration:.2f}s",
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

    image_count = len(
        sub_image_prompts
    )

    print(
        f"🖼️ Total images for scene: "
        f"{image_count}",
        flush=True
    )

    # Short overlap between images.
    # This creates a crossfade instead of a hard cut.
    CROSSFADE_DURATION = 0.45

    for prompt_index, item in enumerate(
        sub_image_prompts,
        start=1
    ):

        image_prompt = item[
            "image_prompt"
        ]

        img_path = (
            f"images/"
            f"s_{scene_number}_"
            f"{prompt_index}.png"
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
        # ----------------------------------------------------

        start_time = (
            duration
            * (prompt_index - 1)
            / image_count
        )

        end_time = (
            duration
            * prompt_index
            / image_count
        )

        image_duration = (
            end_time - start_time
        )

        print(
            f"   ⏱️ Image {prompt_index}: "
            f"{start_time:.2f}s -> "
            f"{end_time:.2f}s "
            f"({image_duration:.2f}s)",
            flush=True
        )

        # ----------------------------------------------------
        # Create the normal fullscreen image clip first.
        # ----------------------------------------------------

        image_clip = create_fullscreen_clip(
            img,
            image_duration,
            prompt_index
        )

        # ----------------------------------------------------
        # Add Ken Burns movement.
        # ----------------------------------------------------

        image_clip = _apply_ken_burns(
            image_clip,
            image_duration,
            (
                index * image_count
                + prompt_index
            )
        )

        # ----------------------------------------------------
        # Crossfade between images.
        #
        # The first image starts normally.
        # Every following image fades in over the previous image.
        # ----------------------------------------------------

        if prompt_index > 1:

            fade_duration = min(
                CROSSFADE_DURATION,
                image_duration * 0.35
            )

            image_clip = image_clip.crossfadein(
                fade_duration
            )

        image_clips.append(
            (
                start_time,
                image_clip
            )
        )

    # --------------------------------------------------------
    # Composite animated images.
    #
    # We intentionally DO NOT concatenate them.
    #
    # concatenate_videoclips() produces hard scene/image cuts.
    # CompositeVideoClip allows the next image to overlap the
    # previous one and create a smooth crossfade.
    # --------------------------------------------------------

    base = CompositeVideoClip(
        [
            clip.set_start(start_time)
            for start_time, clip
            in image_clips
        ],
        size=VIDEO_SIZE
    ).set_duration(
        duration
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

    # --------------------------------------------------------
    # Combine animated image + subtitles.
    # --------------------------------------------------------

    final = CompositeVideoClip(
        [
            base,
            subtitle
        ],
        size=VIDEO_SIZE
    ).set_duration(
        duration
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

    print(
        f"✅ Scene {scene_number} created "
        f"with cinematic motion + "
        f"{CROSSFADE_DURATION:.2f}s crossfade",
        flush=True
    )

    return final
