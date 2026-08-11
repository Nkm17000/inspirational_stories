"""Build the final MP4 from title card, scenes, and CTA card."""

import os
from moviepy.editor import concatenate_videoclips

from .config import FPS, CTA_URL, END_CARD_DURATION, TITLE_CARD_DURATION
from .title_card import create_title_card
from .scene import create_scene
from .end_card import create_end_card

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
