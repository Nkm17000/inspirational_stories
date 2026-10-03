"""Build the final MP4 from title card, scenes, and CTA card."""

from moviepy.editor import concatenate_videoclips, vfx

from .config import (
    FPS,
    CTA_URL,
    END_CARD_DURATION,
    TITLE_CARD_DURATION,
)
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

    # --------------------------------------------------------
    # Cinematic transition settings
    # --------------------------------------------------------
    #
    # This is intentionally short. A 0.40s crossfade keeps the
    # story continuous without making every scene look blurry.
    #
    TRANSITION_DURATION = 0.40

    # --------------------------------------------------------
    # Opening title page
    # --------------------------------------------------------

    print(
        f"\n📖 Adding opening title page: {title}",
        flush=True
    )

    title_clip = create_title_card(
        title,
        TITLE_CARD_DURATION
    )

    clips.append(
        title_clip
    )

    # --------------------------------------------------------
    # Story scenes
    # --------------------------------------------------------

    for i, scene in enumerate(scenes):

        print(
            f"\n🎬 Building story scene "
            f"{i + 1}/{len(scenes)}",
            flush=True
        )

        clip = create_scene(
            scene,
            i
        )

        if clip is None:
            raise ValueError(
                f"❌ Scene {i + 1} returned no video clip"
            )

        if clip.duration is None or clip.duration <= 0:
            raise ValueError(
                f"❌ Scene {i + 1} has invalid duration: "
                f"{clip.duration}"
            )

        clips.append(
            clip
        )

    # --------------------------------------------------------
    # Validate clips before adding CTA
    # --------------------------------------------------------

    if len(clips) <= 1:
        raise ValueError(
            "❌ No story scenes were generated"
        )

    # --------------------------------------------------------
    # Final Like / Subscribe / CTA page
    # --------------------------------------------------------

    print(
        f"\n📣 Adding final Like/Subscribe page: "
        f"{CTA_URL}",
        flush=True
    )

    end_card = create_end_card(
        END_CARD_DURATION
    )

    clips.append(
        end_card
    )

    # --------------------------------------------------------
    # Prepare cinematic crossfades
    # --------------------------------------------------------
    #
    # Old behavior:
    #
    #   Scene 1 | Scene 2 | Scene 3
    #             HARD CUT
    #
    # New behavior:
    #
    #   Scene 1 ─────────╲
    #                    ╲ Scene 2
    #                     ╲────────
    #
    # The next clip fades in while the previous clip is still
    # playing. Negative padding creates the overlap.
    # --------------------------------------------------------

    transitioned_clips = []

    for index, clip in enumerate(clips):

        if index == 0:

            # Opening title starts normally.
            transitioned_clips.append(
                clip
            )

        else:

            fade_duration = min(
                TRANSITION_DURATION,
                max(
                    0.05,
                    clip.duration * 0.30
                )
            )

            print(
                f"🎞️ Crossfade before clip "
                f"{index + 1}: "
                f"{fade_duration:.2f}s",
                flush=True
            )

            transitioned_clips.append(
                clip.crossfadein(
                    fade_duration
                )
            )

    # --------------------------------------------------------
    # Combine all clips with overlap.
    #
    # IMPORTANT:
    # padding=-TRANSITION_DURATION means the next clip starts
    # before the previous clip has completely finished.
    #
    # This is what creates the actual video crossfade.
    # --------------------------------------------------------

    final = concatenate_videoclips(
        transitioned_clips,
        method="compose",
        padding=-TRANSITION_DURATION
    )

    # --------------------------------------------------------
    # Speed up final video by 15%
    #
    # Video and audio are sped up together, preserving sync.
    # --------------------------------------------------------

    final = final.fx(
        vfx.speedx,
        1.15
    )

    print(
        f"\n🎬 Final video duration (1.15x): "
        f"{final.duration:.2f}s",
        flush=True
    )

    # --------------------------------------------------------
    # Write final MP4
    # --------------------------------------------------------

    output_path = "final_video.mp4"

    print(
        f"💾 Writing final video: {output_path}",
        flush=True
    )

    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        threads=2
    )

    print(
        f"✅ Final video created: {output_path}",
        flush=True
    )

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    try:
        final.close()
    except Exception:
        pass

    for clip in clips:
        try:
            clip.close()
        except Exception:
            pass
