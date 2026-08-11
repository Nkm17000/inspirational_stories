"""Application entry point for the Smart Video Generator."""

import os
import sys
from datetime import datetime, timezone

from smart_video.db import (
    get_story_from_mongodb,
    update_story_status,
)
from smart_video.video_builder import build_video


def main():

    print(
        "🚀 Starting SmartStudyLab video generator...",
        flush=True,
    )

    story = None

    try:

        # ==================================================
        # Get next story from MongoDB
        # ==================================================

        story, scenes = get_story_from_mongodb()

        # IMPORTANT:
        # Do not silently return.
        # GitHub Action must know that no story was processed.
        if not story:

            print(
                "❌ No PENDING story was found in MongoDB.",
                flush=True,
            )

            print(
                "ℹ️ No video was generated.",
                flush=True,
            )

            return 2

        # ==================================================
        # Story information
        # ==================================================

        story_id = (
            story.get("story_id")
            or story.get("id")
            or story.get("ID")
            or "unknown"
        )

        title = story.get(
            "title",
            "Untitled Story",
        )

        print(
            f"\n📖 TITLE: {title}",
            flush=True,
        )

        print(
            f"🆔 STORY ID: {story_id}",
            flush=True,
        )

        print(
            f"🎬 SCENES: {len(scenes)}",
            flush=True,
        )

        # ==================================================
        # Generate video
        # ==================================================

        print(
            "\n🎬 Starting video generation...",
            flush=True,
        )

        build_video(
            scenes,
            title,
        )

        # ==================================================
        # Verify generated video
        # ==================================================

        output_path = os.path.abspath(
            "final_video.mp4"
        )

        print(
            f"\n🔎 Checking generated video:",
            flush=True,
        )

        print(
            f"📁 {output_path}",
            flush=True,
        )

        if not os.path.isfile(output_path):

            raise RuntimeError(
                "Video generation completed without creating "
                f"final_video.mp4 at {output_path}"
            )

        video_size = os.path.getsize(
            output_path
        )

        if video_size <= 0:

            raise RuntimeError(
                "final_video.mp4 was created but is empty"
            )

        print(
            "\n==========================================",
            flush=True,
        )

        print(
            "✅ FINAL VIDEO CREATED",
            flush=True,
        )

        print(
            f"📁 Path: {output_path}",
            flush=True,
        )

        print(
            f"📦 Size: "
            f"{video_size / (1024 * 1024):.2f} MB",
            flush=True,
        )

        print(
            "==========================================",
            flush=True,
        )

        # ==================================================
        # Mark story COMPLETED
        # ==================================================

        print(
            f"\n🔄 Updating MongoDB status for "
            f"{story_id}...",
            flush=True,
        )

        status_updated = update_story_status(
            story,
            "COMPLETED",
            {
                "completed_at": datetime.now(
                    timezone.utc
                ),
                "last_error": None,
            },
        )

        if not status_updated:

            raise RuntimeError(
                "Video was successfully created, but "
                f"MongoDB status could not be verified "
                f"as COMPLETED for story {story_id}"
            )

        print(
            f"✅ Story {story_id} marked COMPLETED "
            f"and verified in MongoDB",
            flush=True,
        )

        print(
            "\n✅ Video generation completed successfully!",
            flush=True,
        )

        return 0

    except Exception as e:

        print(
            f"\n❌ Video generation failed: {e}",
            flush=True,
        )

        # ==================================================
        # Mark story FAILED
        # ==================================================

        if story:

            failed_story_id = (
                story.get("story_id")
                or story.get("id")
                or story.get("ID")
                or "unknown"
            )

            try:

                status_updated = update_story_status(
                    story,
                    "FAILED",
                    {
                        "last_error": str(e),
                        "failed_at": datetime.now(
                            timezone.utc
                        ),
                    },
                )

                if status_updated:

                    print(
                        f"🔴 Story {failed_story_id} "
                        f"marked FAILED in MongoDB",
                        flush=True,
                    )

                else:

                    print(
                        f"❌ Could not mark story "
                        f"{failed_story_id} as FAILED",
                        flush=True,
                    )

            except Exception as db_error:

                print(
                    f"❌ MongoDB status update failed: "
                    f"{db_error}",
                    flush=True,
                )

        # IMPORTANT:
        # Return non-zero so GitHub Actions knows
        # that video generation failed.
        return 1


if __name__ == "__main__":

    exit_code = main()

    sys.exit(exit_code)