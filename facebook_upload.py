"""
Upload the generated video to a Facebook Page.

Required environment variables:
    FB_PAGE_ID
    FB_PAGE_ACCESS_TOKEN

Optional environment variables:
    FB_GRAPH_API_VERSION   default: v24.0
    FB_VIDEO_PATH          default: final_video.mp4
    FB_POST_TITLE          default: Smart Learning Lab - New Story
    FB_POST_DESCRIPTION    default: generic description
    MONGODB_URI             optional
    STORY_ID                optional

If STORY_ID and MONGODB_URI are supplied, the script tries to read
the story title from MongoDB and uses it as the Facebook video title.

This script publishes a normal Facebook Page video using:
    POST /{page_id}/videos
"""

import os
import sys
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

PAGE_ID = os.getenv("FB_PAGE_ID", "").strip()
ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()

GRAPH_API_VERSION = os.getenv(
    "FB_GRAPH_API_VERSION",
    "v24.0"
).strip()

VIDEO_PATH = os.getenv(
    "FB_VIDEO_PATH",
    "final_video.mp4"
).strip()

DEFAULT_TITLE = os.getenv(
    "FB_POST_TITLE",
    "Smart Learning Lab - New Story"
).strip()

DEFAULT_DESCRIPTION = os.getenv(
    "FB_POST_DESCRIPTION",
    (
        "Watch this inspiring story from Smart Learning Lab.\n\n"
        "Follow our Facebook Page for more stories."
    )
).strip()

MONGODB_URI = os.getenv(
    "MONGODB_URI",
    ""
).strip()

STORY_ID = os.getenv(
    "STORY_ID",
    ""
).strip()


# ============================================================
# VALIDATION
# ============================================================

def validate_configuration():
    if not PAGE_ID:
        raise RuntimeError(
            "FB_PAGE_ID is not configured."
        )

    if not ACCESS_TOKEN:
        raise RuntimeError(
            "FB_PAGE_ACCESS_TOKEN is not configured."
        )

    video_file = Path(VIDEO_PATH)

    if not video_file.exists():
        raise FileNotFoundError(
            f"Video file not found: {VIDEO_PATH}"
        )

    if video_file.stat().st_size == 0:
        raise RuntimeError(
            f"Video file is empty: {VIDEO_PATH}"
        )


# ============================================================
# OPTIONAL MONGODB STORY TITLE
# ============================================================

def get_story_title_from_mongodb():
    """
    Read the title for STORY_ID from MongoDB when both
    MONGODB_URI and STORY_ID are available.

    Returns None when MongoDB lookup is unavailable.
    """

    if not MONGODB_URI or not STORY_ID:
        return None

    try:
        from pymongo import MongoClient

        print(
            f"🔎 Reading story title for {STORY_ID}...",
            flush=True
        )

        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=10000
        )

        try:
            client.admin.command("ping")

            db = client["storydb"]
            collection = db["story_scenes"]

            story = collection.find_one(
                {
                    "story_id": STORY_ID
                },
                {
                    "title": 1
                }
            )

            if story:
                title = story.get("title")

                if title:
                    print(
                        f"✅ MongoDB story title: {title}",
                        flush=True
                    )

                    return str(title).strip()

            print(
                "⚠️ Story title was not found in MongoDB.",
                flush=True
            )

            return None

        finally:
            client.close()

    except Exception as exc:
        print(
            f"⚠️ MongoDB title lookup failed: {exc}",
            flush=True
        )

        return None


# ============================================================
# FACEBOOK UPLOAD
# ============================================================

def upload_video():
    validate_configuration()

    video_file = Path(VIDEO_PATH)

    # Try to use the actual story title.
    story_title = get_story_title_from_mongodb()

    title = (
        story_title
        if story_title
        else DEFAULT_TITLE
    )

    description = DEFAULT_DESCRIPTION

    # Facebook title should be a reasonable length.
    if len(title) > 255:
        title = title[:252] + "..."

    print(
        "==========================================",
        flush=True
    )

    print(
        "Facebook Page Video Upload",
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )

    print(
        f"Page ID      : {PAGE_ID}",
        flush=True
    )

    print(
        f"Video        : {video_file}",
        flush=True
    )

    print(
        f"Video size   : "
        f"{video_file.stat().st_size / (1024 * 1024):.2f} MB",
        flush=True
    )

    print(
        f"Graph API    : {GRAPH_API_VERSION}",
        flush=True
    )

    print(
        f"Title        : {title}",
        flush=True
    )

    print(
        "Uploading video to Facebook Page...",
        flush=True
    )

    endpoint = (
        f"https://graph.facebook.com/"
        f"{GRAPH_API_VERSION}/"
        f"{PAGE_ID}/videos"
    )

    params = {
        "access_token": ACCESS_TOKEN
    }

    data = {
        "title": title,
        "description": description
    }

    try:
        with video_file.open("rb") as video:

            response = requests.post(
                endpoint,
                params=params,
                data=data,
                files={
                    "source": (
                        video_file.name,
                        video,
                        "video/mp4"
                    )
                },
                timeout=1800
            )

    except requests.RequestException as exc:

        raise RuntimeError(
            f"Facebook upload request failed: {exc}"
        ) from exc

    print(
        f"Facebook HTTP status: {response.status_code}",
        flush=True
    )

    try:
        result = response.json()
    except ValueError:
        result = {
            "raw_response": response.text
        }

    if not response.ok:

        print(
            "❌ Facebook API response:",
            result,
            flush=True
        )

        raise RuntimeError(
            "Facebook video upload failed."
        )

    video_id = result.get("id")

    if not video_id:

        print(
            "❌ Facebook returned no video ID.",
            flush=True
        )

        print(
            "Response:",
            result,
            flush=True
        )

        raise RuntimeError(
            "Facebook upload did not return a video ID."
        )

    print(
        "==========================================",
        flush=True
    )

    print(
        "✅ Facebook video uploaded successfully",
        flush=True
    )

    print(
        f"Facebook video ID: {video_id}",
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )

    return video_id


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:
        upload_video()

    except Exception as exc:

        print(
            f"❌ Facebook upload failed: {exc}",
            flush=True
        )

        sys.exit(1)
