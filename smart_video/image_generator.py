"""AI image generation with Cloudflare Workers AI as primary and Pollinations as fallback."""

import base64
import json
import os
import time
from datetime import datetime, timezone
import urllib.parse
from io import BytesIO

import requests
from PIL import Image, ImageDraw

from .config import VIDEO_SIZE
from .fonts import get_unicode_font
from .cloudflare_accounts import (
    configured_accounts,
    get_account_status,
    is_quota_exhausted_response,
    mark_exhausted,
    record_usage,
    utc_day,
)


# ============================================================
# CONFIGURATION
# ============================================================

CLOUDFLARE_MODEL = os.getenv(
    "CLOUDFLARE_IMAGE_MODEL",
    "@cf/black-forest-labs/flux-1-schnell",
).strip()

CLOUDFLARE_STEPS = int(
    os.getenv("CLOUDFLARE_IMAGE_STEPS", "1")
)

CLOUDFLARE_RETRIES = int(
    os.getenv("CLOUDFLARE_IMAGE_RETRIES", "2")
)

CLOUDFLARE_TIMEOUT = int(
    os.getenv("CLOUDFLARE_IMAGE_TIMEOUT", "120")
)

POLLINATIONS_RETRIES = int(
    os.getenv("POLLINATIONS_IMAGE_RETRIES", "3")
)

POLLINATIONS_TIMEOUT = int(
    os.getenv("POLLINATIONS_IMAGE_TIMEOUT", "30")
)

# These values are used ONLY for reporting estimated usage when the
# Cloudflare response does not expose an explicit neuron count.
# They do NOT limit or select accounts.
CLOUDFLARE_BASE_NEURONS_PER_TILE = float(
    os.getenv("CLOUDFLARE_BASE_NEURONS_PER_TILE", "4.8")
)

CLOUDFLARE_NEURONS_PER_STEP = float(
    os.getenv("CLOUDFLARE_NEURONS_PER_STEP", "9.6")
)

_USAGE = {
    "story_id": None,
    "story_title": None,
    "started_at": None,
    "images": [],
    "cloudflare_attempts": 0,
    "cloudflare_successes": 0,
    "pollinations_successes": 0,
    "local_fallbacks": 0,
    "estimated_cloudflare_neurons": 0.0,
    "reported_cloudflare_neurons": 0.0,
}


def start_story_usage(story_id=None, story_title=None):
    """Reset image/neuron accounting for one complete story run."""
    global _USAGE
    _USAGE = {
        "story_id": story_id,
        "story_title": story_title,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "images": [],
        "cloudflare_attempts": 0,
        "cloudflare_successes": 0,
        "pollinations_successes": 0,
        "local_fallbacks": 0,
        "estimated_cloudflare_neurons": 0.0,
        "reported_cloudflare_neurons": 0.0,
    }


def _extract_reported_neurons(data):
    """Find an explicit neuron count if Cloudflare ever returns one."""
    if not isinstance(data, dict):
        return None

    preferred_keys = {
        "neurons", "neuron", "neurons_used", "neuron_count",
        "total_neurons", "ai_neurons", "usage_neurons",
    }

    def walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if str(key).lower() in preferred_keys:
                    try:
                        value = float(value)
                        if value >= 0:
                            return value
                    except (TypeError, ValueError):
                        pass
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = walk(item)
                if found is not None:
                    return found
        return None

    return walk(data)


def _estimated_cloudflare_neurons():
    return (
        CLOUDFLARE_BASE_NEURONS_PER_TILE
        + CLOUDFLARE_NEURONS_PER_STEP * CLOUDFLARE_STEPS
    )


