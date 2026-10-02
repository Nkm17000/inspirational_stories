# Smart Video Generator - Cloudflare Neuron-Aware Version

This project generates inspirational story videos from MongoDB story JSON. It uses Cloudflare Workers AI for image generation when the locally tracked daily neuron balance is above the configured safety threshold, then uses Pollinations when the balance is at or below that threshold or when Cloudflare fails.

## Provider routing

For every image:

1. Read the persistent UTC-day Cloudflare neuron ledger.
2. Print the current day's used and remaining neurons.
3. If **remaining > 200**, try Cloudflare Workers AI.
4. If **remaining <= 200**, skip Cloudflare and use Pollinations.
5. If Cloudflare is selected but fails, use Pollinations.
6. If both AI providers fail, use the local fallback image.

Cloudflare's current Workers AI documentation states that the free allocation is 10,000 neurons per day and resets at 00:00 UTC. Cloudflare's dashboard is authoritative for actual billed usage; the project ledger is a local routing estimate unless an explicit neuron value is returned by the API response.

## Exact final API prompt logging

The exact final prompt assembled by `scene.py` is the prompt passed to the image generator. Before a Cloudflare request, it is appended to:

```text
logs/image_api_prompts_<story_id>.jsonl
```

Each record contains:

- timestamp
- provider
- image number
- `final_prompt_sent_to_api`

The same final prompt is also stored in the per-story neuron report under each image's `final_prompt_sent_to_api` field.

## Daily neuron logs

The persistent daily ledger is:

```text
logs/cloudflare_daily_usage_YYYY-MM-DD.json
```

The story-level report is:

```text
logs/neuron_usage_<story_id>.json
```

The daily ledger survives separate program runs on the same machine/GitHub runner filesystem. If GitHub Actions starts on a fresh runner each day, the local ledger naturally starts at zero for that runner; use Cloudflare's dashboard as the authoritative account-level balance.

## Environment variables

```text
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_IMAGE_MODEL=@cf/black-forest-labs/flux-1-schnell
CLOUDFLARE_IMAGE_STEPS=1
CLOUDFLARE_DAILY_NEURON_LIMIT=10000
CLOUDFLARE_POLLINATIONS_THRESHOLD=200
CLOUDFLARE_DAILY_USAGE_DIR=logs
CLOUDFLARE_IMAGE_RETRIES=2
CLOUDFLARE_IMAGE_TIMEOUT=120

POLLINATIONS_IMAGE_RETRIES=3
POLLINATIONS_IMAGE_TIMEOUT=30

CLOUDFLARE_BASE_NEURONS_PER_TILE=4.8
CLOUDFLARE_NEURONS_PER_STEP=9.6
```

`CLOUDFLARE_POLLINATIONS_THRESHOLD=200` is the requested routing rule. Change it only if you intentionally want a different safety buffer.

## Recommended story JSON format

Use a story-level `characters` dictionary as the character bible. Character physical descriptions must remain in English and should stay unchanged throughout the story. Story title, category, narration, labels and ending message should be Hindi. Image `scene_prompt` values should be English.

```json
{
  "story_id": "कहानी_001",
  "title": "आईने के सामने लिया फैसला",
  "status": "PENDING",
  "category": "आत्मविश्वास और जीवन की सीख",
  "language": "hi",
  "style": "Cinematic, cartoon-realistic avatar, detailed, natural pose, realistic lighting, soft shadows",
  "characters": {
    "MAIN": {
      "id": "meera123@32",
      "name": "Meera",
      "description": "29-year-old Indian girl, medium-brown skin, long black hair tied in a simple braid, dark brown eyes, slim build, wearing a pale-yellow cotton kurta and navy-blue salwar, small silver earrings."
    },
    "SUPPORT": {
      "id": "sarla456@45",
      "name": "Sarla",
      "description": "45-year-old Indian woman, warm brown skin, black hair with a few gray strands tied in a bun, medium build, dark brown eyes, wearing a simple maroon sari and thin gold earrings."
    }
  },
  "scenes": [
    {
      "scene_number": 1,
      "text": "मीरा एक छोटे शहर के साधारण घर में रहती थी। उसे चित्र बनाना बहुत पसंद था, लेकिन वह अपने बनाए चित्र किसी को दिखाने से डरती थी।",
      "sub_image_prompts": [
        {
          "text": "मीरा चित्र बनाती हुई",
          "scene_prompt": "Meera is sitting on a wooden chair inside a simple Indian home, quietly drawing in a sketchbook near a window, looking thoughtful and slightly emotional."
        },
        {
          "text": "मीरा अपना चित्र छिपाती हुई",
          "scene_prompt": "Meera quietly closes her sketchbook and places it inside a wooden drawer, looking nervous and hesitant, with the same home interior visible around her."
        }
      ]
    },
    {
      "scene_number": 2,
      "text": "अगले दिन सरला ने मीरा से पूछा कि वह अपने चित्र दूसरों को क्यों नहीं दिखाती।",
      "sub_image_prompts": [
        {
          "text": "सरला मीरा से बात करती हुई",
          "scene_prompt": "Meera is sitting with Sarla in the same simple Indian home, listening carefully as Sarla speaks to her with a warm encouraging expression."
        },
        {
          "text": "मीरा आत्मविश्वास से मुस्कुराती हुई",
          "scene_prompt": "Meera stands near the window holding her sketchbook, looking calmer and more confident after speaking with Sarla."
        }
      ]
    }
  ],
  "ending_message": "कभी-कभी सबसे बड़ा कदम दुनिया के सामने नहीं, बल्कि अपने डर के सामने उठाना पड़ता है।",
  "voiceover_style": "warm emotional Hindi voice",
  "music_style": "soft cinematic inspirational music",
  "cta": "ऐसी प्रेरणादायक कहानियों के लिए हमें फॉलो करें।"
}
```

