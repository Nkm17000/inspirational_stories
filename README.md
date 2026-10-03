# Smart Video Generator - Cloudflare Neuron-Aware Version

This project generates inspirational story videos from MongoDB story JSON. It uses Cloudflare Workers AI for image generation when the locally tracked daily neuron balance is above the configured safety threshold, then uses Pollinations when the balance is at or below that threshold or when Cloudflare fails.

## Provider routing

For every image:

1. Load all configured Cloudflare accounts in numeric order.
2. Check MongoDB for each account's status for the current UTC date.
3. Skip accounts already marked `exhausted` for that UTC date.
4. Call the first eligible Cloudflare account.
5. If it succeeds, save the image and record neuron usage for that account and UTC date.
6. If Cloudflare returns HTTP 429 with error code `4006` or a daily-allocation/quota exhaustion message, mark that account exhausted in MongoDB for the current UTC date and immediately switch to the next account.
7. Repeat until all configured accounts have been checked.
8. Only after all Cloudflare accounts fail or are exhausted, call Pollinations.
9. If Pollinations also fails, use the local fallback image.

There is **no neuron limit, 8,500 limit, 200-neuron threshold, or neuron-based provider selection**. Neuron values are tracked for reporting only.

An exhausted account is skipped for the rest of the same UTC date. A new UTC date automatically makes the account eligible again.

The persistent MongoDB collection is:

```text
cloudflare_daily_usage
```

Each record is keyed by:

```text
date_utc + account_id
```

and stores `neurons_used`, `image_count`, `exhausted`, `exhausted_reason`, and timestamps.

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
CLOUDFLARE_ACCOUNT_ID_1=
CLOUDFLARE_API_TOKEN_1=

CLOUDFLARE_ACCOUNT_ID_2=
CLOUDFLARE_API_TOKEN_2=

CLOUDFLARE_ACCOUNT_ID_3=
CLOUDFLARE_API_TOKEN_3=

CLOUDFLARE_ACCOUNT_ID_4=
CLOUDFLARE_API_TOKEN_4=

CLOUDFLARE_ACCOUNT_ID_5=
CLOUDFLARE_API_TOKEN_5=

CLOUDFLARE_IMAGE_MODEL=@cf/black-forest-labs/flux-1-schnell
CLOUDFLARE_IMAGE_STEPS=1
CLOUDFLARE_IMAGE_RETRIES=2
CLOUDFLARE_IMAGE_TIMEOUT=120

CLOUDFLARE_USAGE_COLLECTION=cloudflare_daily_usage

POLLINATIONS_IMAGE_RETRIES=3
POLLINATIONS_IMAGE_TIMEOUT=30
```

You can configure more accounts using the same numbered pattern. The code checks up to account 50.

There is no `CLOUDFLARE_DAILY_NEURON_LIMIT` and no `CLOUDFLARE_POLLINATIONS_THRESHOLD`. Neuron estimates are retained only for usage reporting.

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
          "scene_prompt": "COMIC STYLE LOCK: 2D cartoon/comic characters only, never photorealistic or real-looking humans. Consistent illustrated style. Meera is sitting on a wooden chair inside a simple Indian home, quietly drawing in a sketchbook near a window, looking thoughtful and slightly emotional."
        },
        {
          "text": "मीरा अपना चित्र छिपाती हुई",
          "scene_prompt": "COMIC STYLE LOCK: 2D cartoon/comic characters only, never photorealistic or real-looking humans. Consistent illustrated style. Meera quietly closes her sketchbook and places it inside a wooden drawer, looking nervous and hesitant, with the same home interior visible around her."
        }
      ]
    },
    {
      "scene_number": 2,
      "text": "अगले दिन सरला ने मीरा से पूछा कि वह अपने चित्र दूसरों को क्यों नहीं दिखाती।",
      "sub_image_prompts": [
        {
          "text": "सरला मीरा से बात करती हुई",
          "scene_prompt": "COMIC STYLE LOCK: 2D cartoon/comic characters only, never photorealistic or real-looking humans. Consistent illustrated style. Meera is sitting with Sarla in the same simple Indian home, listening carefully as Sarla speaks to her with a warm encouraging expression."
        },
        {
          "text": "मीरा आत्मविश्वास से मुस्कुराती हुई",
          "scene_prompt": "COMIC STYLE LOCK: 2D cartoon/comic characters only, never photorealistic or real-looking humans. Consistent illustrated style. Meera stands near the window holding her sketchbook, looking calmer and more confident after speaking with Sarla."
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
