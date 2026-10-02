"""MongoDB story loading, normalization, claiming, and status management."""

import time
from datetime import datetime, timezone

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import ConnectionFailure

from .config import (
    COLLECTION_NAME,
    DATABASE_NAME,
    MONGODB_SERVER_TIMEOUT_MS,
    MONGODB_URI,
    STORY_ID,
)


# ---------------------------------------------------------------------------
# MongoDB connection
# ---------------------------------------------------------------------------

def get_mongodb_collection():
    """Create and verify a MongoDB client and return (client, collection)."""
    if not MONGODB_URI:
        raise ValueError("MONGODB_URI environment variable is not set")

    try:
        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=MONGODB_SERVER_TIMEOUT_MS,
        )
        client.admin.command("ping")
        collection = client[DATABASE_NAME][COLLECTION_NAME]

        print(f"✅ MongoDB connected: {DATABASE_NAME}.{COLLECTION_NAME}", flush=True)
        return client, collection
    except ConnectionFailure as exc:
        print(f"❌ MongoDB connection failed: {exc}", flush=True)
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _story_id(story):
    return (
        story.get("story_id")
        or story.get("id")
        or story.get("ID")
        or str(story.get("_id", "unknown"))
    )


def _clean_string(value):
    return value.strip() if isinstance(value, str) else ""


def _normalize_sub_image_prompts(scene):
    """
    Accept the current schema plus common simpler variants.

    Supported input:
      sub_image_prompts: [{text, image_prompt}, ...]
      images: [{text, image_prompt}, ...]
      image_prompts: ["...", "..."]
      image_prompt: "..."
    """
    raw = scene.get("sub_image_prompts")

    if raw is None:
        raw = scene.get("images")

    if raw is None:
        raw = scene.get("image_prompts")

    if raw is None and scene.get("image_prompt"):
        raw = [scene.get("image_prompt")]

    if not isinstance(raw, list):
        return []

    normalized = []

    for item in raw:
        if isinstance(item, str):
            prompt = _clean_string(item)
            sub_text = ""
        elif isinstance(item, dict):
            prompt = _clean_string(
                item.get("image_prompt")
                or item.get("prompt")
                or item.get("imagePrompt")
            )
            sub_text = _clean_string(
                item.get("text")
                or item.get("sub_text")
                or item.get("subtitle")
            )
        else:
            continue

        if prompt:
            normalized.append({
                "text": sub_text,
                "image_prompt": prompt,
            })

    return normalized


def _normalize_scenes(story):
    """Validate and normalize story scenes before video generation."""
    raw_scenes = story.get("scenes")

    if not isinstance(raw_scenes, list):
        raise ValueError("Story must contain a 'scenes' array")

    # Keep the story-level character bible with every normalized scene.
    # Image generation uses this on EVERY sub-image so each request is
    # self-contained and does not depend on previous generated images.
    characters = story.get("characters")
    if not isinstance(characters, dict):
        characters = {}

    style = _clean_string(story.get("style"))

    valid_scenes = []

    for index, scene in enumerate(raw_scenes, start=1):
        if not isinstance(scene, dict):
            print(f"⚠️ Scene {index} skipped: not an object", flush=True)
            continue

        text = _clean_string(
            scene.get("text")
            or scene.get("narration")
            or scene.get("script")
        )
        prompts = _normalize_sub_image_prompts(scene)

        if not text:
            print(f"⚠️ Scene {index} skipped: missing text", flush=True)
            continue

        if not prompts:
            print(
                f"⚠️ Scene {index} skipped: no valid image prompts",
                flush=True,
            )
            continue

        valid_scenes.append({
            "scene_number": scene.get("scene_number", index),
            "text": text,
            "sub_image_prompts": prompts,
            "characters": characters,
            "style": style,
        })

    if not valid_scenes:
        raise ValueError("No valid scenes found")

    return valid_scenes


# ---------------------------------------------------------------------------
# Status management
# ---------------------------------------------------------------------------

def update_story_status(story, status, extra_fields=None, retries=3):
    """Update a story by _id and verify the stored status."""
    if not story:
        print("⚠️ Cannot update MongoDB status: story is missing", flush=True)
        return False

    mongo_id = story.get("_id")
    story_id = _story_id(story)

    fields = {
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    }
    if extra_fields:
        fields.update(extra_fields)

    query = {"_id": mongo_id} if mongo_id is not None else {
        "$or": [
            {"story_id": story_id},
            {"id": story_id},
            {"ID": story_id},
        ]
    }

    for attempt in range(1, retries + 1):
        client = None
        try:
            client, collection = get_mongodb_collection()
            result = collection.update_one(query, {"$set": fields})
            current = collection.find_one(query, {"status": 1})
            actual_status = current.get("status") if current else None

            if actual_status == status:
                print(
                    f"✅ MongoDB status verified: {story_id} -> {status} "
                    f"(matched={result.matched_count}, modified={result.modified_count})",
                    flush=True,
                )
                return True

            print(
                f"⚠️ Status verification {attempt}/{retries}: "
                f"expected={status}, actual={actual_status}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"⚠️ MongoDB status update {attempt}/{retries} failed: {exc}",
                flush=True,
            )
        finally:
            if client:
                client.close()

        if attempt < retries:
            time.sleep(2 * attempt)

    return False


# ---------------------------------------------------------------------------
# Story claiming
# ---------------------------------------------------------------------------

def get_story_from_mongodb():
    """Atomically claim one PENDING story and return (story, normalized_scenes)."""
    client, collection = get_mongodb_collection()

    try:
        query = {"status": "PENDING"}
        if STORY_ID:
            query["$or"] = [
                {"story_id": STORY_ID},
                {"id": STORY_ID},
                {"ID": STORY_ID},
            ]
            print(f"🔎 Requested STORY_ID: {STORY_ID}", flush=True)
        else:
            print("📖 Searching for next PENDING story...", flush=True)

        now = datetime.now(timezone.utc)
        story = collection.find_one_and_update(
            query,
            {
                "$set": {
                    "status": "PROCESSING",
                    "processing_started_at": now,
                    "updated_at": now,
                }
            },
            sort=[("created_at", 1), ("story_id", 1)],
            return_document=ReturnDocument.AFTER,
        )

        if not story:
            print("ℹ️ No PENDING story available.", flush=True)
            return None, []

        story_id = _story_id(story)
        title = _clean_string(story.get("title")) or "Untitled Story"

        print(f"✅ Story claimed: {story_id}", flush=True)
        print(f"📖 Title: {title}", flush=True)

        try:
            scenes = _normalize_scenes(story)
        except ValueError as exc:
            collection.update_one(
                {"_id": story["_id"], "status": "PROCESSING"},
                {
                    "$set": {
                        "status": "FAILED",
                        "last_error": str(exc),
                        "failed_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            raise

        print(f"🎬 Valid scenes: {len(scenes)}", flush=True)
        return story, scenes

    finally:
        client.close()
