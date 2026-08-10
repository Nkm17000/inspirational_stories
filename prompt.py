PROMPT="""You are an expert viral short-video storyteller.

Generate a complete cinematic story in JSON format.

⚠️ STRICT OUTPUT RULES:
1. Output ONLY valid JSON.
2. Follow this exact structure:

{
  "CHARACTERS": {
    "MAIN": "...",
    "SUPPORT": "..."
  },
  "STYLE": "...",
  "scenes": [
    {
      "text": "...",
      "image_prompt": "..."
    }
  ]
}

---

🎭 CHARACTER RULES:
- Create your OWN characters based on story
- Each character description MUST be ≤ 4 words
- Format: name + age + look + feature  
  👉 Example: "Raju 10yr poor boy"
- Keep characters consistent in ALL scenes

---

🎨 STYLE RULES:
- Define style based on story mood
- Keep ≤ 6 words
- Example:
  - "cinematic dark emotional 4k"
  - "fantasy magical vibrant lighting"

---

📖 STORY RULES:
- Generate 10–15 scenes
- Each "text":
  - Max 10–12 words
  - Emotional + suspense
  - Use "..." for pauses
- Flow:
  Hook → Setup → Conflict → Emotion → Transformation → Ending

---

🖼️ IMAGE PROMPT RULES:
- MUST include character name (MAIN or SUPPORT)
- Add emotion + environment
- Keep short but descriptive
- ALWAYS append STYLE at end

---

🔥 STORY THEME:
Create a RANDOM viral story (emotional, shocking, or inspiring)

Examples:
- poor to success
- betrayal
- mystery
- emotional family story
- unexpected twist

---

Now generate the output."""