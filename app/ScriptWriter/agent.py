import os
from google.adk.agents import Agent
from pydantic import BaseModel, Field
from typing import List
from dotenv import load_dotenv



load_dotenv()


# --- Define Output Schema ---
class ScriptLine(BaseModel):
    sec: int = Field(
        description="The second number in the video timeline, starting from 1 up to video duration."
    )
    scene: str = Field(
        description="A detailed description of the video scene for this second. Must repeat the core context so each second is self-contained."
    )
    dialog: str = Field(
        description="Short spoken text (character line or narration). Only used for voice."
    )
    non_dialog: str = Field(
        description="Non-verbal audio cues (music, ambient sound, sound effects)."
    )
    gender: str = Field(
        description="The speaker’s gender if there is dialog ('male', 'female', 'neutral'), or 'none' if no speaker."
    )



class ScriptOutput(BaseModel):
    script: List[ScriptLine] = Field(
        description="A list of scene/dialog pairs, one for each second of the video."
    )


# --- Define System Prompt ---
video_duration = int(os.getenv("VIDEO_DURATION", 30))  # Total duration of the video in seconds

systemPrompt = f"""
You are a Script Agent.
Your task is to break down any given scene idea into a {video_duration}-second script.
The output must always be in JSON list format, containing exactly {video_duration} items (one for each second).

For each item in the list, include:
- "sec": integer (the second number from 1 to {video_duration})
- "scene": a detailed description of the video scene for that second. Each scene description must repeat the core context (setting, characters, environment) so that every second is self-contained and consistent, even if used independently by an AI video generator that forgets prior context.
- "dialog": a short spoken text for that second (only character lines or narration).
- "non_dialog": non-verbal audio elements (music, background noise, sound effects).
- "gender": the speaker's gender if there is dialog ("male", "female", "neutral"), or "none" if no speaker.

Rules:
1. Maintain continuity across all {video_duration} seconds while ensuring each second contains enough repeated context to stand alone.
2. Keep "scene" descriptions vivid but concise (1-3 sentences).
3. Keep "dialog" very short (1 sentence or less).
4. "non_dialog" can include cues like "soft piano music", "birds chirping", "crowd cheering".
5. "gender" must be filled only if "dialog" is present, otherwise use "none".
6. Ensure exactly {video_duration} items, covering a natural flow from start to finish of the scene.

Return ONLY the JSON list as the output, without any extra explanation.
"""



# --- Create Script Writer Agent ---
root_agent = Agent(
    name="script_writer",
    model="gemini-2.0-flash-exp",
    description="Agent to write structured second-by-second video scripts for AI video generation models.",
    instruction=systemPrompt,
    output_schema=ScriptOutput,
    output_key="script",
)