## JSON rules for future story generation

- `story_id`: unique for every story.
- `status`: always `PENDING` before processing.
- `title`, `category`, scene `text`, `text` labels and `ending_message`: Hindi.
- Character `id`, `name` and `description`: English. Keep character IDs stable and unique.
- `description`: English, detailed enough to preserve face, age, hair, skin tone, body proportions, clothing and accessories.
- `style`: English.
- `scene_prompt`: English.
- Do not paste the complete character description into every `scene_prompt`; Python adds it automatically.
- Every independent image request receives the character bible again, so it does not depend on the previous API request remembering the character.
- Reuse the same character ID and description whenever the character appears.
- Do not introduce a new persistent character unless that character is added to the story-level `characters` dictionary.
- Keep scenes chronological and visually continuous.
- Do not put subtitles, captions, logos, watermarks or UI text in `scene_prompt`.
- Use 1–3 `sub_image_prompts` per scene.
- Use `scene_prompt`, not `image_prompt`, for new JSON. `image_prompt` remains supported for older documents.

## Final prompt sent to Cloudflare

For every independent image API call, Python builds a self-contained prompt similar to this:

```text
FULL SCENE CONTEXT:
मीरा एक छोटे शहर के साधारण घर में रहती थी। उसे चित्र बनाना बहुत पसंद था, लेकिन वह अपने बनाए चित्र किसी को दिखाने से डरती थी।

SUB-IMAGE LABEL:
मीरा चित्र बनाती हुई

SCENE:
Meera is sitting on a wooden chair inside a simple Indian home, quietly drawing in a sketchbook near a window, looking thoughtful and slightly emotional.

STYLE:
Cinematic, cartoon-realistic avatar, detailed, natural pose, realistic lighting, soft shadows

MAIN CHARACTER ID: meera123@32 — always use the same Meera character.
CHARACTER: 29-year-old Indian girl, medium-brown skin, long black hair tied in a simple braid, dark brown eyes, slim build, wearing a pale-yellow cotton kurta and navy-blue salwar, small silver earrings.

KEEP CHARACTER CONSISTENT:
Preserve Meera's face, hairstyle, age, skin tone, body proportions, clothing, accessories and identity across every scene. Only change pose, expression and action according to the current scene.

FINAL RULES:
Show only the current story moment. Maintain location and visual continuity. No text, subtitles, captions, logo or watermark.
```

The actual log contains the exact final string, not this shortened example.

## Run

```bash
pip install -r requirements.txt
python main.py
```

MongoDB configuration:

```text
MONGODB_URI=your-mongodb-connection-string
MONGODB_DATABASE=storydb
MONGODB_COLLECTION=story_scenes
```

Optional:

```text
STORY_ID=your_story_id
```

## Output

Generated images:

```text
images/
```

Audio:

```text
audio/
```

Final video:

```text
final_video.mp4
```

Usage logs:

```text
logs/cloudflare_daily_usage_YYYY-MM-DD.json
logs/neuron_usage_<story_id>.json
logs/image_api_prompts_<story_id>.jsonl
```

## Important neuron-usage note

Cloudflare documents the 10,000-neuron daily allocation and the 00:00 UTC reset. The project cannot claim that its local ledger is the exact account-level remaining balance because the REST inference response does not provide a documented daily remaining-neuron counter. When Cloudflare returns an explicit neuron count, that count is recorded; otherwise the configured estimate is recorded. For exact account billing/remaining usage, check the Cloudflare Workers AI dashboard.

## MongoDB story schema compatibility

The generator accepts the original story schema without requiring any JSON migration.
The preferred current image field is:

`scenes[].sub_image_prompts[].scene_prompt`

For backward compatibility it also accepts `image_prompt`, `scenePrompt`, `prompt`, `imagePrompt`, `images`, and `image_prompts` variants.

The story-level `characters` and `style` are copied into the in-memory scene representation. They are then included in every independent image-generation request so Instagram integration does not change the MongoDB schema or character-prompt behavior.

For a new story, use `status: "PENDING"`. The generator changes it to `PROCESSING` and finally `COMPLETED` or `FAILED`.

## Publishing

After the MP4 is generated, the GitHub Actions workflow publishes the same `final_video.mp4` independently to Facebook and Instagram as a Reel. Instagram publishing is isolated from story generation and recognizes Meta content-publishing-limit responses.
