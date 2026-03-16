import whisper
from pathlib import Path


_MODEL_SIZES_MB = {
    "tiny": "75",
    "base": "145",
    "small": "460",
    "medium": "1500",
    "large": "2900",
}


def transcribe(audio_path: str, model_size: str = "base", console=None) -> list:
    """
    Node 2 — transcribe_audio
    Runs OpenAI Whisper locally (no API key needed) to produce
    a timestamped transcript.

    Args:
        audio_path:  Path to .wav audio file
        model_size:  Whisper model variant (tiny/base/small/medium/large)
        console:     Optional Rich console for pretty output

    Returns:
        List of dicts: [{ start_sec, end_sec, text }, ...]
    """
    if console:
        mb = _MODEL_SIZES_MB.get(model_size, "?")
        console.print(f"\n[bold blue]┌─ Step 2/2 — Transcribe Audio[/bold blue]")
        console.print(
            f"[dim]   Loading Whisper '{model_size}' model "
            f"(~{mb} MB — downloads once on first run)...[/dim]"
        )

    model = whisper.load_model(model_size)

    if console:
        console.print("[yellow]   → Transcribing... (with word-level timestamps)[/yellow]")

    result = model.transcribe(
        audio_path,
        verbose=False,
        task="transcribe",
        word_timestamps=True
    )

    # Reconstruct segments by sentence to avoid abrupt cuts
    segments = []
    current_text = []
    current_start = None

    # We iterate through 'segments' which now contain 'words' with timestamps
    for seg in result.get("segments", []):
        for word_info in seg.get("words", []):
            word = word_info["word"].strip()
            if current_start is None:
                current_start = word_info["start"]
            
            current_text.append(word_info["word"])
            
            # Check if the word ends with sentence-terminal punctuation
            if word.endswith(('.', '?', '!')):
                segments.append({
                    "start_sec": round(float(current_start), 2),
                    "end_sec": round(float(word_info["end"]), 2),
                    "text": "".join(current_text).strip()
                })
                current_text = []
                current_start = None

    # Add any remaining text as the last segment
    if current_text:
        last_end = result.get("segments", [])[-1].get("end", 0)
        segments.append({
            "start_sec": round(float(current_start), 2),
            "end_sec": round(float(last_end), 2),
            "text": "".join(current_text).strip()
        })

    if console:
        console.print(
            f"[bold green]   ✓ Sentence-aligned transcription complete:[/bold green] "
            f"{len(segments)} thought-complete segments extracted"
        )

    return segments
