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
      "image_prompt": "English image prompt..."
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

## Image generation

The video pipeline uses the following image-provider order:

1. **Cloudflare Workers AI** — primary provider
2. **Pollinations** — automatic AI fallback if Cloudflare fails
3. **Local generated fallback** — used only if both AI providers fail

For Cloudflare REST API image generation, configure these environment variables:

```bash
export CLOUDFLARE_ACCOUNT_ID="your-cloudflare-account-id"
export CLOUDFLARE_API_TOKEN="your-cloudflare-workers-ai-token"
export CLOUDFLARE_IMAGE_MODEL="@cf/black-forest-labs/flux-1-schnell"
export CLOUDFLARE_IMAGE_STEPS="1"
```

For GitHub Actions, add these repository secrets:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

The workflow already sets the model to `@cf/black-forest-labs/flux-1-schnell` and uses 3 steps to keep image-generation usage lower.

Cloudflare's FLUX.1 Schnell REST response contains the generated image as Base64 in `result.image`; the application decodes and validates that response before saving it.


## Image prompt continuity update

Each generated sub-image request is now self-contained. The generator injects the full story scene text, the exact sub-image moment, the visual direction, and the complete `characters` dictionary into every image request. The character consistency block is deliberately appended at the end of every prompt so Cloudflare/Pollinations receives the same character identity details on every independent request.

This also prevents the empty `MAIN CHARACTER — .` placeholder in older JSON prompts from being used as the character definition.

## Cloudflare neuron usage monitoring

The image generator now prints usage for every generated image and a running story total. It also writes a JSON report to `logs/neuron_usage_<story_id>.json`.

The current FLUX.1 Schnell configuration defaults to `CLOUDFLARE_IMAGE_STEPS=1`, with the usage estimate configured as:
- `CLOUDFLARE_BASE_NEURONS_PER_TILE=4.8`
- `CLOUDFLARE_NEURONS_PER_STEP=9.6`

The default image setting is now `CLOUDFLARE_IMAGE_STEPS=1` to reduce neuron usage. For the observed 1024-class FLUX.1 Schnell output, Cloudflare reported 134.40 neurons at 3 steps; that corresponds to 4 tiles × (4.8 + 3 × 9.6). At 1 step the same tile count is approximately 57.60 neurons/image. The Cloudflare dashboard remains authoritative.

If Cloudflare returns an explicit neuron field in the API response, the tracker records that value as `reported`; otherwise it labels the value `estimated`. The Cloudflare dashboard remains the authoritative source for billed neuron usage.