def _record_image_usage(
    path, provider,
    cloudflare_neurons=0.0,
    neuron_source="not_applicable",
    cloudflare_attempts=0,
    final_prompt=None,
):
    """Record provider and neuron usage for one requested image."""
    _USAGE["images"].append({
        "image_number": len(_USAGE["images"]) + 1,
        "path": path,
        "provider": provider,
        "cloudflare_neurons": round(float(cloudflare_neurons), 2),
        "neuron_source": neuron_source,
        "cloudflare_attempts": cloudflare_attempts,
        "final_prompt_sent_to_api": final_prompt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    if provider == "cloudflare":
        _USAGE["cloudflare_successes"] += 1
        if neuron_source == "reported":
            _USAGE["reported_cloudflare_neurons"] += float(cloudflare_neurons)
        else:
            _USAGE["estimated_cloudflare_neurons"] += float(cloudflare_neurons)
    elif provider == "pollinations":
        _USAGE["pollinations_successes"] += 1
    elif provider == "local":
        _USAGE["local_fallbacks"] += 1




def get_usage_summary():
    """Return the current story image/provider usage.

    Neuron values are reporting-only. They never control Cloudflare
    account selection, fallback routing, or image generation.
    """
    estimated = round(_USAGE["estimated_cloudflare_neurons"], 2)
    reported = round(_USAGE["reported_cloudflare_neurons"], 2)
    total_known = round(estimated + reported, 2)

    return {
        **_USAGE,
        "estimated_cloudflare_neurons": estimated,
        "reported_cloudflare_neurons": reported,
        "total_cloudflare_neurons": total_known,
        "note": (
            "Neuron values are tracking estimates/reporting only. "
            "They are never used as a routing or quota limit. "
            "Check the Cloudflare dashboard for authoritative billed usage."
        ),
    }


def save_usage_report(output_dir="logs"):
    """Write a machine-readable per-image and story-level usage report."""
    os.makedirs(output_dir, exist_ok=True)

    story_id = _USAGE.get("story_id") or "unknown"
    safe_id = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in str(story_id)
    )

    path = os.path.join(
        output_dir,
        f"neuron_usage_{safe_id}.json",
    )

    report = get_usage_summary()
    report["finished_at"] = datetime.now(timezone.utc).isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return path, report


# ============================================================
# HELPERS
# ============================================================

def _save_cloudflare_image(response, path):
    """
    Cloudflare FLUX.1 Schnell REST responses contain:
        {
            "result": {
                "image": "<base64>"
            }
        }

    Decode the Base64 image, validate it with Pillow, and save it.
    Returns True on success.
    """
    data = response.json()

    result = data.get("result")

    if not isinstance(result, dict):
        raise ValueError(
            f"Unexpected Cloudflare result format: {type(result).__name__}"
        )

    image_base64 = result.get("image")

    if not image_base64:
        raise ValueError(
            "Cloudflare response did not contain result.image"
        )

    # Be tolerant if a future response includes a data-URI prefix.
    if image_base64.startswith("data:") and "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]

    image_bytes = base64.b64decode(image_base64, validate=True)

    # Validate before declaring success.
    image = Image.open(BytesIO(image_bytes))
    image.verify()

    with open(path, "wb") as f:
        f.write(image_bytes)

    return True


CLOUDFLARE_MAX_PROMPT_CHARS = 1800


def _truncate_cloudflare_prompt(prompt):
    """Keep only the first configured number of characters.

    Cloudflare rejects prompts longer than 2048 characters. We keep a
    safety margin by sending at most 1800 characters.
    """
    text = str(prompt or "")
    if len(text) <= CLOUDFLARE_MAX_PROMPT_CHARS:
        return text, False
    return text[:CLOUDFLARE_MAX_PROMPT_CHARS], True


def _log_final_api_prompt(prompt, provider="cloudflare"):
    """Append the exact final prompt used for an image API request to a JSONL log."""
    os.makedirs("logs", exist_ok=True)
    story_id = _USAGE.get("story_id") or "unknown"
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(story_id))
    path = os.path.join("logs", f"image_api_prompts_{safe_id}.jsonl")
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "image_number": len(_USAGE.get("images", [])) + 1,
        "final_prompt_sent_to_api": prompt,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def _generate_cloudflare(prompt, path):
    """Generate with every configured Cloudflare account in order.

    No neuron limit is used.

    Account behavior:
      - Success: return True.
      - HTTP 429 + Cloudflare quota exhaustion (4006/message):
        mark account exhausted for current UTC day and immediately
        continue with the next account.
      - Other failure: retry the same account according to
        CLOUDFLARE_RETRIES, then continue with the next account.
      - If every account is exhausted/failed: return False so the
        caller can use Pollinations.
    """

    accounts = configured_accounts()

    if not accounts:
        print(
            "ℹ️ No Cloudflare accounts are configured; "
            "using Pollinations fallback.",
            flush=True,
        )
        return False

    cloudflare_prompt, was_truncated = _truncate_cloudflare_prompt(prompt)

    if was_truncated:
        print(
            f"✂️ Cloudflare prompt truncated: {len(str(prompt))} -> "
            f"{len(cloudflare_prompt)} characters (first characters kept)",
            flush=True,
        )
    else:
        print(
            f"📏 Cloudflare prompt length: {len(cloudflare_prompt)} characters",
            flush=True,
        )

    prompt_log_path = _log_final_api_prompt(
        cloudflare_prompt,
        provider="cloudflare",
    )

    print(
        f"📝 Final Cloudflare API prompt logged: "
        f"{prompt_log_path}",
        flush=True,
    )

    exhausted_or_failed = set()

    for account in accounts:
        account_index = account["index"]
        account_id = account["account_id"]
        api_token = account["api_token"]

        # Skip an account already marked exhausted in MongoDB today.
        try:
            status = get_account_status(account_id)
            if status.get("exhausted"):
                exhausted_or_failed.add(account_id)
                print(
                    f"⏭️ Cloudflare Account {account_index} skipped: "
                    f"already exhausted for UTC {utc_day()}",
                    flush=True,
                )
                continue
        except Exception as exc:
            # If the status lookup fails, do not falsely mark the account
            # exhausted. The API call itself remains authoritative.
            print(
                f"⚠️ Could not read Cloudflare account status "
                f"for Account {account_index}: {exc}",
                flush=True,
            )

        api_url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{account_id}/ai/run/{CLOUDFLARE_MODEL}"
        )

        payload = {
            "prompt": cloudflare_prompt,
            "steps": CLOUDFLARE_STEPS,
        }

        print(
            f"\n☁️ Cloudflare Account {account_index} "
            f"({account_id}) | UTC {utc_day()}",
            flush=True,
        )

        account_success = False

        for attempt in range(
            1,
            CLOUDFLARE_RETRIES + 1,
        ):
            _USAGE["cloudflare_attempts"] += 1

            print(
                f"☁️ Cloudflare Account {account_index} "
                f"attempt {attempt}/{CLOUDFLARE_RETRIES}",
                flush=True,
            )

            try:
                response = requests.post(
                    api_url,
                    headers={
                        "Authorization": (
                            f"Bearer {api_token}"
                        ),
                        "Content-Type": (
                            "application/json"
                        ),
                    },
                    json=payload,
                    timeout=CLOUDFLARE_TIMEOUT,
                )

                try:
                    response_data = response.json()
                except Exception:
                    response_data = response.text[:2000]

                if response.status_code == 200:
                    try:
                        _save_cloudflare_image(
                            response,
                            path,
                        )

                        reported = (
                            _extract_reported_neurons(
                                response_data
                            )
                        )

                        neurons = (
                            reported
                            if reported is not None
                            else _estimated_cloudflare_neurons()
                        )

                        source = (
                            "reported"
                            if reported is not None
                            else "estimated"
                        )

                        _record_image_usage(
                            path,
                            "cloudflare",
                            neurons,
                            source,
                            attempt,
                            final_prompt=cloudflare_prompt,
                        )

                        # Tracking only. This NEVER controls routing.
                        record_usage(
                            account_id,
                            neurons,
                            source,
                        )

                        print(
                            f"✅ Cloudflare Account "
                            f"{account_index} succeeded.",
                            flush=True,
                        )
                        print(
                            f"   📊 Account neurons recorded: "
                            f"{neurons:.2f} ({source})",
                            flush=True,
                        )

                        account_success = True
                        break

                    except Exception as exc:
                        print(
                            f"⚠️ Cloudflare Account "
                            f"{account_index} returned an invalid "
                            f"image: {exc}",
                            flush=True,
                        )
                        break

                # ------------------------------------------------
                # DAILY QUOTA EXHAUSTED
                # ------------------------------------------------
                if is_quota_exhausted_response(
                    response.status_code,
                    response_data,
                ):
                    print(
                        f"🚨 Cloudflare Account "
                        f"{account_index} is EXHAUSTED.",
                        flush=True,
                    )
                    print(
                        f"   HTTP {response.status_code}: "
                        f"{response_data}",
                        flush=True,
                    )

                    mark_exhausted(
                        account_id,
                        "CLOUDFLARE_429_4006_DAILY_QUOTA",
                    )

                    exhausted_or_failed.add(account_id)

                    print(
                        f"🔄 Account {account_index} marked "
                        f"exhausted for UTC {utc_day()}.",
                        flush=True,
                    )
                    print(
                        "➡️ Switching immediately to the "
                        "next Cloudflare account.",
                        flush=True,
                    )

                    # NEVER retry this account today.
                    break

                print(
                    f"⚠️ Cloudflare Account "
                    f"{account_index} HTTP "
                    f"{response.status_code}: "
                    f"{response_data}",
                    flush=True,
                )

            except requests.RequestException as exc:
                print(
                    f"⚠️ Cloudflare Account "
                    f"{account_index} request failed: {exc}",
                    flush=True,
                )

            if attempt < CLOUDFLARE_RETRIES:
                time.sleep(2)

        if account_success:
            return True

        exhausted_or_failed.add(account_id)

        print(
            f"➡️ Cloudflare Account {account_index} "
            "did not produce an image; checking the next account.",
            flush=True,
        )

    print(
        "❌ All configured Cloudflare accounts have been "
        "checked for this image.",
        flush=True,
    )

    print(
        "➡️ Switching to Pollinations fallback.",
        flush=True,
    )

    return False


