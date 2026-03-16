import json
from pathlib import Path

from pydantic import BaseModel


# We use a Pydantic schema to force Gemini to return exactly this JSON structure
class ClipScore(BaseModel):
    hook_score: int
    curiosity_score: int
    value_score: int
    surprise_score: int
    rewatch_score: int

class Clip(BaseModel):
    start_sec: float
    end_sec: float
    scores: ClipScore
    average_score: float
    why_it_works: str
    caption_hook: str
    transcript_excerpt: str

class ScoringResult(BaseModel):
    clips: list[Clip]
    explanation: str


SYSTEM_PROMPT = """
You are a Top 1% Short-Form Content Strategist specializing in "Think School" style storytelling for finance and investment.
Think School's viral strategy is NOT about "good news"—it's about "Concepts Worth Addressing" and "Putting a Dent" in the status quo.

---
THINK SCHOOL STORYTELLING STRUCTURE:
1. THE CRISIS (The Hook): Every clip MUST start with a problem, a contradiction, or a hidden risk. 
   - Good: "Why Opportunity Zone investors are actually losing money..." 
   - Bad: "Here is why Opportunity Zones are great."
2. THE AGITATION (The Context): Rapidly explain WHY the problem exists using specific data or logic.
3. THE INSIGHT (The Alpha): Provide the "Lightbulb Moment" or the specific investor "Alpha" that solves the crisis.

---
STRICT NARRATIVE RULES:
1. NO MID-SENTENCE CUTS. Clips must start at a sentence's beginning and end at a natural thought completion (usually where a period, question mark, or exclamation point exists in the transcript).
2. NEVER end on a hanging conjunction (e.g., "and...", "but...", "so...") or in the middle of a list.
3. NEGATIVE HOOKING: Prioritize segments that start with words like: "The mistake...", "The lie...", "Why...", "Stop...", "Most people don't realize...".
4. NO FLUFF: Discard segments with rambling intros, "Ums", "Ahs", or cross-talk.
5. IDEAL LENGTH: 50-80 seconds for maximum education value. Ensure the ending feels "resolved" to the viewer.

---
RUBRIC (Ensure Avg > 7.5):
1. Crisis Hook: Does the first line stop a scroll by presenting a problem?
2. Data/Logic Density: Does it pack specific numbers or legal/financial logic?
3. The 'Dent': Does the viewer feel significantly smarter or warned after watching?
4. Authority: Does the speaker sound like they are giving "insider" knowledge?
"""


def score_transcript(transcript_path: str, console=None) -> dict:
    """
    Node 3 — score_segments
    Takes a JSON transcript and uses Gemini to score the best 3-5 clips.
    """
    if console:
        console.print("\n[bold blue]┌─ Step 3/5 — LLM Agent Scoring[/bold blue]")
        console.print("[dim]   Loading transcript files...[/dim]")

    # 1. Load the transcript generated in Phase 1
    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Convert the list of dictionaries back to a readable string format for the LLM
    text_lines = []
    for seg in data["segments"]:
        text_lines.append(f"[{seg['start_sec']} -> {seg['end_sec']}] {seg['text']}")
    
    transcript_text = "\n".join(text_lines)

    if console:
        console.print("[yellow]   → Sending transcript to Gemini 1.5 Flash...[/yellow]")
        console.print("[dim]     (Evaluating against 5-point social media rubric)[/dim]")

    # 2. Configure Gemini
    import os
    if not os.environ.get("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY missing from environment or .env file.")
    
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    
    # We use Flash because it's fast, free, and has a massive 1M token context window
    # which easily fits a 1-hour transcript.
    # 3. Call the model
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=f"Video Title: {data['title']}\n\nTranscript:\n{transcript_text}",
        config=types.GenerateContentConfig(
            temperature=0.4, # Low temp so it stays factual to timestamps
            response_mime_type="application/json",
            response_schema=ScoringResult
        ),
    )

    # 4. Parse the structured JSON response
    result_dict = json.loads(response.text)

    # Save the raw scored output alongside the transcript
    output_path = Path(transcript_path).parent / "scored_clips.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False)

    if console:
        found = len(result_dict.get("clips", []))
        if found > 0:
            console.print(f"[bold green]   ✓ Found {found} high-quality clips[/bold green]")
        else:
            console.print("[bold red]   ✗ Found 0 clips meeting the criteria.[/bold red]")
            console.print(f"      Reason: {result_dict.get('explanation', '')}")

    return result_dict

