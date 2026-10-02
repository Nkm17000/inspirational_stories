# Smart Video Generator - Modular Version

This project splits the original single Python script into multiple modules
without changing the overall processing flow.

## Directory structure

```text
smart_video_generator/
├── main.py
├── requirements.txt
├── README.md
├── assets/
│   ├── README.txt
│   └── title_page_template.png   <-- put your supplied poster here
├── images/
├── audio/
├── output/
└── smart_video/
    ├── __init__.py
    ├── config.py
    ├── db.py
    ├── fonts.py
    ├── image_generator.py
    ├── voice.py
    ├── subtitles.py
    ├── branding.py
    ├── scene.py
    ├── end_card.py
    ├── title_card.py
    └── video_builder.py
```

## Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Linux/GitHub Actions Hindi font:

```bash
sudo apt-get update
sudo apt-get install -y fonts-noto-core
```

Set MongoDB:

```bash
export MONGODB_URI="your-mongodb-connection-string"
```

Optional:

```bash
export STORY_ID="story_003"
```

Run:

```bash
python main.py
```

## MongoDB

The generator expects the story document in:

- database: `storydb`
- collection: `story_scenes`

The title page gets its dynamic title from:

```json
{
  "story_id": "story_003",
  "title": "लड़की और लोमड़ी",
  "status": "PENDING"
}
```

The scene format is:

```json
{
  "scene_number": 1,
  "text": "Narration...",
  "sub_image_prompts": [
    {
      "text": "Sentence...",
      "scene_prompt": "English image prompt..."
    }
  ]
}
```

## Video order

1. MongoDB title page
2. All story scenes
3. Final Smart Learning Lab CTA page

The generated video is:

```text
final_video.mp4
```

The title is not hard-coded in the title card. It is passed from MongoDB:
`story["title"] -> build_video(..., title) -> create_title_card(title)`.

## Facebook + Instagram publishing

The generated `final_video.mp4` is published to both platforms by `social_publish.py`.

### GitHub Actions secrets

Configure these repository secrets:

```text
FB_PAGE_ID
FB_PAGE_ACCESS_TOKEN
INSTAGRAM_BUSINESS_ACCOUNT_ID
INSTAGRAM_ACCESS_TOKEN
```

Optional:

```text
META_GRAPH_VERSION
```

If `META_GRAPH_VERSION` is not supplied, the Instagram publisher uses `v23.0`, matching the working Instagram quiz agent used as the implementation reference.

### Instagram Reel flow

The Instagram publisher uses the same working sequence as the quiz agent:

1. Validate the Instagram professional account.
2. Create a `REELS` resumable media container.
3. Upload the generated MP4 to Meta's returned upload URI.
4. Poll the container until it reaches `FINISHED`.
5. Publish with `media_publish`.
6. Detect Meta publishing-limit errors and skip Instagram without blocking a successful Facebook post.

### Publishing behavior

`social_publish.py` attempts Facebook and Instagram independently. If one platform fails but the other succeeds, the workflow still completes successfully. If both fail, the publishing step fails.
