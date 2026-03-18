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
You are a Top 1% Short-Form Content Strategist specializing in "Think School" and "Raj Shamani" style storytelling.
Your goal is to find the most "Viral" segments from long podcasts and turn them into high-engagement Reels/Shorts.

---
EDITORIAL STRATEGY (Think School + Raj Shamani):
1. THE CRISIS HOOK: Every clip MUST start with a bold claim, a contradiction, or a high-value insight. 
   - Good: "The reason 90% of OZ investors will fail..."
   - Good: "Most people think Opportunity Zones are a tax haven, but here's the lie..."
   - Action: Analyze how creators like Raj Shamani pick the segments where the guest is most passionate.
2. THE ALPHA INSIGHT: Provide "Insider Knowledge" that makes the viewer feel 10x smarter.

---
STRICT NARRATIVE & DURATION RULES:
1. NON-NEGOTIABLE DURATION: Each clip MUST be between 30 and 60 seconds (Ideal for Shorts/Reels). 
2. ABSOLUTE MAXIMUM: Never exceed 90 seconds. If a logic block is too long, find the most punchy sub-segment.
3. NO MID-SENTENCE CUTS. Clips must start at a sentence's beginning and end at a natural thought completion (punctuation: . ? !).
4. NEVER end on a hanging conjunction or in the middle of a list.
5. NO FLUFF: Discard segments with rambling intros, "Ums", "Ahs", or cross-talk.

---
RUBRIC (Ensure Avg > 7.5):
1. Scroll-Stopping Hook: Does the first line present a problem or a bold claim?
2. Logical Alpha: Does it pack specific numbers or legal/financial "Alpha"?
3. Viral Duration: Is it strictly 30-90 seconds? (Closer to 45s is best).
4. Clean Narrative: Does it start and end perfectly without mid-word cuts?
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
        console.print("[yellow]   → Sending transcript to Gemini 3 Flash...[/yellow]")
        console.print("[dim]     (Evaluating against 5-point social media rubric)[/dim]")

    # ── 2. Configure Gemini Waterfall ────────────────────────────────────
    import os
    if not os.environ.get("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY missing from environment or .env file.")
    
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    
    MODELS_WATERFALL = [
        "gemini-3-flash",        # Best — try this first, might work free
        "gemini-2.5-pro",        # Very good — 100 requests/day free
        "gemini-2.5-flash",      # Good — 250 requests/day free
        "gemini-2.5-flash-lite"  # Fastest — 1000 requests/day free
    ]

    response = None
    last_error = None

    for model_name in MODELS_WATERFALL:
        try:
            if console:
                console.print(f"[yellow]   → Attempting scoring with {model_name}...[/yellow]")
            
            response = client.models.generate_content(
                model=model_name,
                contents=f"Video Title: {data['title']}\n\nTranscript:\n{transcript_text}",
                config=types.GenerateContentConfig(
                    temperature=0.4, # Low temp so it stays factual to timestamps
                    response_mime_type="application/json",
                    response_schema=ScoringResult
                ),
            )
            # If we reach here, the call succeeded
            break
        except Exception as e:
            last_error = e
            if console:
                console.print(f"[dim red]     ! {model_name} failed: {str(e)}[/dim red]")
            continue

    if not response:
        raise RuntimeError(f"All models in waterfall failed. Last error: {str(last_error)}")

    # 4. Parse the structured JSON response
    result_dict = json.loads(response.text)

    # Post-process model output to enforce constraints + thresholds:
    # - Keep only clips with avg score > 7
    # - Prefer 30–90s, but allow up to 120s if needed (extraction will choose natural end)
    filtered = []
    for c in result_dict.get("clips", []):
        try:
            avg = float(c.get("average_score", 0))
            s = float(c.get("start_sec"))
            e = float(c.get("end_sec"))
        except Exception:
            continue

        if avg <= 7:
            continue

        dur = e - s
        if dur < 30:
            continue
        if dur > 120:
            # Don't hard-trim here; extraction will skip if it can't end naturally <=120.
            c["end_sec"] = s + 120
        filtered.append(c)

    result_dict["clips"] = filtered

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

