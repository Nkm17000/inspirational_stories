"""Edge-TTS language detection and voice generation."""

import os
import time
import asyncio
import threading
import edge_tts
import nest_asyncio

nest_asyncio.apply()

# ============================================================
# VOICE
# ============================================================

# ============================================================
# LANGUAGE + VOICE HELPERS
# ============================================================

def detect_text_language(text):
    """
    Detect Hindi vs English from Unicode script.

    Hindi/Devanagari characters are in U+0900-U+097F.
    If enough Devanagari characters are present, use Hindi TTS.
    Otherwise use English TTS.
    """
    if not text:
        return "en"

    devanagari = sum(
        1 for ch in text
        if "\u0900" <= ch <= "\u097F"
    )

    latin = sum(
        1 for ch in text
        if ("A" <= ch <= "Z") or ("a" <= ch <= "z")
    )

    if devanagari > 0 and devanagari >= latin * 0.20:
        return "hi"

    return "en"


def get_voice_candidates(text):
    """
    Return voices in priority order.

    Hindi:
      1. hi-IN-SwaraNeural
      2. hi-IN-AnanyaNeural
      3. hi-IN-MadhurNeural
      4. en-IN-NeerjaNeural

    English:
      1. en-IN-NeerjaNeural
      2. en-IN-AnanyaNeural
      3. en-IN-PrabhatNeural
    """
    language = detect_text_language(text)

    if language == "hi":
        return [
            "hi-IN-SwaraNeural",
            "hi-IN-AnanyaNeural",
            "hi-IN-MadhurNeural",
            "en-IN-NeerjaNeural",
        ]

    return [
        "en-IN-NeerjaNeural",
        "en-IN-AnanyaNeural",
        "en-IN-PrabhatNeural",
    ]


def clean_tts_text(text):
    """
    Normalize text without destroying Hindi Unicode characters.
    """
    if not text:
        return ""

    text = str(text)

    # Remove accidental control characters but preserve Unicode.
    text = "".join(
        ch for ch in text
        if ch in "\n\r\t" or ord(ch) >= 32
    )

    # Normalize whitespace.
    text = " ".join(text.split())

    return text.strip()


def run_async(coro):
    """
    Safely run an async coroutine even when an event loop is already active.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        result = {}

        def runner():
            try:
                result["value"] = asyncio.run(coro)
            except Exception as e:
                result["error"] = e

        import threading
        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()

        if "error" in result:
            raise result["error"]

        return result.get("value")

    return asyncio.run(coro)


# ============================================================
# VOICE
# ============================================================

def generate_voice(
    text,
    path
):
    """
    Generate Edge-TTS audio for both Hindi and English.

    Hindi text is automatically routed to a Hindi voice.
    English text is routed to an Indian-English voice.

    WordBoundary timings are collected when Edge-TTS provides them.
    The video does NOT depend on WordBoundary timings; subtitles use
    the actual generated audio duration.

    Returns:
        (audio_path, word_timings)
    """

    text = clean_tts_text(text)

    if not text:
        print("⚠️ Empty narration text; skipping TTS", flush=True)
        return None, []

    language = detect_text_language(text)
    voices = get_voice_candidates(text)

    print(
        f"🌐 Detected language: "
        f"{'Hindi' if language == 'hi' else 'English'}",
        flush=True
    )

    print(
        f"🎤 Voice candidates: {', '.join(voices)}",
        flush=True
    )

    async def tts(voice_name):
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_name,
            rate="-15%",
            # Explicitly request word boundaries where supported.
            boundary="WordBoundary"
        )

        audio_bytes = bytearray()
        word_timings = []

        async for chunk in communicate.stream():

            chunk_type = chunk.get("type")

            if chunk_type == "audio":
                data = chunk.get("data", b"")

                if data:
                    audio_bytes.extend(data)

            elif chunk_type == "WordBoundary":
                word = chunk.get("text", "").strip()

                if not word:
                    continue

                offset = chunk.get("offset", 0)
                word_duration = chunk.get("duration", 0)

                # Edge-TTS timing units are 100 nanoseconds.
                start_seconds = offset / 10_000_000
                end_seconds = (
                    offset + word_duration
                ) / 10_000_000

                word_timings.append({
                    "word": word,
                    "start": start_seconds,
                    "end": end_seconds
                })

        if not audio_bytes:
            raise RuntimeError(
                f"Edge-TTS returned no audio for voice '{voice_name}'"
            )

        # Write atomically so a failed request never leaves a bad MP3.
        temp_path = path + ".tmp"

        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        if not os.path.exists(temp_path) or os.path.getsize(temp_path) < 1000:
            try:
                os.remove(temp_path)
            except OSError:
                pass

            raise RuntimeError(
                f"TTS produced an invalid/empty audio file for '{voice_name}'"
            )

        os.replace(temp_path, path)

        return word_timings

    # Try each suitable voice. This is much better than retrying
    # the same voice three times when the selected voice is unavailable.
    for voice_index, voice_name in enumerate(voices, start=1):

        for attempt in range(1, 3):

            try:
                print(
                    f"🎤 Voice {voice_index}/{len(voices)} "
                    f"({voice_name}) attempt {attempt}",
                    flush=True
                )

                timings = run_async(tts(voice_name))

                print(
                    f"✅ Voice generated using {voice_name}: "
                    f"{len(timings)} word timings",
                    flush=True
                )

                return path, timings

            except Exception as e:

                print(
                    f"⚠️ {voice_name} failed: {e}",
                    flush=True
                )

                time.sleep(2)

    print(
        "❌ All Edge-TTS voices failed",
        flush=True
    )

    return None, []