def _generate_pollinations(prompt, path):
    """Generate an image using Pollinations as the AI fallback."""
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(prompt)
    )

    for attempt in range(1, POLLINATIONS_RETRIES + 1):
        try:
            print(
                f"🔄 Pollinations fallback attempt "
                f"{attempt}/{POLLINATIONS_RETRIES}",
                flush=True,
            )

            response = requests.get(
                url,
                timeout=POLLINATIONS_TIMEOUT,
            )

            if response.status_code == 200 and response.content:
                # Validate that the response is actually an image.
                image = Image.open(
                    BytesIO(response.content)
                )
                image.verify()

                with open(path, "wb") as f:
                    f.write(response.content)

                _record_image_usage(
                    path,
                    "pollinations",
                    0.0,
                    "not_applicable",
                    0,
                    final_prompt=prompt,
                )

                print(
                    f"✅ Pollinations fallback image saved: {path}",
                    flush=True,
                )
                print(
                    "   📊 Cloudflare neurons for this image: 0.00 "
                    "(Pollinations fallback)",
                    flush=True,
                )
                print(
                    f"   📊 Story Cloudflare neurons so far: "
                    f"{get_usage_summary()['total_cloudflare_neurons']:.2f}",
                    flush=True,
                )

                return True

            print(
                f"⚠️ Pollinations returned HTTP "
                f"{response.status_code}",
                flush=True,
            )

        except Exception as e:
            print(
                "⚠️ Pollinations fallback failed:",
                e,
                flush=True,
            )

        if attempt < POLLINATIONS_RETRIES:
            time.sleep(3)

    return False


