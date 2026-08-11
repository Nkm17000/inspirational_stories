"""Hindi/English subtitle rendering."""

import numpy as np
from PIL import Image, ImageDraw
from moviepy.editor import ImageClip, CompositeVideoClip

from .config import VIDEO_SIZE
from .fonts import get_unicode_font

# ============================================================
# WORD COUNT / SUBTITLE HELPERS
# ============================================================

def split_words_unicode(text):
    """
    Unicode-safe word splitting.

    Python's split() already handles Hindi words separated by spaces,
    but this helper also removes empty tokens and avoids accidental
    punctuation-only tokens.
    """
    if not text:
        return []

    return [
        word.strip()
        for word in str(text).split()
        if word.strip()
    ]

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

    font = get_unicode_font(FONT_SIZE, bold=True)

    # ------------------------------------------------------------
    # Split sentence into words
    # ------------------------------------------------------------

    words = split_words_unicode(text)

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
            render_font = get_unicode_font(34, bold=True)

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
