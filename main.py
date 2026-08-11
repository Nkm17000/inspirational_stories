"""Application entry point for the Smart Video Generator."""

import os
from datetime import datetime, timezone

from smart_video.config import MONGODB_URI
from smart_video.db import get_story_from_mongodb, update_story_status
from smart_video.video_builder import build_video


def main():
    print("🚀 Starting SmartStudyLab video generator...", flush=True)
    story = None

    try:
        story, scenes = get_story_from_mongodb()

        if not story:
            print("ℹ️ Nothing to process. All stories may already be completed.", flush=True)
            return

        story_id = story.get("story_id", "unknown")
        title = story.get("title", "Untitled Story")

        print(f"\n📖 TITLE: {title}", flush=True)
        print(f"🆔 STORY ID: {story_id}", flush=True)
        print(f"🎬 SCENES: {len(scenes)}", flush=True)

        # The title is taken directly from MongoDB.
        build_video(scenes, title)

        output_path = "final_video.mp4"
        if not os.path.exists(output_path):
            raise RuntimeError("❌ Video generation finished but final_video.mp4 was not created")

        video_size = os.path.getsize(output_path)
        if video_size == 0:
            raise RuntimeError("❌ final_video.mp4 is empty")

        print(
            f"✅ final_video.mp4 created successfully "
            f"({video_size / (1024 * 1024):.2f} MB)",
            flush=True,
        )

        status_updated = update_story_status(
            story,
            "COMPLETED",
            {
                "completed_at": datetime.now(timezone.utc),
                "last_error": None,
            },
        )

        if not status_updated:
            raise RuntimeError(
                f"❌ Video was created, but MongoDB status could not be "
                f"verified as COMPLETED for story {story_id}"
            )

        print(f"\n✅ Story {story_id} marked COMPLETED and verified in MongoDB", flush=True)
        print("\n✅ Video generation completed!", flush=True)

    except Exception as e:
        print(f"\n❌ Video generation failed: {e}", flush=True)

        if story:
            failed_story_id = (
                story.get("story_id")
                or story.get("id")
                or story.get("ID")
                or "unknown"
            )

            status_updated = update_story_status(
                story,
                "FAILED",
                {
                    "last_error": str(e),
                    "failed_at": datetime.now(timezone.utc),
                },
            )

            if status_updated:
                print(f"🔴 Story {failed_story_id} marked FAILED in MongoDB", flush=True)
            else:
                print(f"❌ Could not mark story {failed_story_id} as FAILED", flush=True)

        raise


if __name__ == "__main__":
    main()