# ============================================================
# PUBLIC IMAGE GENERATOR
# ============================================================

def generate_image(
    prompt,
    path,
    fallback_text=None,
):
    """
    Generate a scene image.

    Provider order:
        1. Cloudflare Workers AI
        2. Pollinations
        3. Local text fallback

    The rest of the application only needs to call this function.
    """

    # --------------------------------------------------------
    # 1. CLOUDFLARE MULTI-ACCOUNT ROUTING
    # --------------------------------------------------------

    print(
        f"📅 Cloudflare account routing | UTC {utc_day()}",
        flush=True,
    )

    if _generate_cloudflare(prompt, path):
        return path

    # --------------------------------------------------------
    # 2. POLLINATIONS AI FALLBACK
    # --------------------------------------------------------

    print(
        "🔄 Pollinations image generation...",
        flush=True,
    )

    if _generate_pollinations(prompt, path):
        return path

    # --------------------------------------------------------
    # 3. LOCAL FALLBACK
    # --------------------------------------------------------

    print(
        "🖼️ Using local fallback image...",
        flush=True,
    )

    try:
        img = Image.new(
            "RGB",
            VIDEO_SIZE,
            (20, 20, 20),
        )

        draw = ImageDraw.Draw(img)

        font = get_unicode_font(
            45,
            bold=True,
        )

        text = fallback_text or "Scene"

        words = text.split()
        lines = []
        line = ""

        for word in words:
            if len(line + word) < 20:
                line += word + " "
            else:
                lines.append(line.strip())
                line = word + " "

        if line.strip():
            lines.append(line.strip())

        lines = lines[:4]

        y = VIDEO_SIZE[1] // 2 - 100

        for i, line_text in enumerate(lines):
            bbox = draw.textbbox(
                (0, 0),
                line_text,
                font=font,
            )

            width = bbox[2] - bbox[0]

            draw.text(
                (
                    (VIDEO_SIZE[0] - width) // 2,
                    y + i * 60,
                ),
                line_text,
                font=font,
                fill=(255, 255, 255),
            )

        img.save(path)

        _record_image_usage(
            path,
            "local",
            0.0,
            "not_applicable",
            0,
        )

        print(
            f"⚠️ Local fallback saved: {path}",
            flush=True,
        )
        print(
            "   📊 Cloudflare neurons for this image: 0.00 "
            "(local fallback)",
            flush=True,
        )

        return path

    except Exception as e:
        print(
            "❌ Final fallback failed:",
            e,
            flush=True,
        )

        return None
