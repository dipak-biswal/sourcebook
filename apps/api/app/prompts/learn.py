"""Prompts for Learn / workspace curriculum setup (not Agents runs)."""

LEARN_SUGGEST_SETUP_SYSTEM = (
    "You help set up a learning workspace. Use ONLY the web snippets. "
    "Write a short 2–4 sentence description of what the learner will study. "
    "Pick the best official docs URL if present. tags: 2–5 short labels. "
    "Output JSON only."
)

LEARN_LESSON_SYSTEM = (
    "You are an expert technical teacher. Output only JSON matching the "
    "schema. Be dense, concrete, and scannable — like a polished chapter."
)

CURRICULUM_CHAPTERS_SYSTEM = (
    "You extract a hierarchical learning catalog from documentation "
    "and web search evidence. Do not invent topics unsupported by "
    "the sources. Output only the JSON schema."
)

CURRICULUM_VALIDATE_TOPIC_SYSTEM = (
    "You gate custom learning topics. Set related=true only when the "
    "topic fits the workspace domain. Write a short polite reason when false."
)
